# views/draft_value.py
"""Draft Value Recap tab: surplus-vs-slot charts, reach/steal cards, and manager
chips driven by the live Sleeper draft (mock fallback). See the Phase A design doc."""
import pandas as pd
import streamlit as st

from ingestion.draft_value import (
    RAW_SOURCE_COLS, half_life_to_lambda, consensus_rank,
    build_pick_values, summarize_managers,
)
from ingestion.match_util import normalize_name

SOURCE_KEYS = ["lr", "fc", "ktc", "draft", "adp"]
SOURCE_LABELS = {"lr": "LR", "fc": "FC", "ktc": "KTC", "draft": "Draft", "adp": "ADP"}


def _rookie_lookup(rookies: pd.DataFrame):
    """(by_id, by_name) dicts mapping sleeper_id / normalized name -> rookie row dict."""
    by_id, by_name = {}, {}
    for _, r in rookies.iterrows():
        rec = r.to_dict()
        if pd.notna(r.get("sleeper_id")):
            by_id[str(r["sleeper_id"])] = rec
        by_name[normalize_name(str(r["name"]))] = rec
    return by_id, by_name


def _source_ranks_from_row(row: dict | None) -> dict:
    """Pull the five raw per-source ranks from a matched rookie row (None if absent)."""
    out = {}
    for k in SOURCE_KEYS:
        v = row.get(RAW_SOURCE_COLS[k]) if row else None
        out[k] = float(v) if (v is not None and pd.notna(v)) else None
    return out


def _collect_live_picks(rookies, draft, league_id):
    """Picks from the live Sleeper draft -> list of row dicts (or [] if none/error)."""
    from ingestion.sleeper import get_draft_picks, build_roster_to_manager
    try:
        picks = get_draft_picks(draft["draft_id"])
    except Exception:
        return []
    if not picks:
        return []
    roster_to_mgr = build_roster_to_manager(league_id) if league_id else {}
    by_id, by_name = _rookie_lookup(rookies)
    rows = []
    for pk in picks:
        md = pk.get("metadata") or {}
        nm = f"{md.get('first_name', '')} {md.get('last_name', '')}".strip()
        row = None
        if pk.get("player_id") and str(pk["player_id"]) in by_id:
            row = by_id[str(pk["player_id"])]
        elif nm:
            row = by_name.get(normalize_name(nm))
        rows.append({
            "manager": roster_to_mgr.get(pk.get("roster_id"), f"Team {pk.get('roster_id')}"),
            "player": (row or {}).get("name") or nm or "?",
            "position": (row or {}).get("position") or md.get("position") or "",
            "pick_no": pk.get("pick_no"),
            **_source_ranks_from_row(row),
        })
    return rows


def _collect_mock_picks(rookies):
    """Picks from the most recent in-session mock -> list of row dicts (or [])."""
    picks = st.session_state.get("draft_picks") or []
    if not picks:
        return []
    _, by_name = _rookie_lookup(rookies)
    rows = []
    for p in picks:
        row = by_name.get(normalize_name(str(p.get("player", ""))))
        rows.append({
            "manager": p.get("owner", "?"),
            "player": p.get("player", "?"),
            "position": p.get("player_pos") or (row or {}).get("position") or "",
            "pick_no": p.get("pick"),
            **_source_ranks_from_row(row),
        })
    return rows


def _pick_card_html(title, row, color):
    pos = row.get("position", "")
    rank = row.get("consensus_rank")
    rstr = f"{rank:.1f}" if pd.notna(rank) else "—"
    return (
        f"<div style='border:1px solid #444;border-left:5px solid {color};"
        f"border-radius:8px;padding:10px 12px;background:#1a1a2e'>"
        f"<div style='font-size:0.8em;color:#aaa'>{title}</div>"
        f"<div style='font-size:1.1em;font-weight:bold'>{row['player']} "
        f"<span style='color:#888;font-size:0.7em'>{pos}</span></div>"
        f"<div style='font-size:0.8em;color:#bbb'>{row['manager']} · "
        f"pick {row['pick_no']:.0f} · consensus {rstr}</div>"
        f"<div style='font-size:0.95em;color:{color}'>surplus {row['surplus']:+.0f}</div>"
        f"</div>"
    )


