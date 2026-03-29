import streamlit as st

from ingestion.sleeper import get_user, get_leagues, build_ownership_map


def render_league_connect():
    st.header("Connect Your Sleeper League")
    st.caption("Enter your Sleeper username to get started")

    username = st.text_input("Sleeper Username", value=st.session_state.get("_input_username", ""))

    if not username:
        return

    user = get_user(username)
    if user is None:
        st.error(f"User '{username}' not found on Sleeper.")
        return

    st.success(f"Found user: **{user['display_name'] or user['username']}**")

    leagues = get_leagues(user["user_id"])
    if not leagues:
        st.warning("No NFL leagues found for this user in the current season.")
        return

    league_options = {f"{lg['name']} ({lg['total_rosters']} teams)": lg for lg in leagues}
    selected_label = st.selectbox("Select a league", list(league_options.keys()))
    selected_league = league_options[selected_label]

    if st.button("Connect League", type="primary"):
        with st.spinner("Loading rosters..."):
            ownership_map = build_ownership_map(selected_league["league_id"])

        st.session_state["sleeper_username"] = user["username"] or username
        st.session_state["sleeper_display_name"] = user["display_name"] or username
        st.session_state["user_id"] = user["user_id"]
        st.session_state["league_id"] = selected_league["league_id"]
        st.session_state["league_name"] = selected_league["name"]
        st.session_state["ownership_map"] = ownership_map
        st.rerun()
