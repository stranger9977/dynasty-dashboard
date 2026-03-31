import json
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from config import KTC_HISTORY_DIR, KTC_HISTORY_TTL_DAYS, KTC_PLAYER_URL, KTC_DYNASTY_URL
from ingestion.ktc import extract_players_array, HEADERS


def _parse_history_date(d: str) -> date:
    """Parse KTC date format YYMMDD to a Python date."""
    year = 2000 + int(d[:2])
    month = int(d[2:4])
    day = int(d[4:6])
    return date(year, month, day)


def fetch_player_history(ktc_slug: str, ktc_id: int) -> list[dict]:
    """Fetch KTC historical superflex values for a player. Disk-cached.

    The player page has a `playerSuperflex` JS variable with an
    `overallValue` array of {d: "YYMMDD", v: int} entries going back years.
    """
    KTC_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = KTC_HISTORY_DIR / f"{ktc_id}.json"

    # Check disk cache
    if cache_path.exists():
        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        if datetime.now() - mtime < timedelta(days=KTC_HISTORY_TTL_DAYS):
            with open(cache_path) as f:
                return json.load(f)

    # Scrape player page — slug already includes the ID (e.g., "josh-allen-365")
    url = f"{KTC_PLAYER_URL}/{ktc_slug}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    # Extract playerSuperflex JS variable which contains overallValue history
    history = []
    match = re.search(
        r"var\s+playerSuperflex\s*=\s*(\{.*?\});", resp.text, re.DOTALL
    )
    if match:
        try:
            data = json.loads(match.group(1))
            history = data.get("overallValue", [])
        except (json.JSONDecodeError, ValueError):
            pass

    # Save to disk cache
    with open(cache_path, "w") as f:
        json.dump(history, f)

    return history


def get_ktc_value_at_date(history: list[dict], target: date) -> int | None:
    """Find the KTC value closest to (but not after) the target date."""
    if not history:
        return None

    best_val = None
    best_date = None

    for entry in history:
        try:
            d = _parse_history_date(entry["d"])
        except (ValueError, KeyError):
            continue
        if d <= target:
            if best_date is None or d > best_date:
                best_date = d
                best_val = entry["v"]

    # If no entry before target, use the earliest available
    if best_val is None and history:
        try:
            earliest = min(history, key=lambda e: e["d"])
            best_val = earliest["v"]
        except (ValueError, KeyError):
            pass

    return best_val


def build_pick_lookup() -> dict[str, tuple[str, int]]:
    """Fetch KTC main page and extract draft pick entries (position RDP).

    Returns {pick_name: (ktc_slug, ktc_id)} e.g.
    {"2026 Early 1st": ("2026-early-1st-pick", 12345)}
    """
    try:
        resp = requests.get(KTC_DYNASTY_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        players = extract_players_array(resp.text)
    except (requests.RequestException, ValueError):
        return {}

    lookup = {}
    for p in players:
        pos_id = p.get("positionID")
        position = p.get("position", "")
        if pos_id == 5 or position == "RDP":
            name = p.get("playerName", "")
            slug = p.get("slug", "")
            ktc_id = p.get("playerID")
            if name and ktc_id:
                lookup[name] = (slug, ktc_id)
    return lookup


def batch_fetch_histories(
    players: list[tuple[str, int]],
    progress_callback=None,
) -> dict[int, list[dict]]:
    """Fetch KTC history for multiple players with rate limiting.

    Args:
        players: list of (ktc_slug, ktc_id) tuples
        progress_callback: optional callable(current, total)

    Returns: {ktc_id: history_list}
    """
    results = {}
    total = len(players)

    for i, (slug, ktc_id) in enumerate(players):
        # Check if already cached (no sleep needed)
        cache_path = KTC_HISTORY_DIR / f"{ktc_id}.json"
        needs_fetch = True
        if cache_path.exists():
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if datetime.now() - mtime < timedelta(days=KTC_HISTORY_TTL_DAYS):
                needs_fetch = False

        history = fetch_player_history(slug, ktc_id)
        results[ktc_id] = history

        if progress_callback:
            progress_callback(i + 1, total)

        # Rate limit only for actual HTTP requests
        if needs_fetch and i < total - 1:
            time.sleep(0.5)

    return results
