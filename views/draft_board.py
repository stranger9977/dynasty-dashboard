# views/draft_board.py
"""Shared rookie render helpers reused by the live Draft Board and the mock."""
import pandas as pd
import streamlit as st

from config import POSITIONS

POS_COLORS = {"QB": "#e41a1c", "RB": "#377eb8", "WR": "#4daf4a", "TE": "#ff7f00"}

BOARD_COLS = ["name", "position", "team", "blended_rank", "adp_rank",
              "draft_skill_rank", "lr_rank", "fc_rookie_rank", "ktc_rookie_rank",
              "rank_spread", "age", "college"]

DISAGREE_COLS = ["name", "position", "team", "blended_rank", "lr_rank", "fc_rookie_rank",
                 "ktc_rookie_rank", "draft_skill_rank", "adp_rank", "rank_spread",
                 "source_high", "source_low"]


def _fmt(v, spec="{:.0f}"):
    return spec.format(v) if pd.notna(v) else "—"


def _board_col_config():
    n = st.column_config.NumberColumn
    return {
        "name": st.column_config.TextColumn("Player", width="medium"),
        "position": st.column_config.TextColumn("Pos", width="small"),
        "team": st.column_config.TextColumn("Tm", width="small"),
        "blended_rank": n("Blend#", format="%.1f"),
        "adp_rank": n("ADP#", format="%d"),
        "draft_skill_rank": n("Draft#", format="%d"),
        "lr_rank": n("LR#", format="%d"),
        "fc_rookie_rank": n("FC#", format="%d"),
        "ktc_rookie_rank": n("KTC#", format="%d"),
        "rank_spread": n("Spread", format="%.0f"),
        "age": n("Age", format="%.1f"),
        "source_high": st.column_config.TextColumn("Bull"),
        "source_low": st.column_config.TextColumn("Bear"),
        "college": st.column_config.TextColumn("College"),
    }


def _card_html(p: pd.Series) -> str:
    """One best-available card as an HTML string sized to flex/wrap responsively."""
    color = POS_COLORS.get(p["position"], "#666")
    age = f"{p['age']:.1f}" if pd.notna(p.get("age")) else "—"
    draft = f"{_fmt(p.get('draft_skill_rank'))} (pk {_fmt(p.get('draft_overall_pick'))})"
    note = ""
    if pd.notna(p.get("source_high")) and pd.notna(p.get("source_low")):
        note = f"{p['source_high']} loves / {p['source_low']} fades"
    return (
        f"<div style='flex:1 1 240px;border:1px solid #444;border-left:5px solid {color};"
        f"border-radius:8px;padding:8px 10px;background:#1a1a2e'>"
        f"<div style='font-weight:bold'>{p['name']}</div>"
        f"<div style='font-size:0.72em;color:#aaa'>{p['position']} · {p.get('team','')} · "
        f"age {age} · {p.get('college','') or ''}</div>"
        f"<div style='font-size:0.8em;margin-top:4px'>Blend <b>{_fmt(p.get('blended_rank'),'{:.1f}')}</b>"
        f" · ADP {_fmt(p.get('adp_rank'))} · Draft {draft}</div>"
        f"<div style='font-size:0.74em;color:#bbb'>LR {_fmt(p.get('lr_rank'))} · "
        f"FC {_fmt(p.get('fc_rookie_rank'))} · KTC {_fmt(p.get('ktc_rookie_rank'))} · "
        f"spread {_fmt(p.get('rank_spread'))}</div>"
        f"<div style='font-size:0.68em;color:#888'>{note}</div>"
        f"</div>"
    )


def render_best_available_cards(available: pd.DataFrame, rank_col: str, top_n: int = 2):
    st.markdown("#### Best Available by Position")
    for pos in POSITIONS:
        pool = available[available["position"] == pos].sort_values(rank_col).head(top_n)
        if pool.empty:
            continue
        # One flex-wrap row per position: cards stack 1-up on phones, multi-up on
        # wider screens (flex-basis 240px), so it reads well on mobile.
        cards = "".join(_card_html(p) for _, p in pool.iterrows())
        st.markdown(
            f"<div style='font-size:0.8em;color:#9aa;margin:8px 0 2px'>{pos}</div>"
            f"<div style='display:flex;flex-wrap:wrap;gap:8px'>{cards}</div>",
            unsafe_allow_html=True,
        )


def render_sortable_board(rookies: pd.DataFrame):
    cols = [c for c in BOARD_COLS if c in rookies.columns]
    st.dataframe(rookies[cols], use_container_width=True, hide_index=True,
                 column_config=_board_col_config())


def render_disagreements(rookies: pd.DataFrame, n: int = 15):
    st.markdown("#### Biggest Disagreements")
    st.caption("Sorted by spread across LR / FC / KTC / Draft / ADP — value or trap")
    if "rank_spread" not in rookies.columns:
        st.info("Disagreement spread unavailable.")
        return
    d = rookies[rookies["rank_spread"].notna()].sort_values("rank_spread", ascending=False).head(n)
    cols = [c for c in DISAGREE_COLS if c in d.columns]
    st.dataframe(d[cols], use_container_width=True, hide_index=True,
                 column_config=_board_col_config())
