import altair as alt
import pandas as pd
import streamlit as st

from components.filters import apply_filters
from config import MERGED_PARQUET


def render():
    st.header("Ranking Comparison: FantasyCalc vs KeepTradeCut")
    st.caption("Superflex | PPR | 12-team")

    if not MERGED_PARQUET.exists():
        st.info("No data loaded. Click **Refresh Data** in the sidebar to get started.")
        return

    df = pd.read_parquet(MERGED_PARQUET)
    filtered = apply_filters(df)

    if filtered.empty:
        st.warning("No players match the current filters.")
        return

    matched = filtered[filtered["fc_rank"].notna() & filtered["ktc_rank"].notna()]

    # --- Sort mode toggle ---
    sort_mode = st.radio(
        "Sort by",
        ["Weighted (favors top players)", "Raw rank difference"],
        horizontal=True,
    )
    use_weighted = sort_mode.startswith("Weighted")
    sort_col = "rank_diff_weighted_abs" if use_weighted else "rank_diff_abs"
    diff_col = "rank_diff_weighted" if use_weighted else "rank_diff"

    # --- Summary metrics ---
    if not matched.empty:
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Players Compared", len(matched))

        if use_weighted:
            col2.metric("Avg Weighted Diff", f"{matched['rank_diff_weighted_abs'].mean():.2f}")
        else:
            col2.metric("Avg Rank Diff", f"{matched['rank_diff_abs'].mean():.1f}")

        # Biggest disagreements using current sort mode
        fc_lower_idx = matched[diff_col].idxmax()
        fc_lower = matched.loc[fc_lower_idx]
        if use_weighted:
            col3.metric(
                "FC Ranks Much Lower",
                fc_lower["name"],
                delta=f"{fc_lower['rank_diff_weighted']:.2f} (FC#{int(fc_lower['fc_rank'])} vs KTC#{int(fc_lower['ktc_rank'])})",
                delta_color="inverse",
            )
        else:
            col3.metric(
                "FC Ranks Much Lower",
                fc_lower["name"],
                delta=f"{int(fc_lower['rank_diff'])} ranks",
                delta_color="inverse",
            )

        ktc_lower_idx = matched[diff_col].idxmin()
        ktc_lower = matched.loc[ktc_lower_idx]
        if use_weighted:
            col4.metric(
                "FC Ranks Much Higher",
                ktc_lower["name"],
                delta=f"{ktc_lower['rank_diff_weighted']:.2f} (FC#{int(ktc_lower['fc_rank'])} vs KTC#{int(ktc_lower['ktc_rank'])})",
                delta_color="inverse",
            )
        else:
            col4.metric(
                "FC Ranks Much Higher",
                ktc_lower["name"],
                delta=f"{int(ktc_lower['rank_diff'])} ranks",
                delta_color="inverse",
            )

    # --- Scatter plot ---
    if not matched.empty:
        st.subheader("Rank Agreement")

        max_rank = max(matched["fc_rank"].max(), matched["ktc_rank"].max())
        diagonal = pd.DataFrame({"x": [1, max_rank], "y": [1, max_rank]})

        points = alt.Chart(matched).mark_circle(size=60, opacity=0.7).encode(
            x=alt.X("fc_rank:Q", title="FantasyCalc Rank", scale=alt.Scale(reverse=True)),
            y=alt.Y("ktc_rank:Q", title="KeepTradeCut Rank", scale=alt.Scale(reverse=True)),
            color=alt.Color("position:N", scale=alt.Scale(
                domain=["QB", "RB", "WR", "TE"],
                range=["#e41a1c", "#377eb8", "#4daf4a", "#ff7f00"],
            )),
            tooltip=["name", "position", "team", "fc_rank:Q", "ktc_rank:Q",
                      "rank_diff:Q", "rank_diff_weighted:Q"],
        )

        line = alt.Chart(diagonal).mark_line(
            strokeDash=[5, 5], color="gray", opacity=0.5
        ).encode(x="x:Q", y="y:Q")

        st.altair_chart(points + line, use_container_width=True)

    # --- Position tabs with data table ---
    tabs = st.tabs(["All"] + ["QB", "RB", "WR", "TE"])

    display_cols = [
        "name", "position", "team", "fc_rank", "ktc_rank", "rank_diff",
        "rank_diff_weighted",
        "fc_pos_rank", "ktc_pos_rank", "pos_rank_diff",
        "fc_value", "ktc_value", "fc_tier", "ktc_tier",
        "age", "is_rookie",
    ]
    available_cols = [c for c in display_cols if c in filtered.columns]

    for tab, pos_filter in zip(tabs, [None, "QB", "RB", "WR", "TE"]):
        with tab:
            tab_df = filtered if pos_filter is None else filtered[filtered["position"] == pos_filter]
            tab_df = tab_df.sort_values(sort_col, ascending=False, na_position="last")
            st.dataframe(
                tab_df[available_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "name": st.column_config.TextColumn("Player", width="medium"),
                    "position": st.column_config.TextColumn("Pos", width="small"),
                    "team": st.column_config.TextColumn("Team", width="small"),
                    "fc_rank": st.column_config.NumberColumn("FC#", format="%d"),
                    "ktc_rank": st.column_config.NumberColumn("KTC#", format="%d"),
                    "rank_diff": st.column_config.NumberColumn("Raw Diff", format="%d"),
                    "rank_diff_weighted": st.column_config.NumberColumn("Wtd Diff", format="%.2f"),
                    "fc_pos_rank": st.column_config.NumberColumn("FC Pos#", format="%d"),
                    "ktc_pos_rank": st.column_config.NumberColumn("KTC Pos#", format="%d"),
                    "pos_rank_diff": st.column_config.NumberColumn("Pos Diff", format="%d"),
                    "fc_value": st.column_config.NumberColumn("FC Val", format="%d"),
                    "ktc_value": st.column_config.NumberColumn("KTC Val", format="%d"),
                    "fc_tier": st.column_config.NumberColumn("FC Tier", format="%d"),
                    "ktc_tier": st.column_config.NumberColumn("KTC Tier", format="%d"),
                    "age": st.column_config.NumberColumn("Age", format="%.1f"),
                    "is_rookie": st.column_config.CheckboxColumn("Rookie"),
                },
            )

    # --- Disagreement bar charts ---
    if not matched.empty:
        st.subheader("Biggest Disagreements")
        col_left, col_right = st.columns(2)

        bar_label = "Weighted Diff" if use_weighted else "Rank Difference"
        bar_col = diff_col

        with col_left:
            st.markdown("**FC Ranks Higher** (KTC undervalues)")
            fc_higher_df = matched.nsmallest(15, diff_col)[["name", "position", bar_col]].copy()
            fc_higher_df["_abs"] = fc_higher_df[bar_col].abs()
            chart = alt.Chart(fc_higher_df).mark_bar(color="#377eb8").encode(
                x=alt.X("_abs:Q", title=bar_label),
                y=alt.Y("name:N", sort="-x", title=""),
                tooltip=["name", "position",
                          alt.Tooltip("_abs:Q", title=bar_label, format=".2f" if use_weighted else "d")],
            )
            st.altair_chart(chart, use_container_width=True)

        with col_right:
            st.markdown("**KTC Ranks Higher** (FC undervalues)")
            ktc_higher_df = matched.nlargest(15, diff_col)[["name", "position", bar_col]].copy()
            chart = alt.Chart(ktc_higher_df).mark_bar(color="#e41a1c").encode(
                x=alt.X(f"{bar_col}:Q", title=bar_label),
                y=alt.Y("name:N", sort="-x", title=""),
                tooltip=["name", "position",
                          alt.Tooltip(f"{bar_col}:Q", title=bar_label, format=".2f" if use_weighted else "d")],
            )
            st.altair_chart(chart, use_container_width=True)
