from datetime import datetime, date

import pandas as pd
import streamlit as st

from config import MERGED_PARQUET, CURRENT_SEASON
from ingestion.sleeper import (
    get_league_info,
    get_league_users,
    get_rosters,
    get_league_drafts,
    get_draft,
    get_draft_picks,
    get_transactions,
)
from ingestion.ktc_history import (
    fetch_player_history,
    get_ktc_value_at_date,
    build_pick_lookup,
    batch_fetch_histories,
)


def get_league_chain(league_id: str) -> list[dict]:
    """Walk previous_league_id chain to get all seasons, oldest first."""
    chain = []
    current_id = league_id
    seen = set()

    while current_id and current_id not in seen:
        seen.add(current_id)
        info = get_league_info(current_id)
        if info is None:
            break
        chain.append(info)
        current_id = info.get("previous_league_id")

    chain.reverse()  # oldest first
    return chain


def build_roster_to_manager(league_id: str) -> dict[int, str]:
    """Map roster_id → manager display_name for a league."""
    rosters = get_rosters(league_id)
    users = get_league_users(league_id)
    mapping = {}
    for r in rosters:
        owner_id = r.get("owner_id")
        name = users.get(owner_id, f"Team {r['roster_id']}")
        mapping[r["roster_id"]] = name
    return mapping


def _get_draft_pick_map(league_id: str) -> dict[tuple[int, int], dict]:
    """For a league's rookie drafts, map (round, original_roster_id) → draft pick info.

    The key is (round, original_roster_id) where original_roster_id comes from
    slot_to_roster_id — the team whose draft slot it originally was. This matches
    how Sleeper represents traded picks: {season, round, roster_id} where roster_id
    is the original slot owner.

    Returns {(round, original_roster_id): {"player_id": str, "pick_no": int, ...}}
    """
    drafts = get_league_drafts(league_id)
    pick_map = {}

    for d in drafts:
        draft_id = d.get("draft_id")
        if not draft_id:
            continue
        full_draft = get_draft(draft_id)
        if not full_draft or full_draft.get("status") != "complete":
            continue

        # Only use rookie drafts (player_type == 1) for pick resolution.
        settings = full_draft.get("settings", {})
        player_type = settings.get("player_type", 0)
        if player_type != 1:
            continue

        # slot_to_roster_id maps draft_slot → original roster_id
        slot_to_roster = full_draft.get("slot_to_roster_id") or {}

        try:
            picks = get_draft_picks(draft_id)
        except Exception:
            continue

        for pick in picks:
            rnd = pick.get("round")
            draft_slot = pick.get("draft_slot")
            player_id = pick.get("player_id")
            if not (rnd and draft_slot and player_id):
                continue

            # Map draft_slot back to the original roster that owned this slot
            original_roster_id = slot_to_roster.get(str(draft_slot))
            if original_roster_id is None:
                # Fallback: if no slot mapping, use the roster that picked
                original_roster_id = pick.get("roster_id")

            pick_map[(rnd, original_roster_id)] = {
                "player_id": str(player_id),
                "pick_no": pick.get("pick_no"),
                "draft_slot": draft_slot,
                "roster_id": pick.get("roster_id"),  # who actually picked
            }

    return pick_map


def _classify_pick_tier(roster_id: int, total_rosters: int, roster_to_manager: dict) -> str:
    """Classify a pick as Early/Mid/Late based on roster position.

    Without actual standings, we default to Mid. This is a rough heuristic.
    """
    # Default to Mid since we don't have historical standings
    return "Mid"


def fetch_all_trades(league_id: str) -> list[dict]:
    """Fetch all trades across all seasons for a league.

    Returns list of normalized trade dicts sorted by date (newest first).
    """
    chain = get_league_chain(league_id)
    all_trades = []

    for league_info in chain:
        lid = league_info["league_id"]
        season = league_info["season"]
        roster_map = build_roster_to_manager(lid)

        # Build draft pick resolution map for this season
        draft_pick_map = _get_draft_pick_map(lid)

        for week in range(1, 19):
            try:
                txns = get_transactions(lid, week)
            except Exception:
                continue

            for txn in txns:
                if txn.get("type") != "trade" or txn.get("status") != "complete":
                    continue

                trade = _normalize_trade(
                    txn, season, week, lid, roster_map, draft_pick_map, chain
                )
                if trade:
                    all_trades.append(trade)

    # Sort newest first
    all_trades.sort(key=lambda t: t["timestamp"], reverse=True)
    return all_trades


