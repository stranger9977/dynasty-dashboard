# views/roster_impact.py
"""Roster Impact tab: 2026 projected points each manager's rookie haul adds to their
roster — total, and the marginal upgrade to their starting lineup. See Phase B design."""
import pandas as pd
import streamlit as st

from config import STARTER_COUNTS
from ingestion.match_util import normalize_name
from ingestion.roster_impact import points_above_starters, lineup_changes

SCORE_OPTIONS = {"PPR": "pts_ppr", "Half PPR": "pts_half_ppr", "Standard": "pts_std"}


def _collect_drafted(rookies, draft, league_id):
    """{manager: [sleeper_player_id, ...]} from the live draft, mock as fallback."""
    if draft and draft.get("draft_id"):
        from ingestion.sleeper import get_draft_picks, build_roster_to_manager
        try:
            picks = get_draft_picks(draft["draft_id"])
        except Exception:
            picks = []
        if picks:
            roster_to_mgr = build_roster_to_manager(league_id) if league_id else {}
            out = {}
            for pk in picks:
                pid = pk.get("player_id")
                if not pid:
                    continue
                mgr = roster_to_mgr.get(pk.get("roster_id"), f"Team {pk.get('roster_id')}")
                out.setdefault(mgr, []).append(str(pid))
            if out:
                return out
    # mock fallback: map pick player names -> sleeper_id via the rookies frame
    picks = st.session_state.get("draft_picks") or []
    if not picks:
        return {}
    name_to_id = {}
    for _, r in rookies.iterrows():
        if pd.notna(r.get("sleeper_id")):
            name_to_id[normalize_name(str(r["name"]))] = str(r["sleeper_id"])
    out = {}
    for p in picks:
        pid = name_to_id.get(normalize_name(str(p.get("player", ""))))
        if not pid:
            continue
        out.setdefault(p.get("owner", "?"), []).append(pid)
    return out


def render_roster_impact(rookies, draft, league_id):
    st.subheader("Roster Impact — 2026 Projections")

    from ingestion.projections import load_projections
    proj = load_projections()
    if proj.empty:
        st.info("No 2026 projections loaded. Click **Refresh Data** in the sidebar.")
        return
    proj = proj.copy()
    proj["player_id"] = proj["player_id"].astype(str)
    proj_idx = proj.set_index("player_id")

    score_label = st.radio("Scoring", list(SCORE_OPTIONS), horizontal=True, key="ri_score")
    score_col = SCORE_OPTIONS[score_label]

    drafted = _collect_drafted(rookies, draft, league_id)
    if not drafted:
        st.info("No draft picks yet — start your live draft or run a mock "
                "in the Mock Draft Simulator.")
        return

    # baseline rosters (existing players), keyed by manager
    roster_ids = {}
    if league_id:
        from ingestion.sleeper import get_rosters, build_roster_to_manager
        roster_to_mgr = build_roster_to_manager(league_id)
        for r in get_rosters(league_id):
            mgr = roster_to_mgr.get(r["roster_id"], f"Team {r['roster_id']}")
            roster_ids[mgr] = set(str(p) for p in (r.get("players") or []))

    def _frame(ids):
        ids = [i for i in ids if i in proj_idx.index]
        if not ids:
            return pd.DataFrame({"player_id": [], "position": [], score_col: [], "name": []})
        return proj_idx.loc[ids, ["position", score_col, "name"]].reset_index()

    rows, per_mgr, total_roster, matched_roster = [], {}, 0, 0
    for mgr, added_ids in drafted.items():
        added_ids = [str(i) for i in added_ids]
        base_ids = roster_ids.get(mgr, set()) - set(added_ids)   # never double-count
        total_roster += len(base_ids)
        matched_roster += sum(1 for i in base_ids if i in proj_idx.index)
        base_df = _frame(list(base_ids))
        add_df = _frame(added_ids)
        total_added = float(add_df[score_col].sum()) if not add_df.empty else 0.0
        above = points_above_starters(base_df, add_df, STARTER_COUNTS, score_col)
        per_mgr[mgr] = {
            "add_df": add_df,
            "changes": lineup_changes(base_df, add_df, STARTER_COUNTS, score_col),
        }
        rows.append({"manager": mgr, "total_added": round(total_added, 1),
                     "above_starters": round(above, 1)})
    summary = pd.DataFrame(rows).set_index("manager").sort_values(
        "above_starters", ascending=False)

    if total_roster:
        st.caption(f"Projection coverage: {matched_roster}/{total_roster} rostered "
                   f"players matched · scoring {score_label}")

    # Horizontal bars, ranked high-to-low.
    from views.charts import hbar
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Total projected pts added**")
        hbar(summary["total_added"], "pts", color="#377eb8")
    with c2:
        st.markdown("**Pts added above starters**")
        hbar(summary["above_starters"], "pts", color="#4daf4a")

    st.markdown("---")
    st.caption("Expand a manager for the per-slot change (↑ added / ↓ bumped) and their "
               "current veteran starters.")
    for mgr in summary.index:
        d = per_mgr[mgr]
        add_df, changes = d["add_df"], d["changes"]
        head = (f"{mgr} — +{summary.loc[mgr, 'above_starters']:.0f} above starters · "
                f"{summary.loc[mgr, 'total_added']:.0f} total")
        with st.expander(head):
            # Drafted rookies and their raw projections
            if add_df.empty:
                st.caption("No projected rookies drafted.")
            else:
                st.markdown("**Drafted rookies**")
                for _, p in add_df.sort_values(score_col, ascending=False).iterrows():
                    st.markdown(f"- {p['name']} ({p['position']}) · {p[score_col]:.0f} pts")

            # Per-slot +/- vs the manager's current veteran starters
            st.markdown("**Lineup change by slot**")
            for pos in ("QB", "RB", "WR", "TE"):
                ch = changes.get(pos, {})
                delta = ch.get("delta", 0.0)
                if ch.get("added_in"):
                    ins = ", ".join(f"{n} {p:.0f}" for n, p in ch["added_in"])
                    outs = (", ".join(f"{n} {p:.0f}" for n, p in ch["bumped_out"])
                            or "open slot")
                    st.markdown(f"- **{pos} {delta:+.0f}** — ↑ {ins} · ↓ {outs}")
                else:
                    st.markdown(f"- {pos} +0  ·  _no starter upgrade_")
                vets = ", ".join(f"{n} {p:.0f}" for n, p
                                 in ch.get("old_starters", [])) or "—"
                st.caption(f"current {pos} starters: {vets}")
