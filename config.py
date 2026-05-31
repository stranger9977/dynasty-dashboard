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
NFL_DRAFT_PARQUET = DATA_DIR / "nfl_draft.parquet"
PROJECTIONS_PARQUET = DATA_DIR / "projections.parquet"
ADP_CSV = DATA_DIR / "adp_rankings.csv"
SEED_DIR = DATA_DIR / "seed"

# Equal-weight rookie blend across the 5 sources
BLEND_WEIGHTS_DEFAULT = {"lr": 0.20, "fc": 0.20, "ktc": 0.20, "draft": 0.20, "adp": 0.20}

# KTC history cache
KTC_HISTORY_DIR = DATA_DIR / "ktc_history"
KTC_HISTORY_TTL_DAYS = 7
KTC_PLAYER_URL = "https://keeptradecut.com/dynasty-rankings/players"

# Position groups
POSITIONS = ["QB", "RB", "WR", "TE"]

# Starting-lineup counts for "points above starters" (user-defined: SF approximated
# by a 2nd QB). Used by the Roster Impact view.
STARTER_COUNTS = {"QB": 2, "RB": 3, "WR": 4, "TE": 2}

# Points analysis
PPW_FALLBACK = 110.0  # Points per win fallback
PPW_MIN, PPW_MAX = 50.0, 250.0  # Sanity bounds for PPW estimate

# Lineup slot eligibility
FLEX_ELIGIBLE = {"RB", "WR", "TE"}
SUPER_FLEX_ELIGIBLE = {"QB", "RB", "WR", "TE"}

# Composite scoring grade thresholds (percentile-based, 0-100)
COMPOSITE_GRADE_THRESHOLDS = {"A+": 90, "A": 75, "B": 60, "C": 45, "Fair": 0}

# Name overrides for matching {fc_name: ktc_name}
NAME_OVERRIDES = {}
