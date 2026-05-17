# 2026 NFL Schedule Analysis

15 angle-by-angle analyses of the 2026 NFL schedule (released 2026-05-14), built for dynasty fantasy football decision support.

## Quick Start

```bash
cd ~/projects/dynasty-dashboard
uv run python analysis/schedule_2026/scripts/<analysis>.py
```

Each script reads from `data/raw/` and writes to `output/<slug>/{data.parquet, chart.png, findings.md}`.

## Data Sources

| Source | File(s) | What it provides |
|---|---|---|
| nflverse `games.csv` | `data/raw/games.csv` | Full schedule incl. 272 games for 2026, rest days, stadium, kickoff times, historical betting lines |
| nflverse PBP | `data/raw/pbp_{2020..2025}.parquet` | Play-by-play for position SoS, pace, FPA |
| nflverse rosters | `data/raw/rosters_{2024,2025}.csv` | Player positions, team movement (revenge games) |
| Rotowire / DK | `data/raw/win_totals_2026.csv` | 2026 season win totals (BAL highest 11.5, ARI/MIA lowest 4.5) |
| Hardcoded | `_shared/teams.py` | Stadium lat/lon, timezones, roof type, divisions |
| meteostat | climate cache | Historical wind per outdoor stadium |
| Ourlads + PBP | scraped at runtime | CB depth charts + coverage stats |

## Shared Utilities (`_shared/`)

- `nflverse.py` — `load_games()`, `load_schedule_2026()`, `load_pbp(seasons)`, `load_rosters(season)`, `load_win_totals_2026()`
- `teams.py` — stadium dicts, `home_stadium(team)`, `resolve_stadium(stadium_id, name)`, `is_neutral_site(...)`, `DIVISIONS`, `ALL_TEAMS`
- `output.py` — `write_data(slug, df)`, `write_findings(slug, md)`, `chart_path(slug)`, `artifact_dir(slug)`

## The 15 Analyses

### Schedule-shape (no external data)

| Slug | Headline | Top finding |
|---|---|---|
| [`bye_leverage`](output/bye_leverage/findings.md) | Bye week timing + rest differential | CHI best rest (+15); LAC worst (-24, faces 4 opps off bye) |
| [`gauntlet`](output/gauntlet/findings.md) | 3+ consecutive top-10 opponents | MIN W8-11 (DET, BUF, GB, SF) is league's worst gauntlet; KC most-fortunate (6 easy weeks, 0 gauntlet) |
| [`front_back_sos`](output/front_back_sos/findings.md) | H1 vs H2 SoS swing → trade-deadline timing | Sell-high: PIT (+1.75), SF (+1.68), DET (+1.12). Buy-low: DEN (-1.79), BUF (-1.78), WAS (-1.68) |
| [`schedule_luck`](output/schedule_luck/findings.md) | 10k Monte Carlo SoS vs random schedules | Unlucky: BUF (97.7%ile), CAR (94.6), TB (92.1). Lucky: DET (2.3), CLE (4.0), CIN (12.1). ~63% of "tough schedule" complaints are noise. |
| [`correlation_graph`](output/correlation_graph/findings.md) | Jaccard similarity graph of shared opponents | AFC West (DEN/KC/LV/LAC) most entangled. Auto-tuned threshold = 0.52, 56 edges |
| [`body_clock`](output/body_clock/findings.md) | Local-tz kickoff time per team-game | LA & LV worst (4 body-clock disadvantage games each). Intl games hit ~3:30am body clock for US teams |
| [`revenge_games`](output/revenge_games/findings.md) | FF-relevant players vs former team | 149 revenge games. Week 11 most loaded (13). Marquee: Geno + Lockett vs SEA W10, Mostert vs MIA W1 |
| [`intl_return_dip`](output/intl_return_dip/findings.md) | Historical (2007-2025) return-week effect | **Null result.** 51.4% cover vs 50% baseline (n=107). Within 1 SE — no edge to fade |
| [`travel_miles`](output/travel_miles/findings.md) | Great-circle miles + tz shifts | SF (18,946 mi), LA (17,486), JAX (15,947) — all play overseas. CAR least-traveled (4,317) |

