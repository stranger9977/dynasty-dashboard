import streamlit as st

from ingestion.seed import ensure_data_from_seed
ensure_data_from_seed()

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
    elif selected_tool == "Draft Wizard":
        from views.draft_wizard import render
        render()
    elif selected_tool == "Trade History":
        from views.trade_history import render
        render()
    elif selected_tool == "Start/Sit History":
        from views.start_sit import render
        render()
    elif selected_tool == "Waiver History":
        from views.waiver_history import render
        render()
    elif selected_tool == "Value Over Replacement":
        from views.value_over_replacement import render
        render()
    elif selected_tool == "Manager War":
        from views.manager_war import render
        render()
