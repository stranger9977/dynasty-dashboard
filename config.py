from pathlib import Path

# League settings
NUM_QBS = 2  # Superflex
NUM_TEAMS = 12
PPR = 1
IS_DYNASTY = True
TE_PREMIUM = True

# API / scrape URLs
FANTASYCALC_URL = "https://api.fantasycalc.com/values/current"
KTC_DYNASTY_URL = "https://keeptradecut.com/dynasty-rankings"
KTC_ROOKIE_URL = "https://keeptradecut.com/dynasty-rankings/rookie-rankings"
SLEEPER_API = "https://api.sleeper.app/v1"
from datetime import date
CURRENT_SEASON = date.today().year

# Data paths
DATA_DIR = Path(__file__).parent / "data"
FC_PARQUET = DATA_DIR / "fantasycalc.parquet"
KTC_PARQUET = DATA_DIR / "ktc.parquet"
MERGED_PARQUET = DATA_DIR / "merged.parquet"

# KTC history cache
KTC_HISTORY_DIR = DATA_DIR / "ktc_history"
KTC_HISTORY_TTL_DAYS = 7
KTC_PLAYER_URL = "https://keeptradecut.com/dynasty-rankings/players"

# Position groups
POSITIONS = ["QB", "RB", "WR", "TE"]

# Name overrides for matching {fc_name: ktc_name}
NAME_OVERRIDES = {}
