import streamlit as st

from components.sidebar import render_sidebar

st.set_page_config(page_title="Dynasty Dashboard", layout="wide", page_icon="\U0001f3c8")

selected_tool = render_sidebar()

if selected_tool == "Ranking Comparison":
    from views.ranking_comparison import render
    render()
