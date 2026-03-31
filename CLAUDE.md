# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```bash
uv run streamlit run streamlit_app.py
```

Uses `uv` for package management (not pip/venv). Python 3.12+. Install deps with `uv sync`.

## Architecture

Streamlit dynasty fantasy football dashboard with manual page dispatch (not native multipage — `views/` not `pages/`).

### Entry Flow

`streamlit_app.py` → `components/sidebar.py` renders tool radio → dispatches to `views/*.py`. If no Sleeper league connected, shows `components/league_connect.py` instead.

### Layer Structure

- **`config.py`** — All constants: league settings (Superflex/PPR/12-team), API URLs, data paths, positions
- **`ingestion/`** — Data fetching, scraping, matching, and annotation. No UI code here.
- **`components/`** — Shared Streamlit UI: sidebar (tool nav + data refresh), filters, league connect
- **`views/`** — Tool pages: Ranking Comparison, Waiver Wire, Draft Wizard, Trade History

### Data Sources & Ingestion

| Source | Module | Method |
|---|---|---|
| FantasyCalc | `ingestion/fantasycalc.py` | JSON API (`api.fantasycalc.com`) |
| KeepTradeCut | `ingestion/ktc.py` | HTML scrape — regex extracts `playersArray` JS variable |
| KTC History | `ingestion/ktc_history.py` | Per-player page scrape — extracts `playerSuperflex.overallValue` |
| LateRound | `ingestion/lateround.py` | Manual CSV (`data/lateround_rankings.csv`) |
| Sleeper | `ingestion/sleeper.py` | REST API (no auth, `@st.cache_data(ttl=300)`) |

**Player matching** (`ingestion/matching.py`): 3-stage merge — MFL ID join → exact normalized name+position → fuzzy match (SequenceMatcher ≥ 0.85). Produces `merged.parquet` with disagreement metrics.

**KTC values use base `superflexValues`** (not TEP) because FantasyCalc doesn't support TE Premium — using TEP would create false disagreements on TEs.

### Caching Strategy

- **Parquet files** (`data/*.parquet`) — Rankings persisted to disk, refreshed via sidebar button
- **KTC history** (`data/ktc_history/{ktc_id}.json`) — 7-day TTL disk cache per player
- **Sleeper players** (`data/sleeper_players.json`) — Full NFL player list, 7-day disk cache
- **Sleeper API** — `@st.cache_data(ttl=300)` (5 min) on all endpoint functions
- **Trade analysis** — `st.session_state["trade_analysis_{league_id}"]` for computed results

### Session State Keys

`sleeper_username`, `sleeper_display_name`, `user_id`, `league_id`, `league_name`, `ownership_map` — set by league_connect, cleared by disconnect.

### Key Patterns

- Views follow: load parquet → annotate ownership if connected → apply filters → render
- Ownership annotation happens at render time (parquet stays source-agnostic)
- `CURRENT_SEASON = date.today().year` (derived, not hardcoded)
- Sleeper league history traversal via `previous_league_id` chaining
- Trade pick resolution uses `slot_to_roster_id` to map draft slots → original roster owners
- `extract_players_array()` in `ktc.py` is public — reused by `ktc_history.py`

### Draft Wizard Specifics

- `_smart_auto_pick()`: blended_value × positional_need [0.85–1.20] × noise [0.92–1.08]
- Manager rules: 7 rule types (won't draft position/player, will draft player at pick, etc.)
- Blended rank: configurable weights (default 50% LR, 25% FC, 25% KTC)
- Draft auto-detection: finds `player_type=1` (rookie) drafts, fetches full draft via `/draft/{id}`

### Trade History Specifics

- 3 grading modes: Value Gained (Realized), Hindsight (Today), At Trade Time
- "Realized" value: tracks asset value to exit date (when traded away) or today if still held
- Exit map built from all trades to find when each (manager, player) pair was traded away
- Startup pick-only trades excluded by default (checkbox filter)
