import streamlit as st
import pandas as pd

from config import POSITIONS


def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filters")

    # Position
    positions = st.sidebar.multiselect("Position", POSITIONS, default=POSITIONS)
    df = df[df["position"].isin(positions)]

    # Rookie / Veteran
    player_type = st.sidebar.radio("Player Type", ["All", "Rookies", "Veterans"])
    if player_type == "Rookies":
        df = df[df["is_rookie"] == True]
    elif player_type == "Veterans":
        df = df[df["is_rookie"] == False]

    # Only matched (both sources)
    matched_only = st.sidebar.checkbox("Both sources only", value=True)
    if matched_only:
        df = df[df["fc_rank"].notna() & df["ktc_rank"].notna()]

    # Min rank disagreement
    if len(df) > 0 and "rank_diff_abs" in df.columns:
        max_diff = int(df["rank_diff_abs"].max()) if df["rank_diff_abs"].notna().any() else 0
        if max_diff > 0:
            min_diff = st.sidebar.slider("Min rank disagreement", 0, max_diff, 0)
            if min_diff > 0:
                df = df[df["rank_diff_abs"] >= min_diff]

    # Tier filter
    tier_col = st.sidebar.selectbox("Tier source", ["FC Tier", "KTC Tier"])
    col = "fc_tier" if tier_col == "FC Tier" else "ktc_tier"
    if df[col].notna().any():
        tiers = sorted(df[col].dropna().unique().astype(int))
        if len(tiers) > 1:
            tier_range = st.sidebar.select_slider(
                "Tier range", options=tiers, value=(tiers[0], tiers[-1])
            )
            df = df[(df[col] >= tier_range[0]) & (df[col] <= tier_range[1])]

    # Team filter
    teams = sorted(df["team"].dropna().unique())
    selected_teams = st.sidebar.multiselect("Team", teams)
    if selected_teams:
        df = df[df["team"].isin(selected_teams)]

    # Name search
    search = st.sidebar.text_input("Search player")
    if search:
        df = df[df["name"].str.contains(search, case=False, na=False)]

    return df
