import streamlit as st

from components.sidebar import render_sidebar

st.set_page_config(page_title="Dynasty Dashboard", layout="wide", page_icon="\U0001f3c8")

selected_tool = render_sidebar()

if "league_id" not in st.session_state:
    from components.league_connect import render_league_connect
    render_league_connect()
else:
    if selected_tool == "Ranking Comparison":
        from views.ranking_comparison import render
        render()
    elif selected_tool == "Waiver Wire":
        from views.waiver_wire import render
        render()
