import os
from datetime import datetime

import streamlit as st

from config import DATA_DIR, FC_PARQUET, KTC_PARQUET, MERGED_PARQUET


def render_sidebar() -> str:
    st.sidebar.title("Dynasty Dashboard")

    # League switcher
    if "league_id" in st.session_state:
        from ingestion.sleeper import get_leagues, build_ownership_map

        st.sidebar.caption(f"_{st.session_state['sleeper_display_name']}_")

        # League selector — switch without disconnecting
        leagues = get_leagues(st.session_state["user_id"])
        league_map = {lg["name"]: lg for lg in leagues}
        current_name = st.session_state.get("league_name")

        # Find index of current league
        league_names = list(league_map.keys())
        current_idx = league_names.index(current_name) if current_name in league_names else 0

        selected_name = st.sidebar.selectbox(
            "League", league_names, index=current_idx, key="league_selector"
        )

        # Switch league if changed
        if selected_name != current_name:
            selected_league = league_map[selected_name]
            st.session_state["league_id"] = selected_league["league_id"]
            st.session_state["league_name"] = selected_league["name"]
            st.session_state["ownership_map"] = build_ownership_map(
                selected_league["league_id"]
            )
            st.rerun()

        if st.sidebar.button("Disconnect", use_container_width=True):
            for key in ["sleeper_username", "sleeper_display_name", "user_id",
                        "league_id", "league_name", "ownership_map", "leagues"]:
                st.session_state.pop(key, None)
            st.rerun()

        st.sidebar.markdown("---")

    tool = st.sidebar.radio(
        "Tool",
        ["Ranking Comparison", "Waiver Wire", "Draft Wizard", "Trade History",
         "Start/Sit History", "Waiver History", "Value Over Replacement", "Manager War"],
        label_visibility="collapsed",
        key="selected_tool",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Data")

    from config import FC_PARQUET, KTC_PARQUET, NFL_DRAFT_PARQUET, ADP_CSV
    from ingestion.lateround import LATEROUND_CSV

    def _fresh(path, label):
        if path.exists():
            ts = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%b %d %I:%M%p")
            try:
                import pandas as pd
                n = len(pd.read_parquet(path)) if str(path).endswith(".parquet") else len(pd.read_csv(path))
            except Exception:
                n = "?"
            st.sidebar.caption(f"{label}: {n} · {ts}")
        else:
            st.sidebar.caption(f"{label}: — (none)")

    _fresh(FC_PARQUET, "FantasyCalc")
    _fresh(KTC_PARQUET, "KeepTradeCut")
    _fresh(LATEROUND_CSV, "LateRound")
    _fresh(NFL_DRAFT_PARQUET, "NFL Draft")
    _fresh(ADP_CSV, "ADP")

    if st.sidebar.button("Refresh Data", use_container_width=True):
        _refresh_data()

    return tool


def _refresh_data():
    from ingestion.fantasycalc import fetch_fantasycalc
    from ingestion.ktc import fetch_ktc
    from ingestion.matching import merge_rankings

    DATA_DIR.mkdir(exist_ok=True)

    with st.sidebar.status("Refreshing data...", expanded=True) as status:
        st.write("Fetching FantasyCalc...")
        fc = fetch_fantasycalc()
        fc.to_parquet(FC_PARQUET, index=False)
        st.write(f"FantasyCalc: {len(fc)} players")

        st.write("Fetching KeepTradeCut...")
        kt = fetch_ktc()
        kt.to_parquet(KTC_PARQUET, index=False)
        st.write(f"KeepTradeCut: {len(kt)} players")

        st.write("Fetching NFL draft capital...")
        try:
            from ingestion.nfl_draft import fetch_nfl_draft
            from config import NFL_DRAFT_PARQUET
            nd = fetch_nfl_draft()
            nd.to_parquet(NFL_DRAFT_PARQUET, index=False)
            st.write(f"NFL draft: {len(nd)} skill picks")
        except Exception as e:
            st.write(f"NFL draft fetch failed — keeping existing ({e})")

        st.write("Matching players...")
        merged = merge_rankings(fc, kt)
        merged.to_parquet(MERGED_PARQUET, index=False)
        both = merged[merged["fc_rank"].notna() & merged["ktc_rank"].notna()]
        st.write(f"Matched: {len(both)} players")

        # Refresh ownership if league connected
        if "league_id" in st.session_state:
            from ingestion.sleeper import build_ownership_map
            st.write("Refreshing rosters...")
            st.session_state["ownership_map"] = build_ownership_map(
                st.session_state["league_id"]
            )

        status.update(label="Data refreshed!", state="complete")
