# views/charts.py
"""Shared chart helpers for the Draft Wizard views."""
import altair as alt
import streamlit as st


def hbar(series, value_title: str, color: str = "#4daf4a"):
    """Horizontal bar chart with bars sorted high-to-low by value.

    series: a pandas Series indexed by label (e.g. manager) -> numeric value."""
    df = series.rename("value").rename_axis("label").reset_index()
    chart = (
        alt.Chart(df)
        .mark_bar(color=color)
        .encode(
            x=alt.X("value:Q", title=value_title),
            y=alt.Y("label:N", sort="-x", title=None),          # high-to-low
            tooltip=[alt.Tooltip("label:N", title=""),
                     alt.Tooltip("value:Q", title=value_title, format=".1f")],
        )
        .properties(height=alt.Step(26))
    )
    st.altair_chart(chart, use_container_width=True)