def _chip_html(title, manager, detail, color, avatar_url=None):
    """avatar_url is the deferred-avatar seam (Phase A leaves it None)."""
    avatar = (
        f"<img src='{avatar_url}' style='width:30px;height:30px;border-radius:50%;"
        f"margin-right:8px'>" if avatar_url else ""
    )
    return (
        f"<div style='display:flex;align-items:center;border:1px solid {color};"
        f"border-radius:16px;padding:8px 14px;background:#1a1a2e'>{avatar}"
        f"<div><div style='font-weight:bold;color:{color};font-size:0.85em'>{title}</div>"
        f"<div style='font-size:0.95em'>{manager}</div>"
        f"<div style='font-size:0.72em;color:#999'>{detail}</div></div></div>"
    )


def render_draft_value_recap(rookies, draft, league_id):
    st.subheader("Draft Recap — Value by Manager")

    rows, source_label = [], "live draft"
    if draft and draft.get("draft_id"):
        rows = _collect_live_picks(rookies, draft, league_id)
    if not rows:
        rows = _collect_mock_picks(rookies)
        source_label = "last mock"
    if not rows:
        st.info("No draft picks yet — start your live draft or run a mock "
                "in the Mock Draft Simulator to see the recap.")
        return

    picks_df = pd.DataFrame(rows)
    picks_df = picks_df[picks_df["pick_no"].notna()].copy()
    if picks_df.empty:
        st.info("No completed picks yet.")
        return

    st.caption(f"Based on the {source_label} · {len(picks_df)} picks · "
               "surplus = value of player taken − value of the slot used")

    # --- Controls: source toggles + decay half-life ---
    cols = st.columns(len(SOURCE_KEYS))
    active = set()
    for col, k in zip(cols, SOURCE_KEYS):
        if col.checkbox(SOURCE_LABELS[k], value=True, key=f"dvr_src_{k}"):
            active.add(k)
    if not active:
        st.warning("Select at least one ranking source.")
        return
    half_life = st.slider("Value half-life (picks)", 2, 15, 6, key="dvr_hl",
                          help="How fast pick value decays — lower means early "
                               "picks matter much more.")
    lam = half_life_to_lambda(half_life)

    # --- Math ---
    picks_df["consensus_rank"] = picks_df.apply(
        lambda r: consensus_rank({k: r[k] for k in SOURCE_KEYS}, active), axis=1)
    pv = build_pick_values(picks_df, lam, max_rank=len(rookies))
    summary = summarize_managers(pv)

    # --- Two charts side by side (stack on mobile) ---
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Total value vs slot**")
        st.bar_chart(summary["total_surplus"])
    with c2:
        st.markdown("**Value per pick**")
        st.bar_chart(summary["surplus_per_pick"])

    # --- Reach / Steal cards ---
    st.markdown("---")
    steal = pv.loc[pv["surplus"].idxmax()]
    reach = pv.loc[pv["surplus"].idxmin()]
    rc1, rc2 = st.columns(2)
    with rc1:
        st.markdown(_pick_card_html("💎 Biggest Steal", steal, "#4daf4a"),
                    unsafe_allow_html=True)
    with rc2:
        st.markdown(_pick_card_html("🧨 Biggest Reach", reach, "#e41a1c"),
                    unsafe_allow_html=True)

    # --- Manager chips ---
    st.markdown("---")
    hog = summary.index[0]       # highest total surplus
    guys = summary.index[-1]     # lowest total surplus
    hog_pick = pv[pv["manager"] == hog].sort_values("surplus", ascending=False).iloc[0]
    guys_pick = pv[pv["manager"] == guys].sort_values("surplus").iloc[0]
    ch1, ch2 = st.columns(2)
    with ch1:
        st.markdown(_chip_html(
            "🐷 Value Hog", hog,
            f"+{summary.loc[hog, 'total_surplus']:.0f} total · "
            f"best: {hog_pick['player']} ({hog_pick['surplus']:+.0f})",
            "#4daf4a"), unsafe_allow_html=True)
    with ch2:
        st.markdown(_chip_html(
            "🎯 Gets His Guys — no matter what", guys,
            f"{summary.loc[guys, 'total_surplus']:.0f} total · "
            f"reach: {guys_pick['player']} ({guys_pick['surplus']:+.0f})",
            "#e41a1c"), unsafe_allow_html=True)