def _normalize_trade(
    txn: dict,
    season: int,
    week: int,
    league_id: str,
    roster_map: dict[int, str],
    draft_pick_map: dict[tuple[int, int], dict],
    league_chain: list[dict],
) -> dict | None:
    """Normalize a Sleeper trade transaction into our standard format."""
    timestamp = txn.get("status_updated", 0)
    trade_date = datetime.fromtimestamp(timestamp / 1000).date() if timestamp else None

    roster_ids = txn.get("roster_ids", [])
    if len(roster_ids) < 2:
        return None

    adds = txn.get("adds") or {}
    drops = txn.get("drops") or {}
    draft_picks = txn.get("draft_picks") or []

    # Group assets by roster_id
    # adds: {player_id: receiving_roster_id}
    sides = {}
    for rid in roster_ids:
        sides[rid] = {
            "roster_id": rid,
            "manager": roster_map.get(rid, f"Team {rid}"),
            "players_received": [],
            "picks_received": [],
        }

    for player_id, receiving_rid in adds.items():
        receiving_rid = int(receiving_rid) if not isinstance(receiving_rid, int) else receiving_rid
        if receiving_rid in sides:
            sides[receiving_rid]["players_received"].append(str(player_id))

    for dp in draft_picks:
        owner_rid = dp.get("owner_id")  # who receives the pick
        if isinstance(owner_rid, str):
            owner_rid = int(owner_rid)
        if owner_rid in sides:
            pick_season = dp.get("season")
            if isinstance(pick_season, str):
                pick_season = int(pick_season)
            pick_round = dp.get("round")
            original_rid = dp.get("roster_id")  # whose slot it originally is

            # Try to resolve pick
            resolved = _resolve_pick(
                pick_season, pick_round, original_rid,
                league_chain, roster_map
            )

            sides[owner_rid]["picks_received"].append({
                "season": pick_season,
                "round": pick_round,
                "original_roster_id": original_rid,
                "original_owner": roster_map.get(original_rid, f"Team {original_rid}"),
                "resolved_player_id": resolved.get("player_id"),
                "resolved_player_name": resolved.get("player_name"),
                "pick_label": resolved.get("pick_label"),
                "is_resolved": resolved.get("is_resolved", False),
            })

    sides_list = list(sides.values())

    return {
        "trade_id": txn.get("transaction_id", ""),
        "season": season,
        "week": week,
        "timestamp": timestamp,
        "date": trade_date,
        "league_id": league_id,
        "sides": sides_list,
    }


def _resolve_pick(
    pick_season: int,
    pick_round: int,
    original_roster_id: int,
    league_chain: list[dict],
    roster_map: dict[int, str],
) -> dict:
    """Try to resolve a traded draft pick to the player who was actually drafted."""
    result = {
        "player_id": None,
        "player_name": None,
        "pick_label": f"{pick_season} Round {pick_round}",
        "is_resolved": False,
    }

    if not pick_season or not pick_round:
        return result

    # Find the league for the pick's season
    target_league = None
    for info in league_chain:
        if info["season"] == pick_season:
            target_league = info
            break

    if not target_league:
        return result

    # Check if draft is complete
    draft_pick_map = _get_draft_pick_map(target_league["league_id"])

    key = (pick_round, original_roster_id)
    if key in draft_pick_map:
        pick_info = draft_pick_map[key]
        result["player_id"] = pick_info["player_id"]
        result["is_resolved"] = True
        # Player name will be filled in later from the parquet lookup

    return result