### FF-positional (PBP-derived)

| Slug | Headline | Top finding |
|---|---|---|
| [`position_sos`](output/position_sos/findings.md) | FPA/position SoS, all 17 wks | RBs: PHI/DET/SEA easiest. WRs: NFC East easy, AFC West toughest. TEs: AFC North soft |
| [`ff_playoffs_sos`](output/ff_playoffs_sos/findings.md) | **Most actionable** — SoS for FF playoffs (W14-16) | RB league-winners: SF, NYG, WAS. WR: ARI*, NE, DEN. TE: CLE, SEA, DET. **\*ARI and DAL have W14 byes** → only 2 FF playoff games |
| [`pace_volume`](output/pace_volume/findings.md) | Projected total plays from pace × pace | DAL (1072), CHI, NYG, TB, HOU top. LV (997), MIN, MIA bottom. 4.4 play/game spread |
| [`game_script_rb`](output/game_script_rb/findings.md) | Implied-spread → leading-share for RBs | BAL (9.24) best RB game-script (8 games as 3+ pt favorite, 0 as dog). MIA/ARI/LV's RBs cap out |

### External-data

| Slug | Headline | Top finding |
|---|---|---|
| [`wind_exposure`](output/wind_exposure/findings.md) | meteostat historical wind per outdoor stadium | CLE (156.5), CHI (128.4), PIT, BUF, MIA most-exposed. ARI sheltered (25.5, 13 indoor games) |
| [`cb_wr_matchup`](output/cb_wr_matchup/findings.md) | ⚠️ Team CB unit scores + WR matchup difficulty | DEN/HOU/SEA top CB units. MIA/ARI bottom. **Caveats below** |

## Known Caveats

- **`cb_wr_matchup`** — PFR coverage stats endpoint returned 403 to scrape, so CB quality fell back to PBP-derived counting stats (pass deflections + INTs + tackles, recency-weighted). This is noisier than the spec'd passer-rating-allowed composite. Also: Ourlads scrape missed ARI (URL slug mismatch), 90% CB name match rate. Treat output as a coarse tier, not a precise ranking.
- **`body_clock`** — "advantage" threshold (2h past 1pm local) catches normal 4pm CBS-late and primetime slots, inflating advantage counts (226 league-wide). Net metric (disadvantage − advantage) is still informative, but raw advantage counts overstate the effect. Disadvantage counts are the trustworthy column.
- **`revenge_games`** — Uses 2025 rosters as proxy for 2026 rosters (2026 rosters not yet available). Late summer signings/cuts will shift this list.
- **`intl_return_dip`** — Effect size is within 1 SE of baseline (n=107). Methodology is sound but the underlying phenomenon appears to be noise. Documented as a null result.
- **`schedule_luck`** Monte Carlo draws 11 non-division opponents *with replacement* from the 24-team pool. A without-replacement constraint would tighten the distribution slightly; current implementation is conservative (treats sched as more random than it is).

## Dependencies

Already in project `pyproject.toml`:
- `pandas`, `numpy`, `pyarrow` (data)
- `matplotlib` (charts)
- `networkx` (correlation graph)
- `meteostat` (wind)
- `beautifulsoup4`, `requests` (scraping)
- `zoneinfo` (stdlib, body clock)

## Re-running

To refresh raw data (when nflverse updates 2026 schedule with betting lines, etc.):

```bash
cd ~/projects/dynasty-dashboard/analysis/schedule_2026/data/raw
curl -sLO https://github.com/nflverse/nfldata/raw/master/data/games.csv
# Re-run any affected analysis script
```

To refresh win totals: re-run `cb_wr_matchup.py`'s scrape block, or hand-edit `data/raw/win_totals_2026.csv`.

## File Map

```
analysis/schedule_2026/
├── README.md                     # this file
├── _shared/
│   ├── nflverse.py
│   ├── teams.py
│   └── output.py
├── data/raw/                     # gitignored; downloaded data
├── scripts/                      # 15 analysis scripts
└── output/<slug>/
    ├── data.parquet              # primary result
    ├── chart.png                 # matplotlib visualization
    └── findings.md               # ~200-word writeup with specific numbers
```
