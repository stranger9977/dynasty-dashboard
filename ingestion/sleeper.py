import requests
import streamlit as st

from config import SLEEPER_API, CURRENT_SEASON


def get_user(username: str) -> dict | None:
    resp = requests.get(f"{SLEEPER_API}/user/{username}", timeout=10)
    if resp.status_code == 404 or resp.json() is None:
        return None
    resp.raise_for_status()
    data = resp.json()
    return {
        "user_id": data["user_id"],
        "username": data.get("username"),
        "display_name": data.get("display_name"),
        "avatar": data.get("avatar"),
    }


@st.cache_data(ttl=300)
def get_leagues(user_id: str, season: int = CURRENT_SEASON) -> list[dict]:
    resp = requests.get(
        f"{SLEEPER_API}/user/{user_id}/leagues/nfl/{season}", timeout=10
    )
    resp.raise_for_status()
    leagues = []
    for lg in resp.json():
        leagues.append({
            "league_id": lg["league_id"],
            "name": lg["name"],
            "total_rosters": lg.get("total_rosters"),
            "draft_id": lg.get("draft_id"),
            "status": lg.get("status"),
            "settings": lg.get("settings", {}),
        })
    return leagues


@st.cache_data(ttl=300)
def get_rosters(league_id: str) -> list[dict]:
    resp = requests.get(f"{SLEEPER_API}/league/{league_id}/rosters", timeout=10)
    resp.raise_for_status()
    rosters = []
    for r in resp.json():
        rosters.append({
            "roster_id": r["roster_id"],
            "owner_id": r.get("owner_id"),
            "players": r.get("players") or [],
            "starters": r.get("starters") or [],
        })
    return rosters


@st.cache_data(ttl=300)
def get_league_users(league_id: str) -> dict[str, str]:
    resp = requests.get(f"{SLEEPER_API}/league/{league_id}/users", timeout=10)
    resp.raise_for_status()
    return {u["user_id"]: u.get("display_name", u.get("username", "Unknown")) for u in resp.json()}


def build_ownership_map(league_id: str) -> dict[str, str]:
    rosters = get_rosters(league_id)
    users = get_league_users(league_id)
    ownership = {}
    for roster in rosters:
        owner_name = users.get(roster["owner_id"], f"Team {roster['roster_id']}")
        for player_id in roster["players"]:
            ownership[str(player_id)] = owner_name
    return ownership