def _load_sleeper_players() -> dict[str, dict]:
    """Fetch and cache the full Sleeper players list for name resolution.

    Returns {sleeper_id: {name, position}} for all NFL players (current + historical).
    Cached to disk for 7 days since this is a ~30MB download.
    """
    import json
    from config import DATA_DIR

    cache_path = DATA_DIR / "sleeper_players.json"

    if cache_path.exists():
        from datetime import timedelta
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(days=7):
            with open(cache_path) as f:
                return json.load(f)

    import requests
    from config import SLEEPER_API
    try:
        resp = requests.get(f"{SLEEPER_API}/players/nfl", timeout=60)
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        return {}

    players = {}
    for pid, p in raw.items():
        name = p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
        if name:
            players[pid] = {
                "name": name,
                "position": p.get("position", ""),
            }

    DATA_DIR.mkdir(exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(players, f)

    return players


def build_player_lookup() -> dict[str, dict]:
    """Build a lookup from sleeper_id to player info.

    Uses merged parquet as primary source, supplements with FC parquet,
    then falls back to the full Sleeper players list for historical players.

    Returns {sleeper_id: {name, position, ktc_id, ktc_slug}}
    """
    from config import FC_PARQUET, KTC_PARQUET

    lookup = {}

    # Primary: merged parquet (has ktc_id mapping)
    if MERGED_PARQUET.exists():
        df = pd.read_parquet(MERGED_PARQUET)
        for _, row in df.iterrows():
            sid = row.get("sleeper_id")
            if pd.notna(sid):
                sid = str(int(sid)) if isinstance(sid, float) else str(sid)
                lookup[sid] = {
                    "name": row.get("name", "Unknown"),
                    "position": row.get("position", ""),
                    "ktc_id": int(row["ktc_id"]) if pd.notna(row.get("ktc_id")) else None,
                    "ktc_slug": row.get("ktc_slug") if pd.notna(row.get("ktc_slug")) else None,
                }

    # Supplement: FC parquet has sleeper_id for players not in merged
    if FC_PARQUET.exists():
        fc = pd.read_parquet(FC_PARQUET)
        for _, row in fc.iterrows():
            sid = row.get("sleeper_id")
            if pd.notna(sid):
                sid = str(int(sid)) if isinstance(sid, float) else str(sid)
                if sid not in lookup:
                    lookup[sid] = {
                        "name": row.get("name", "Unknown"),
                        "position": row.get("position", ""),
                        "ktc_id": None,
                        "ktc_slug": None,
                    }

    # Fallback: Sleeper players list for historical/retired players
    sleeper_players = _load_sleeper_players()
    for sid, info in sleeper_players.items():
        if sid not in lookup:
            lookup[sid] = {
                "name": info["name"],
                "position": info["position"],
                "ktc_id": None,
                "ktc_slug": None,
            }

    # Build KTC name → (ktc_id, ktc_slug) map for filling in missing slugs/ids
    ktc_name_map = {}  # "name|position" -> (ktc_id, slug)
    if KTC_PARQUET.exists():
        ktc = pd.read_parquet(KTC_PARQUET)
        for _, row in ktc.iterrows():
            name = row.get("name", "")
            pos = row.get("position", "")
            ktc_id = row.get("ktc_id")
            ktc_slug = row.get("ktc_slug")
            if name and pd.notna(ktc_id):
                key = f"{name.lower().strip()}|{pos}"
                ktc_name_map[key] = (
                    int(ktc_id),
                    ktc_slug if pd.notna(ktc_slug) else None,
                )

    # Fill in missing ktc_id/ktc_slug by name matching
    for sid, info in lookup.items():
        if info["name"]:
            key = f"{info['name'].lower().strip()}|{info['position']}"
            if key in ktc_name_map:
                kid, kslug = ktc_name_map[key]
                if info["ktc_id"] is None:
                    info["ktc_id"] = kid
                if info["ktc_slug"] is None:
                    info["ktc_slug"] = kslug

    return lookup


def grade_trade(value_diff: float) -> str:
    """Grade a trade based on KTC value difference."""
    abs_diff = abs(value_diff)
    if abs_diff >= 3000:
        return "A+"
    elif abs_diff >= 2000:
        return "A"
    elif abs_diff >= 1000:
        return "B"
    elif abs_diff >= 500:
        return "C"
    else:
        return "Fair"


def _build_exit_map(trades: list[dict]) -> dict[tuple[str, str], date]:
    """Build a map of when each manager traded away each player.

    Scans all trades to find exit dates: when a manager gave away a player
    they had previously received. For players traded multiple times, we track
    the earliest exit after each acquisition.

    Returns {(manager, player_id): [exit_date1, exit_date2, ...]} sorted by date.
    """
    from collections import defaultdict

    # Track all exits: (manager, player_id) -> list of exit dates
    exits = defaultdict(list)

    for t in sorted(trades, key=lambda x: x.get("timestamp", 0)):
        trade_date = t.get("date")
        if not trade_date or len(t["sides"]) < 2:
            continue

        for i, side in enumerate(t["sides"]):
            other = t["sides"][1 - i]
            manager = side["manager"]

            # Players this manager GAVE AWAY = players the other side received
            for pid in other.get("players_received", []):
                exits[(manager, pid)].append(trade_date)

            # Picks this manager gave away — track by resolved player_id
            for pick in other.get("picks_received", []):
                if pick.get("is_resolved") and pick.get("resolved_player_id"):
                    exits[(manager, pick["resolved_player_id"])].append(trade_date)

    # Sort each list
    for key in exits:
        exits[key].sort()

    return dict(exits)


def _find_exit_date(
    exit_map: dict,
    manager: str,
    player_id: str,
    acquisition_date: date,
) -> date | None:
    """Find the earliest date after acquisition_date when this manager traded the player away."""
    exits = exit_map.get((manager, player_id), [])
    for d in exits:
        if d > acquisition_date:
            return d
    return None


def compute_trade_values(
    trades: list[dict],
    player_lookup: dict[str, dict],
    histories: dict[int, list[dict]],
    pick_lookup: dict[str, tuple[str, int]],
    pick_histories: dict[int, list[dict]],
) -> list[dict]:
    """Enrich trades with KTC values at trade time, today, and realized.

    "Realized" value = value at exit date if the player was later traded away,
    or today's value if still held. This is the most accurate measure of
    value gained from a trade.

    Each asset gets: `ktc_value` (at trade), `ktc_value_now` (today),
    `ktc_value_realized` (at exit or today).
    Each side gets: `total_value`, `total_value_now`, `total_value_realized`.
    """
    from datetime import date as date_cls
    today = date_cls.today()

    # Build exit map first — needs all trades to know when players changed hands
    exit_map = _build_exit_map(trades)

    enriched = []

    for trade in trades:
        trade_date = trade.get("date")
        if not trade_date:
            enriched.append(trade)
            continue

        for side in trade["sides"]:
            side_value = 0
            side_value_now = 0
            side_value_realized = 0
            player_details = []
            manager = side["manager"]

            # Value players
            for pid in side["players_received"]:
                info = player_lookup.get(pid, {})
                name = info.get("name", f"ID:{pid}")
                position = info.get("position", "")
                ktc_id = info.get("ktc_id")

                value = None
                value_now = None
                value_realized = None
                exit_date = _find_exit_date(exit_map, manager, pid, trade_date)

                if ktc_id and ktc_id in histories:
                    hist = histories[ktc_id]
                    value = get_ktc_value_at_date(hist, trade_date)
                    value_now = get_ktc_value_at_date(hist, today)
                    if exit_date:
                        value_realized = get_ktc_value_at_date(hist, exit_date)
                    else:
                        value_realized = value_now  # still held

                if value:
                    side_value += value
                if value_now:
                    side_value_now += value_now
                if value_realized:
                    side_value_realized += value_realized

                player_details.append({
                    "name": name,
                    "position": position,
                    "sleeper_id": pid,
                    "ktc_value": value,
                    "ktc_value_now": value_now,
                    "ktc_value_realized": value_realized,
                    "exit_date": exit_date,
                    "type": "player",
                })

            # Value picks
            for pick in side["picks_received"]:
                pick_value = None
                pick_value_now = None
                pick_value_realized = None
                display_name = pick["pick_label"]
                exit_date = None

                if pick["is_resolved"] and pick["resolved_player_id"]:
                    pid = pick["resolved_player_id"]
                    info = player_lookup.get(pid, {})
                    player_name = info.get("name")
                    pick["resolved_player_name"] = player_name

                    exit_date = _find_exit_date(exit_map, manager, pid, trade_date)

                    ktc_id = info.get("ktc_id")
                    if ktc_id and ktc_id in histories:
                        hist = histories[ktc_id]
                        pick_value = get_ktc_value_at_date(hist, trade_date)
                        pick_value_now = get_ktc_value_at_date(hist, today)
                        if exit_date:
                            pick_value_realized = get_ktc_value_at_date(hist, exit_date)
                        else:
                            pick_value_realized = pick_value_now

                    became_label = f" -- became {player_name}" if player_name else ""
                    display_name = f"{pick['pick_label']}{became_label}"
                else:
                    pick_name = _match_pick_to_ktc(pick, pick_lookup)
                    if pick_name:
                        slug_id = pick_lookup.get(pick_name)
                        if slug_id:
                            _, ktc_id = slug_id
                            if ktc_id in pick_histories:
                                hist = pick_histories[ktc_id]
                                pick_value = get_ktc_value_at_date(hist, trade_date)
                                pick_value_now = get_ktc_value_at_date(hist, today)
                                pick_value_realized = pick_value_now  # still held
                        display_name = pick_name

                if pick_value:
                    side_value += pick_value
                if pick_value_now:
                    side_value_now += pick_value_now
                if pick_value_realized:
                    side_value_realized += pick_value_realized

                player_details.append({
                    "name": display_name,
                    "position": "PICK",
                    "ktc_value": pick_value,
                    "ktc_value_now": pick_value_now,
                    "ktc_value_realized": pick_value_realized,
                    "exit_date": exit_date,
                    "type": "pick",
                    "is_resolved": pick["is_resolved"],
                    "resolved_player_name": pick.get("resolved_player_name"),
                })

            side["total_value"] = side_value
            side["total_value_now"] = side_value_now
            side["total_value_realized"] = side_value_realized
            side["assets"] = player_details

        # Compute diffs and grades for all three modes
        if len(trade["sides"]) >= 2:
            s0, s1 = trade["sides"][0], trade["sides"][1]

            # At trade time
            _set_diff(trade, s0["total_value"], s1["total_value"],
                      s0["manager"], s1["manager"],
                      "", "")

            # Today's values
            _set_diff(trade, s0["total_value_now"], s1["total_value_now"],
                      s0["manager"], s1["manager"],
                      "_now", "_now")

            # Realized values
            _set_diff(trade, s0["total_value_realized"], s1["total_value_realized"],
                      s0["manager"], s1["manager"],
                      "_realized", "_realized")
        else:
            for suffix in ["", "_now", "_realized"]:
                trade[f"value_diff{suffix}"] = 0
                trade[f"abs_diff{suffix}"] = 0
                trade[f"grade{suffix}"] = "Fair"
                trade[f"winner{suffix}"] = None
                trade[f"loser{suffix}"] = None

        enriched.append(trade)

    return enriched


def _set_diff(trade, v0, v1, mgr0, mgr1, key_suffix, winner_suffix):
    """Helper to set diff/grade/winner/loser fields on a trade."""
    diff = v0 - v1
    trade[f"value_diff{key_suffix}"] = diff
    trade[f"abs_diff{key_suffix}"] = abs(diff)
    trade[f"grade{key_suffix}"] = grade_trade(diff)
    if diff > 0:
        trade[f"winner{winner_suffix}"] = mgr0
        trade[f"loser{winner_suffix}"] = mgr1
    elif diff < 0:
        trade[f"winner{winner_suffix}"] = mgr1
        trade[f"loser{winner_suffix}"] = mgr0
    else:
        trade[f"winner{winner_suffix}"] = None
        trade[f"loser{winner_suffix}"] = None


def _match_pick_to_ktc(pick: dict, pick_lookup: dict) -> str | None:
    """Match a Sleeper draft pick to a KTC pick name.

    Tries variations like "2026 Mid 1st", "2026 1st" etc.
    """
    season = pick.get("season")
    rnd = pick.get("round")
    if not season or not rnd:
        return None

    round_names = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
    round_label = round_names.get(rnd, f"{rnd}th")

    # Try with tiers
    for tier in ["Mid", "Early", "Late", ""]:
        if tier:
            name = f"{season} {tier} {round_label}"
        else:
            name = f"{season} {round_label}"
        if name in pick_lookup:
            return name

    return None
