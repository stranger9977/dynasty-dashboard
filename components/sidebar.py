import os
from datetime import datetime

import streamlit as st

from config import DATA_DIR, FC_PARQUET, KTC_PARQUET, MERGED_PARQUET


def render_sidebar() -> str:
    st.sidebar.title("Dynasty Dashboard")

    tool = st.sidebar.radio("Tool", ["Ranking Comparison"], label_visibility="collapsed")

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

        status.update(label="Data refreshed!", state="complete")
