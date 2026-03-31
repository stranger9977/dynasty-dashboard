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

    tool = st.sidebar.radio("Tool", ["Ranking Comparison", "Waiver Wire", "Draft Wizard", "Trade History"], label_visibility="collapsed", key="selected_tool")

    st.sidebar.markdown("---")
    st.sidebar.subheader("Data")

    # Show last refresh time
    if MERGED_PARQUET.exists():
        mtime = os.path.getmtime(MERGED_PARQUET)
        ts = datetime.fromtimestamp(mtime).strftime("%b %d, %Y %I:%M %p")
        st.sidebar.caption(f"Last refresh: {ts}")
    else:
        st.sidebar.warning("No data yet — click Refresh Data")

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
