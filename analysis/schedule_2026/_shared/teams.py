"""Team metadata: stadium coords, timezones, divisions. Hardcoded — 32 teams + neutral sites."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Stadium:
    name: str
    lat: float
    lon: float
    tz: str
    roof: str  # 'outdoor', 'dome', 'retractable'

# Keyed by nflverse stadium_id where stable; international venues keyed by name.
STADIUMS: dict[str, Stadium] = {
    "ATL97": Stadium("Mercedes-Benz Stadium", 33.7553, -84.4006, "America/New_York", "retractable"),
    "BAL00": Stadium("M&T Bank Stadium", 39.2780, -76.6227, "America/New_York", "outdoor"),
    "BOS00": Stadium("Gillette Stadium", 42.0909, -71.2643, "America/New_York", "outdoor"),
    "BUF00": Stadium("Highmark Stadium", 42.7738, -78.7870, "America/New_York", "outdoor"),
    "CAR00": Stadium("Bank of America Stadium", 35.2258, -80.8528, "America/New_York", "outdoor"),
    "CHI98": Stadium("Soldier Field", 41.8623, -87.6167, "America/Chicago", "outdoor"),
    "CIN00": Stadium("Paycor Stadium", 39.0954, -84.5160, "America/New_York", "outdoor"),
    "CLE00": Stadium("Huntington Bank Field", 41.5061, -81.6995, "America/New_York", "outdoor"),
    "DAL00": Stadium("AT&T Stadium", 32.7473, -97.0945, "America/Chicago", "retractable"),
    "DEN00": Stadium("Empower Field at Mile High", 39.7439, -105.0201, "America/Denver", "outdoor"),
    "DET00": Stadium("Ford Field", 42.3400, -83.0456, "America/New_York", "dome"),
    "GNB00": Stadium("Lambeau Field", 44.5013, -88.0622, "America/Chicago", "outdoor"),
    "HOU00": Stadium("NRG Stadium", 29.6847, -95.4107, "America/Chicago", "retractable"),
    "IND00": Stadium("Lucas Oil Stadium", 39.7601, -86.1638, "America/New_York", "retractable"),
    "JAX00": Stadium("EverBank Stadium", 30.3239, -81.6373, "America/New_York", "outdoor"),
    "KAN00": Stadium("Arrowhead Stadium", 39.0489, -94.4839, "America/Chicago", "outdoor"),
    "LAX01": Stadium("SoFi Stadium", 33.9535, -118.3392, "America/Los_Angeles", "dome"),
    "MIA00": Stadium("Hard Rock Stadium", 25.9580, -80.2389, "America/New_York", "outdoor"),
    "MIN01": Stadium("U.S. Bank Stadium", 44.9737, -93.2581, "America/Chicago", "dome"),
    "NAS00": Stadium("Nissan Stadium", 36.1665, -86.7713, "America/Chicago", "outdoor"),
    "NOR00": Stadium("Caesars Superdome", 29.9511, -90.0814, "America/Chicago", "dome"),
    "NYC01": Stadium("MetLife Stadium", 40.8135, -74.0745, "America/New_York", "outdoor"),
    "PHI00": Stadium("Lincoln Financial Field", 39.9008, -75.1675, "America/New_York", "outdoor"),
    "PHO00": Stadium("State Farm Stadium", 33.5276, -112.2626, "America/Phoenix", "retractable"),
    "PIT00": Stadium("Acrisure Stadium", 40.4468, -80.0158, "America/New_York", "outdoor"),
    "SEA00": Stadium("Lumen Field", 47.5952, -122.3316, "America/Los_Angeles", "outdoor"),
    "SFO01": Stadium("Levi's Stadium", 37.4032, -121.9696, "America/Los_Angeles", "outdoor"),
    "TAM00": Stadium("Raymond James Stadium", 27.9759, -82.5033, "America/New_York", "outdoor"),
    "VEG00": Stadium("Allegiant Stadium", 36.0908, -115.1830, "America/Los_Angeles", "dome"),
    "WAS00": Stadium("Northwest Stadium", 38.9078, -76.8645, "America/New_York", "outdoor"),
}

# International venues — keyed by stadium name in nflverse (since stadium_id reuses home team's id)
INTERNATIONAL: dict[str, Stadium] = {
    "Melbourne Cricket Ground": Stadium("Melbourne Cricket Ground", -37.8200, 144.9834, "Australia/Melbourne", "outdoor"),
    "Tottenham Hotspur Stadium": Stadium("Tottenham Hotspur Stadium", 51.6042, -0.0664, "Europe/London", "retractable"),
    "Wembley Stadium": Stadium("Wembley Stadium", 51.5560, -0.2796, "Europe/London", "retractable"),
    "FC Bayern Munich Stadium": Stadium("Allianz Arena", 48.2188, 11.6247, "Europe/Berlin", "outdoor"),
    "Bernabeu": Stadium("Santiago Bernabéu", 40.4530, -3.6883, "Europe/Madrid", "retractable"),
    "Stade de France": Stadium("Stade de France", 48.9244, 2.3601, "Europe/Paris", "outdoor"),
    "Estadio Banorte": Stadium("Estadio Banorte (Azteca)", 19.3026, -99.1505, "America/Mexico_City", "outdoor"),
    "Maracana Stadium": Stadium("Maracanã", -22.9122, -43.2302, "America/Sao_Paulo", "outdoor"),
}

# Map team abbr → home stadium_id
TEAM_HOME_STADIUM: dict[str, str] = {
    "ARI": "PHO00", "ATL": "ATL97", "BAL": "BAL00", "BUF": "BUF00",
    "CAR": "CAR00", "CHI": "CHI98", "CIN": "CIN00", "CLE": "CLE00",
    "DAL": "DAL00", "DEN": "DEN00", "DET": "DET00", "GB":  "GNB00",
    "HOU": "HOU00", "IND": "IND00", "JAX": "JAX00", "KC":  "KAN00",
    "LA":  "LAX01", "LAC": "LAX01", "LV":  "VEG00", "MIA": "MIA00",
    "MIN": "MIN01", "NE":  "BOS00", "NO":  "NOR00", "NYG": "NYC01",
    "NYJ": "NYC01", "PHI": "PHI00", "PIT": "PIT00", "SEA": "SEA00",
    "SF":  "SFO01", "TB":  "TAM00", "TEN": "NAS00", "WAS": "WAS00",
}

DIVISIONS: dict[str, str] = {
    "BUF": "AFC East", "MIA": "AFC East", "NE": "AFC East", "NYJ": "AFC East",
    "BAL": "AFC North", "CIN": "AFC North", "CLE": "AFC North", "PIT": "AFC North",
    "HOU": "AFC South", "IND": "AFC South", "JAX": "AFC South", "TEN": "AFC South",
    "DEN": "AFC West", "KC": "AFC West", "LAC": "AFC West", "LV": "AFC West",
    "DAL": "NFC East", "NYG": "NFC East", "PHI": "NFC East", "WAS": "NFC East",
    "CHI": "NFC North", "DET": "NFC North", "GB": "NFC North", "MIN": "NFC North",
    "ATL": "NFC South", "CAR": "NFC South", "NO": "NFC South", "TB": "NFC South",
    "ARI": "NFC West", "LA": "NFC West", "SEA": "NFC West", "SF": "NFC West",
}

ALL_TEAMS: list[str] = sorted(DIVISIONS.keys())


def home_stadium(team: str) -> Stadium:
    """Return the Stadium for a team's home venue."""
    sid = TEAM_HOME_STADIUM[team]
    return STADIUMS[sid]


def resolve_stadium(stadium_id: str, stadium_name: str) -> Stadium:
    """Resolve a game's actual stadium, handling neutral/international games.

    nflverse reuses the 'home' team's stadium_id for international games, so we
    have to dispatch on stadium NAME for international venues.
    """
    if stadium_name in INTERNATIONAL:
        return INTERNATIONAL[stadium_name]
    return STADIUMS[stadium_id]


def is_neutral_site(team: str, stadium_id: str, stadium_name: str) -> bool:
    """True if this game is at a venue that is not the team's home stadium."""
    if stadium_name in INTERNATIONAL:
        return True
    return TEAM_HOME_STADIUM.get(team) != stadium_id
