import altair as alt
import pandas as pd
import streamlit as st

from components.filters import apply_filters
from config import MERGED_PARQUET

SOURCES = {
    "FantasyCalc": {"rank": "fc_rank", "value": "fc_value", "tier": "fc_tier", "pos_rank": "fc_pos_rank", "short": "FC"},
    "KeepTradeCut": {"rank": "ktc_rank", "value": "ktc_value", "tier": "ktc_tier", "pos_rank": "ktc_pos_rank", "short": "KTC"},
    "LateRound": {"rank": "lr_rank", "value": None, "tier": "lr_tier", "pos_rank": "lr_pos_rank", "short": "LR"},
}


def render():
    st.header("Ranking Comparison")
    st.caption("Superflex | PPR | 12-team")

    if not MERGED_PARQUET.exists():
        st.info("No data loaded. Click **Refresh Data** in the sidebar to get started.")
        return

    df = pd.read_parquet(MERGED_PARQUET)

    # Merge LateRound rankings for rookies
    from ingestion.lateround import load_lateround, merge_lateround
    lr = load_lateround()
    if not lr.empty:
        rookies = df[df["is_rookie"] == True].copy()
        rookies = merge_lateround(rookies, lr)
        # Write LR columns back onto df
        for col in ["lr_rank", "lr_pos_rank", "lr_tier"]:
            if col in rookies.columns:
                df[col] = None
                df.loc[rookies.index, col] = rookies[col]

    # Annotate with ownership if league connected
    if "ownership_map" in st.session_state:
        from ingestion.ownership import annotate_ownership
        df = annotate_ownership(df, st.session_state["ownership_map"])

    # --- Source selection ---
    available_sources = list(SOURCES.keys())
    # Only show LateRound if data exists
    if "lr_rank" not in df.columns or df["lr_rank"].notna().sum() == 0:
        available_sources = [s for s in available_sources if s != "LateRound"]

    col_a, col_b = st.columns(2)
    with col_a:
        source_a = st.selectbox("Source A", available_sources, index=0, key="cmp_source_a")
    with col_b:
        default_b = 1 if len(available_sources) > 1 else 0
        source_b = st.selectbox("Source B", available_sources, index=default_b, key="cmp_source_b")

    sa = SOURCES[source_a]
    sb = SOURCES[source_b]
    rank_a, rank_b = sa["rank"], sb["rank"]
    short_a, short_b = sa["short"], sb["short"]

    filtered = apply_filters(df)

    if filtered.empty:
        st.warning("No players match the current filters.")
        return

    # Compute comparison columns on the fly
    matched = filtered[filtered[rank_a].notna() & filtered[rank_b].notna()].copy()
    if not matched.empty:
        matched["rank_diff"] = matched[rank_a] - matched[rank_b]
        matched["rank_diff_abs"] = matched["rank_diff"].abs()
        matched["avg_rank"] = (matched[rank_a] + matched[rank_b]) / 2
        matched["rank_diff_weighted"] = matched["rank_diff"] / matched["avg_rank"]
        matched["rank_diff_weighted_abs"] = matched["rank_diff_weighted"].abs()

    # Also add to filtered for table display
    filtered = filtered.copy()
    filtered["rank_diff"] = filtered[rank_a] - filtered[rank_b]
    filtered["rank_diff_abs"] = filtered["rank_diff"].abs()
    avg = (filtered[rank_a] + filtered[rank_b]) / 2
    filtered["rank_diff_weighted"] = filtered["rank_diff"] / avg
    filtered["rank_diff_weighted_abs"] = filtered["rank_diff_weighted"].abs()

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

        a_lower_idx = matched[diff_col].idxmax()
        a_lower = matched.loc[a_lower_idx]
        col3.metric(
            f"{short_a} Ranks Much Lower",
            a_lower["name"],
            delta=f"{a_lower[diff_col]:.2f}" if use_weighted else f"{int(a_lower['rank_diff'])} ranks",
            delta_color="inverse",
        )

        b_lower_idx = matched[diff_col].idxmin()
        b_lower = matched.loc[b_lower_idx]
        col4.metric(
            f"{short_a} Ranks Much Higher",
            b_lower["name"],
            delta=f"{b_lower[diff_col]:.2f}" if use_weighted else f"{int(b_lower['rank_diff'])} ranks",
            delta_color="inverse",
        )

    # --- Scatter plot ---
    if not matched.empty:
        st.subheader("Rank Agreement")

        max_rank = max(matched[rank_a].max(), matched[rank_b].max())
        diagonal = pd.DataFrame({"x": [1, max_rank], "y": [1, max_rank]})

        points = alt.Chart(matched).mark_circle(size=60, opacity=0.7).encode(
            x=alt.X(f"{rank_a}:Q", title=f"{source_a} Rank", scale=alt.Scale(reverse=True)),
            y=alt.Y(f"{rank_b}:Q", title=f"{source_b} Rank", scale=alt.Scale(reverse=True)),
            color=alt.Color("position:N", scale=alt.Scale(
                domain=["QB", "RB", "WR", "TE"],
                range=["#e41a1c", "#377eb8", "#4daf4a", "#ff7f00"],
            )),
            tooltip=["name", "position", "team", f"{rank_a}:Q", f"{rank_b}:Q",
                      "rank_diff:Q", "rank_diff_weighted:Q"]
                     + (["owner"] if "owner" in matched.columns else []),
        )

        line = alt.Chart(diagonal).mark_line(
            strokeDash=[5, 5], color="gray", opacity=0.5
        ).encode(x="x:Q", y="y:Q")

        st.altair_chart(points + line, use_container_width=True)

    # --- Position tabs with data table ---
    tabs = st.tabs(["All"] + ["QB", "RB", "WR", "TE"])

    display_cols = [
        "name", "owner", "position", "team", rank_a, rank_b, "rank_diff",
        "rank_diff_weighted",
        sa.get("pos_rank"), sb.get("pos_rank"),
        sa.get("value"), sb.get("value"),
        sa.get("tier"), sb.get("tier"),
        "age", "is_rookie",
    ]
    display_cols = [c for c in display_cols if c is not None]
    available_cols = [c for c in display_cols if c in filtered.columns]

    col_config = {
        "name": st.column_config.TextColumn("Player", width="medium"),
        "owner": st.column_config.TextColumn("Owner", width="medium"),
        "position": st.column_config.TextColumn("Pos", width="small"),
        "team": st.column_config.TextColumn("Team", width="small"),
        rank_a: st.column_config.NumberColumn(f"{short_a}#", format="%d"),
        rank_b: st.column_config.NumberColumn(f"{short_b}#", format="%d"),
        "rank_diff": st.column_config.NumberColumn("Raw Diff", format="%d"),
        "rank_diff_weighted": st.column_config.NumberColumn("Wtd Diff", format="%.2f"),
        "fc_pos_rank": st.column_config.NumberColumn("FC Pos#", format="%d"),
        "ktc_pos_rank": st.column_config.NumberColumn("KTC Pos#", format="%d"),
        "lr_pos_rank": st.column_config.NumberColumn("LR Pos#", format="%d"),
        "fc_value": st.column_config.NumberColumn("FC Val", format="%d"),
        "ktc_value": st.column_config.NumberColumn("KTC Val", format="%d"),
        "fc_tier": st.column_config.NumberColumn("FC Tier", format="%d"),
        "ktc_tier": st.column_config.NumberColumn("KTC Tier", format="%d"),
        "lr_tier": st.column_config.NumberColumn("LR Tier", format="%d"),
        "age": st.column_config.NumberColumn("Age", format="%.1f"),
        "is_rookie": st.column_config.CheckboxColumn("Rookie"),
    }

    for tab, pos_filter in zip(tabs, [None, "QB", "RB", "WR", "TE"]):
        with tab:
            tab_df = filtered if pos_filter is None else filtered[filtered["position"] == pos_filter]
            tab_df = tab_df.sort_values(sort_col, ascending=False, na_position="last")
            st.dataframe(
                tab_df[available_cols],
                use_container_width=True,
                hide_index=True,
                column_config=col_config,
            )

    # --- Disagreement bar charts ---
    if not matched.empty:
        st.subheader("Biggest Disagreements")
        col_left, col_right = st.columns(2)

        bar_label = "Weighted Diff" if use_weighted else "Rank Difference"

        with col_left:
            st.markdown(f"**{short_a} Ranks Higher** ({short_b} undervalues)")
            higher_df = matched.nsmallest(15, diff_col)[["name", "position", diff_col]].copy()
            higher_df["_abs"] = higher_df[diff_col].abs()
            chart = alt.Chart(higher_df).mark_bar(color="#377eb8").encode(
                x=alt.X("_abs:Q", title=bar_label),
                y=alt.Y("name:N", sort="-x", title=""),
                tooltip=["name", "position",
                          alt.Tooltip("_abs:Q", title=bar_label, format=".2f" if use_weighted else "d")],
            )
            st.altair_chart(chart, use_container_width=True)

        with col_right:
            st.markdown(f"**{short_b} Ranks Higher** ({short_a} undervalues)")
            lower_df = matched.nlargest(15, diff_col)[["name", "position", diff_col]].copy()
            chart = alt.Chart(lower_df).mark_bar(color="#e41a1c").encode(
                x=alt.X(f"{diff_col}:Q", title=bar_label),
                y=alt.Y("name:N", sort="-x", title=""),
                tooltip=["name", "position",
                          alt.Tooltip(f"{diff_col}:Q", title=bar_label, format=".2f" if use_weighted else "d")],
            )
            st.altair_chart(chart, use_container_width=True)
