# CB/WR Matchup Index — 2026 (v1, team-level)

Per-team CB unit strength derived from 2024-2025 PBP coverage stats applied to current depth charts. CB unit = 0.45·CB1 + 0.35·CB2 + 0.20·Nickel. WR schedule difficulty is the average opposing CB unit score across each WR's 17-game 2026 schedule (higher = tougher).

## Top 5 CB units

- **DEN** (93.9) — Riley Moss / Pat Surtain II / Ja'Quan McMillian
- **HOU** (91.7) — Derek Stingley Jr. / Kamari Lassiter / Jalen Pitre
- **SEA** (91.1) — Devon Witherspoon / Josh Jobe / Nick Emmanwori
- **PIT** (87.4) — Joey Porter Jr. / Jamel Dean / JALEN RAMSEY
- **ATL** (87.0) — Mike Hughes / A.J. Terrell Jr. / Billy Bowman Jr.

## Bottom 5 CB units

- **MIA** (51.4) — Chris Johnson / JuJu Brents / Jason Marshall Jr.
- **ARI** (54.1) — Will Johnson / Kei'Trel Clark / Max Melton
- **KC** (57.0) — Nohl Williams / Mansoor Delane / Kader Kohou
- **LV** (67.1) — Eric Stokes / Darien Porter / Taron Johnson
- **MIN** (67.6) — James Pierre / Isaiah Rodgers / Byron Murphy Jr.

## WR schedule difficulty (top 3 WRs per team)

**Toughest CB schedules:**
- **DK Metcalf** (PIT) — avg opp CB unit 82.2
- **Roman Wilson** (PIT) — avg opp CB unit 82.2
- **Marquez Valdes-Scantling** (PIT) — avg opp CB unit 82.2

**Easiest CB schedules:**
- **Allen Lazard** (NYJ) — avg opp CB unit 72.3
- **Garrett Wilson** (NYJ) — avg opp CB unit 72.3
- **John Metchie III** (NYJ) — avg opp CB unit 72.3

## Scope notes

- **Ourlads scrape:** 31/32 teams returned depth chart data; remaining teams filled from 2025 nflverse rosters (depth_chart_position=='CB'), ordered by jersey number as a proxy for depth.
- **PFR advanced defense was BLOCKED (HTTP 403) for both 2024 and 2025**, so the spec'd CB-quality composite (passer rating allowed, comp%, yards/target) was **replaced with a PBP-derived composite**: pass deflections per game (55%) + interceptions per game (weighted within that 55%) + solo tackles per game (45%). Scores are population percentiles among DBs with >=4 weighted games of PBP activity in 2024-2025; weighting 2025=0.6, 2024=0.4. Players below the activity threshold default to 50 (median).
- **CB-name match rate:** 86/96 (90%); 10 slots defaulted to 50. Rookies and lightly-used CBs are the main miss categories.
- **WR list:** top 3 WRs per team from 2025 rosters, ordered by jersey number (no separate per-route or snap-share data used).
