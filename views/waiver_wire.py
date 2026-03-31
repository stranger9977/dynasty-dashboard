import altair as alt
import pandas as pd
import streamlit as st

from config import MERGED_PARQUET, POSITIONS

RANK_SOURCES = {
    "Blended (avg)": ("blended_rank", "Rank"),
    "FantasyCalc": ("fc_rank", "FC#"),
    "KeepTradeCut": ("ktc_rank", "KTC#"),
}


def render():
    st.header("Waiver Wire")
    st.caption("Best available unrostered players by position")

    if not MERGED_PARQUET.exists():
        st.info("No data loaded. Click **Refresh Data** in the sidebar to get started.")
        return

    if "ownership_map" not in st.session_state:
        st.info("Connect a Sleeper league to see waiver wire availability.")
        return

    df = pd.read_parquet(MERGED_PARQUET)

    # Annotate ownership
    from ingestion.ownership import annotate_ownership
    df = annotate_ownership(df, st.session_state["ownership_map"])

    # --- Ranking source toggle ---
    source_label = st.radio(
        "Rank by", list(RANK_SOURCES.keys()), horizontal=True, key="ww_source"
    )
    rank_col, rank_display = RANK_SOURCES[source_label]

    # Waiver wire = Free Agents only (not incoming rookies, not rostered)
    fa = df[df["owner"] == "Free Agent"].copy()

    # Require the selected ranking source to be present
    fa = fa[fa[rank_col].notna()]
    fa = fa.sort_values(rank_col, na_position="last").reset_index(drop=True)

    # --- Summary ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Available Players", len(fa))
    for i, pos in enumerate(POSITIONS):
        [col2, col3, col4, col1][i].metric(f"Available {pos}s", len(fa[fa["position"] == pos]))

    # --- Filters ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Waiver Filters")

    positions = st.sidebar.multiselect("Position", POSITIONS, default=POSITIONS, key="ww_pos")
    fa = fa[fa["position"].isin(positions)]

    search = st.sidebar.text_input("Search player", key="ww_search")
    if search:
        fa = fa[fa["name"].str.contains(search, case=False, na=False)]

    if fa.empty:
        st.warning("No free agents match the current filters.")
        return

    # --- Position tabs ---
    tabs = st.tabs(["All"] + POSITIONS)

    display_cols = [
        "name", "position", "team", rank_col,
        "fc_rank", "ktc_rank", "fc_value", "ktc_value",
        "fc_tier", "ktc_tier", "age", "years_exp",
    ]
    # Deduplicate if rank_col is already fc_rank or ktc_rank
    display_cols = list(dict.fromkeys(display_cols))
    available_cols = [c for c in display_cols if c in fa.columns]

    col_config = {
        "name": st.column_config.TextColumn("Player", width="medium"),
        "position": st.column_config.TextColumn("Pos", width="small"),
        "team": st.column_config.TextColumn("Team", width="small"),
        "blended_rank": st.column_config.NumberColumn("Rank", format="%.0f"),
        "fc_rank": st.column_config.NumberColumn("FC#", format="%d"),
        "ktc_rank": st.column_config.NumberColumn("KTC#", format="%d"),
        "fc_value": st.column_config.NumberColumn("FC Val", format="%d"),
        "ktc_value": st.column_config.NumberColumn("KTC Val", format="%d"),
        "fc_tier": st.column_config.NumberColumn("FC Tier", format="%d"),
        "ktc_tier": st.column_config.NumberColumn("KTC Tier", format="%d"),
        "age": st.column_config.NumberColumn("Age", format="%.1f"),
        "years_exp": st.column_config.NumberColumn("Exp", format="%d"),
    }

    for tab, pos_filter in zip(tabs, [None] + POSITIONS):
        with tab:
            tab_df = fa if pos_filter is None else fa[fa["position"] == pos_filter]
            tab_df = tab_df.sort_values(rank_col)
            st.dataframe(
                tab_df[available_cols],
                use_container_width=True,
                hide_index=True,
                column_config=col_config,
            )

    # --- Upgrade opportunities: compare FA to your roster ---
    my_name = st.session_state.get("sleeper_display_name")
    if my_name:
        my_team = df[df["owner"] == my_name].copy()
        my_team = my_team[my_team[rank_col].notna()]

        if not my_team.empty:
            st.subheader("Upgrade Opportunities")
            st.caption(f"Free agents ranked higher than your worst player at each position (by {source_label})")

            for pos in positions:
                my_pos = my_team[my_team["position"] == pos].sort_values(rank_col)
                fa_pos = fa[fa["position"] == pos].sort_values(rank_col)

                if my_pos.empty or fa_pos.empty:
                    continue

                worst_rank = my_pos[rank_col].max()
                upgrades = fa_pos[fa_pos[rank_col] < worst_rank]

                if upgrades.empty:
                    continue

                with st.expander(
                    f"**{pos}** — {len(upgrades)} available ranked above your {pos}{len(my_pos)}",
                    expanded=True,
                ):
                    compare_cols = ["name", "team", rank_col, "fc_rank", "ktc_rank",
                                    "fc_value", "ktc_value", "age"]
                    compare_cols = list(dict.fromkeys(compare_cols))
                    avail_compare = [c for c in compare_cols if c in fa.columns]

                    col_left, col_right = st.columns(2)
                    with col_left:
                        st.markdown("**Best Available**")
                        st.dataframe(
                            upgrades[avail_compare].head(5),
                            use_container_width=True, hide_index=True,
                            column_config=col_config,
                        )
                    with col_right:
                        st.markdown("**Your Worst Rostered**")
                        st.dataframe(
                            my_pos[avail_compare].tail(5).sort_values(rank_col, ascending=False),
                            use_container_width=True, hide_index=True,
                            column_config=col_config,
                        )

    # --- Top available by position chart ---
    st.subheader("Top Available by Position")
    top_n = st.slider("Players per position", 5, 20, 10, key="ww_top_n")

    chart_data = []
    for pos in positions:
        pos_df = fa[fa["position"] == pos].head(top_n)
        chart_data.append(pos_df)

    if chart_data:
        chart_df = pd.concat(chart_data)
        chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X(f"{rank_col}:Q", title=rank_display, scale=alt.Scale(reverse=True)),
            y=alt.Y("name:N", sort=alt.EncodingSortField(field=rank_col, order="ascending"), title=""),
            color=alt.Color("position:N", scale=alt.Scale(
                domain=["QB", "RB", "WR", "TE"],
                range=["#e41a1c", "#377eb8", "#4daf4a", "#ff7f00"],
            )),
            tooltip=["name", "position", "team", f"{rank_col}:Q", "fc_rank:Q", "ktc_rank:Q", "age:Q"],
            row=alt.Row("position:N", title="", sort=POSITIONS),
        ).properties(height=alt.Step(20)).resolve_scale(y="independent")

        st.altair_chart(chart, use_container_width=True)
