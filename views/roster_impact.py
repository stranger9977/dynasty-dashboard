# views/roster_impact.py
"""Roster Impact tab: 2026 projected points each manager's rookie haul adds to their
roster — total, and the marginal upgrade to their starting lineup. See Phase B design."""
import pandas as pd
import streamlit as st

from config import STARTER_COUNTS
from ingestion.match_util import normalize_name
from ingestion.roster_impact import starter_points, points_above_starters, lineup_changes

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

    # Current rosters (all managers), keyed by manager — used by the starter
    # leaderboard and as draft baselines.
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

    # --- Projected Starter Leaderboard (current rosters, draft-independent) ---
    if roster_ids:
        st.markdown("#### 📊 Projected Starter Leaderboard")
        st.caption(f"Highest projected starting lineups today — best "
                   f"{STARTER_COUNTS['QB']} QB / {STARTER_COUNTS['RB']} RB / "
                   f"{STARTER_COUNTS['WR']} WR / {STARTER_COUNTS['TE']} TE · "
                   f"scoring {score_label}")
        sl_rows = []
        for mgr, ids in roster_ids.items():
            rf = _frame(list(ids))
            row = {"Manager": mgr}
            for pos in ("QB", "RB", "WR", "TE"):
                row[pos] = round(starter_points(rf, {pos: STARTER_COUNTS[pos]}, score_col), 1)
            row["Total"] = round(starter_points(rf, STARTER_COUNTS, score_col), 1)
            sl_rows.append(row)
        sl = (pd.DataFrame(sl_rows).sort_values("Total", ascending=False)
              .reset_index(drop=True))
        sl.index = sl.index + 1
        st.dataframe(sl, use_container_width=True, column_config={
            c: st.column_config.NumberColumn(c, format="%.0f")
            for c in ("QB", "RB", "WR", "TE", "Total")
        })
        st.markdown("---")

    # --- Draft impact (needs picks) ---
    drafted = _collect_drafted(rookies, draft, league_id)
    if not drafted:
        st.info("No draft picks yet — start your live draft or run a mock in the "
                "Mock Draft Simulator to see draft impact.")
        return

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

    # --- Top-10 individual lineup upgrades across the league ---
    st.markdown("---")
    st.markdown("#### 🏆 Top 10 individual upgrades")
    ups = []
    for mgr in summary.index:
        for pos, ch in per_mgr[mgr]["changes"].items():
            for u in ch.get("upgrades", []):
                if u["gain"] <= 0:
                    continue
                ups.append({
                    "Manager": mgr,
                    "Slot": pos,
                    "Added (↑)": f"{u['player']} {u['pts']:.0f}",
                    "Replaced (↓)": (f"{u['replaced']} {u['replaced_pts']:.0f}"
                                     if u["replaced"] else "open slot"),
                    "Upgrade": round(u["gain"], 1),
                })
    if ups:
        lb = (pd.DataFrame(ups).sort_values("Upgrade", ascending=False)
              .head(10).reset_index(drop=True))
        lb.index = lb.index + 1
        st.dataframe(
            lb, use_container_width=True,
            column_config={"Upgrade": st.column_config.NumberColumn("Upgrade", format="%.1f")},
        )
    else:
        st.caption("No starting-lineup upgrades yet.")

    # --- Per-manager slot tables ---
    st.markdown("---")
    st.caption("Expand a manager for their per-slot change (↑ added / ↓ bumped) and "
               "current veteran starters.")
    for mgr in summary.index:
        d = per_mgr[mgr]
        add_df, changes = d["add_df"], d["changes"]
        head = (f"{mgr} — +{summary.loc[mgr, 'above_starters']:.0f} above starters · "
                f"{summary.loc[mgr, 'total_added']:.0f} total")
        with st.expander(head):
            if add_df.empty:
                st.caption("No projected rookies drafted.")
            else:
                st.markdown("**Drafted rookies**")
                for _, p in add_df.sort_values(score_col, ascending=False).iterrows():
                    st.markdown(f"- {p['name']} ({p['position']}) · {p[score_col]:.0f} pts")

            st.markdown("**Lineup change by slot**")
            slot_rows = []
            for pos in ("QB", "RB", "WR", "TE"):
                ch = changes.get(pos, {})
                added = ", ".join(f"{n} {p:.0f}" for n, p in ch.get("added_in", [])) or "—"
                bumped = ", ".join(f"{n} {p:.0f}" for n, p in ch.get("bumped_out", []))
                if not bumped:
                    bumped = "open slot" if ch.get("added_in") else "—"
                starters = ", ".join(f"{n} {p:.0f}" for n, p
                                     in ch.get("old_starters", [])) or "—"
                slot_rows.append({
                    "Slot": pos,
                    "Δ": f"{ch.get('delta', 0.0):+.0f}",
                    "Added ↑": added,
                    "Bumped ↓": bumped,
                    "Current starters": starters,
                })
            st.table(pd.DataFrame(slot_rows).set_index("Slot"))
