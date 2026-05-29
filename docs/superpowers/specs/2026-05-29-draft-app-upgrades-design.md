# Draft App Upgrades — Design

**Date:** 2026-05-29
**Goal:** Make the dynasty dashboard a live, phone-friendly rookie-draft assistant
for the 2026 draft: add NFL draft capital and consensus ADP as ranking sources,
blend all five sources equally, surface disagreement, show best-available decision
cards (top 2–3 per position) that work both live and in a mock, make every column
easily sortable on a phone, and deploy to Streamlit Cloud.

> **Scope note:** An earlier draft of this spec included an availability-probability
> Monte-Carlo model with per-manager tendency profiles. That ambitious piece is
> **rolled back** — instead the user judges who'll go before their next pick by
> sorting the columns manually. Not built now.

## Context

- Streamlit app, manual page dispatch (`views/`), `uv`, Python 3.12, no secrets.
- Rookie ranks today: LateRound (manual CSV), FantasyCalc (API), KTC (scrape),
  merged in `views/draft_wizard.py::_get_rookies()` with a weighted `blended_rank`.
- `data/` is gitignored → cloud clone starts empty; KTC scrape may be blocked from
  cloud IPs. Solution (approved): commit a seed snapshot; app boots from it.
- 2026 NFL draft data confirmed from nflverse. Consensus ADP supplied as an image,
  transcribed to `data/adp_rankings.csv` (72 players; pos-ranks sum to 72, ADP
  monotonic, names cross-checked vs nflverse/merged).
- Target rookie draft: league **"Make it (dy)Nasty"** under user **brochillington**
  (draft `1312130398142107648`) — used only to connect/auto-detect the draft.

## Ranking sources (5, blended with EQUAL weights = 20% each)

| Source | Key | Origin |
|---|---|---|
| LateRound | `lr_rank` | manual CSV (`data/lateround_rankings.csv`) — use **rank, not tier** |
| FantasyCalc | `fc_rookie_rank` | API (existing) |
| KeepTradeCut | `ktc_rookie_rank` | scrape (existing) |
| NFL Draft capital | `draft_skill_rank` | nflverse (new) |
| Consensus ADP | `adp_rank` | manual CSV (`data/adp_rankings.csv`, new) |

`blended_rank` = equal-weight mean of available source ranks, renormalized per
player when a source is missing. Sidebar sliders default 20×5, adjustable.

## Components

### 1. NFL Draft Capital — `ingestion/nfl_draft.py`
- `fetch_nfl_draft(season=CURRENT_SEASON)`: download nflverse `draft_picks.parquet`
  (`requests`→`BytesIO`→`read_parquet`), filter season + skill positions →
  `name, position, team, college, draft_overall_pick, draft_skill_rank,
  draft_pos_rank` (`draft_skill_rank` = dense rank of skill players by pick;
  `draft_pos_rank` = rank by pick within position). Persist `data/nfl_draft.parquet`.
- `merge_nfl_draft(rookies, draft)`: normalized name+position join + fuzzy fallback
  (mirrors `ingestion/lateround.py`).

### 2. Consensus ADP — `ingestion/adp.py`
- `load_adp()`: read `data/adp_rankings.csv` (`rank,name,position,pos_rank,adp`) →
  `adp_rank` (from `rank`), `adp_pos_rank`, `adp_value` (decimal, for display).
- `merge_adp(rookies, adp)`: same normalized+fuzzy join helper.

### 3. Blend, LateRound-by-rank, disagreement (in `_get_rookies`)
- `RANK_SOURCES` += `"NFL Draft": "draft_skill_rank"`, `"ADP": "adp_rank"`.
- Equal-weight blend over the 5 source ranks (renormalized for missing sources).
- LateRound surfaced by `lr_rank`; `lr_tier` dropped from board/cards.
- Disagreement: `rank_spread` = max−min across the 5 source ranks (≥2 present);
  `source_high`/`source_low` = most bullish/bearish source.

### 4. Best-Available decision cards (shared live + mock)
- A render helper showing the **best 2–3 available per position** (QB/RB/WR/TE) as
  cards, used in BOTH the Draft Board (first page) and the mock's "your pick" view.
- "Available" pool = rookies minus already-drafted:
  - **Live (first page):** from `get_draft_picks(draft_id)` (short TTL ≈20–30s +
    manual refresh button); falls back to overall top-N before any picks. Match
    drafted players by `sleeper_id`, then normalized name.
  - **Mock:** minus the mock's simulated picks.
- Card decision info: name, pos, NFL team, **age (decimal)**, college,
  `blended_rank`, NFL Draft (skill rank + overall pick), ADP, LR/FC/KTC ranks,
  `rank_spread` + "X loves / Y fades" note.
- `top_n` per position configurable (2 or 3).

### 5. Sortable board + Biggest Disagreements
- Compact, **sortable** rookie table (tap a header to sort on phone): Player, Pos,
  Team, Blend#, ADP#, Draft#, LR#, FC#, KTC#, Spread, Age — full detail available;
  this is the manual "who might go before my next pick" tool.
- Dedicated **Biggest Disagreements** table sorted by `rank_spread` desc with each
  source's rank + range + bull/bear label.

### 6. Mobile Draft Wizard (`views/draft_wizard.py`)
- Move **Rank by** + board position filter into the top of the main pane (off the
  sidebar drawer). Cards (§4) are the primary phone surface.
- Compact default columns with full per-source detail behind an expander; every
  column sortable. Age decimal. Reduce mock-grid columns for phones (low priority).
- **Mock mirrors live:** same cards + sortable board render in both, so rehearsing a
  mock exercises exactly the live draft-day surface.
- Blend-weight sliders stay in the sidebar (advanced).

### 7. Refresh + freshness (`components/sidebar.py`, `tools/refresh_rankings.py`)
- Per-source freshness lines (FC, KTC, LR, NFL Draft, ADP): count + last-updated.
- One Refresh button also fetches NFL draft capital; **seed fallback** if a live
  source fails (no wipe). ADP + LateRound are manual CSVs (refresh re-reads them).

### 8. Deploy to Streamlit Cloud
- Commit seed snapshots to **`data/seed/`** (un-gitignore): fantasycalc, ktc,
  merged, nfl_draft parquets + lateround_rankings.csv + adp_rankings.csv.
- Startup bootstrap: if `data/*` missing, copy from `data/seed/`.
- Add `.streamlit/config.toml`; generate `requirements.txt`. Deploy from `main`
  after merging `feat/draft-app-upgrades`. No secrets.

## Error handling
- Live fetches wrapped; on failure fall back to existing parquet/seed + sidebar
  warning. Missing source for a player → excluded from that player's blend/spread.
- If no connected draft/order, cards show overall best-available (no live removal).

## Testing
- Unit: draft dense-ranking; ADP load + rank; equal-weight blend renormalization
  (missing source); disagreement spread + bull/bear.
- Headless AppTest: app boots; Draft Wizard returns rookies with all 5 source ranks,
  `blended_rank`, `rank_spread`; best-available cards render for each position.
- Manual: run app, sort columns + view cards + disagreements + a mock pick on a
  narrow viewport.

## Out of scope (YAGNI)
- Availability-probability model and per-manager tendency profiles (rolled back).
- Persisting Sleeper login across cloud cold starts.
- Non-skill draft capital; historical classes; reworking all-players views.
