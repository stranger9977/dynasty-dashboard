"""Birthday enrichment from Sleeper and nflreadr."""
import json
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
import pandas as pd


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/diacritics/suffixes, collapse whitespace."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower()
    for ch in [".", ",", "'", "-"]:
        s = s.replace(ch, "")
    for suffix in [" jr", " sr", " ii", " iii", " iv", " v"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = " ".join(s.split())
    return s


def _names_match(a: str, b: str) -> bool:
    """Return True if two already-normalized names match exactly or are highly similar.

    Uses SequenceMatcher >= 0.90 to handle apostrophe/spelling variants
    (e.g. 'jamar chase' vs 'jamarr chase').
    """
    if a == b:
        return True
    if not a or not b:
        return False
    return SequenceMatcher(None, a, b).ratio() >= 0.90


def lookup_sleeper_birthday(name: str, position: str, sleeper_db: dict) -> str | None:
    """Look up a player's birthday in the Sleeper players DB.

    Matches by normalized name + position. Falls back to fuzzy match
    (SequenceMatcher >= 0.90) to handle apostrophe/spelling variants.
    """
    target = normalize_name(name)
    for _, player in sleeper_db.items():
        if not isinstance(player, dict):
            continue
        if player.get("position") != position:
            continue
        full = player.get("full_name") or ""
        if _names_match(normalize_name(full), target):
            return player.get("birth_date")
    return None


def enrich_with_birthdays(
    guide_df: pd.DataFrame,
    sleeper_db: dict,
    nfl_birthdays: pd.DataFrame,
) -> pd.DataFrame:
    """Add `birthday` and `birthday_conflict` columns to guide_df.

    Birthday is set when both sources agree (or only one has it).
    Conflict flag is set when both sources disagree.
    """
    nfl_lookup = {
        (normalize_name(r["name"]), r["position"]): r["birth_date"]
        for _, r in nfl_birthdays.iterrows()
    }

    out = guide_df.copy()
    birthdays: list[str | None] = []
    conflicts: list[bool] = []
    for _, row in out.iterrows():
        sb = lookup_sleeper_birthday(row["name"], row["position"], sleeper_db)
        nb = nfl_lookup.get((normalize_name(row["name"]), row["position"]))
        if sb and nb and sb != nb:
            birthdays.append(None)
            conflicts.append(True)
        elif sb:
            birthdays.append(sb)
            conflicts.append(False)
        elif nb:
            birthdays.append(nb)
            conflicts.append(False)
        else:
            birthdays.append(None)
            conflicts.append(False)
    out["birthday"] = birthdays
    # Use object dtype so values remain Python bool (not numpy.bool_),
    # which preserves `is True` / `is False` identity checks.
    out["birthday_conflict"] = pd.Series(conflicts, dtype=object, index=out.index)
    return out


def load_sleeper_db(path: str = "data/sleeper_players.json") -> dict:
    return json.loads(Path(path).read_text())
