# International Return-Week Dip

**Question:** Do NFL teams underperform vs. Vegas the week after playing an international game?

## Historical effect (2007-2025, regular season)

- International games found: **54** (Wembley/Tottenham/Twickenham, Munich, Frankfurt, Mexico City, Sao Paulo, plus the Bills Toronto series).
- Return-week team-games with Vegas line and final score: **n = 107**.
- **Return-week ATS cover rate: 51.4%** vs. league baseline 50.0% (n=9,704) -> delta **+1.4 pp**.
- **Return-week avg margin: +0.23** vs. baseline +0.00 -> delta **+0.23 pts**.

The historical signal is **small and statistically noisy**. Cover rate sits within roughly one standard error of 50% at this sample size (SE ~= 4.8 pp). The often-cited "international hangover" is, at most, a modest tilt -- not a clean edge. Most international participants get bye weeks attached, which appears to wash out any travel fatigue.

## 2026 schedule -- nine affected return-week games

The 2026 slate has the most international games in NFL history (9). Each affects two teams' next game:

- **LA** (intl W1 Melbourne Cricket Ground) -> W2 vs NYG
- **SF** (intl W1 Melbourne Cricket Ground) -> W2 vs MIA
- **DAL** (intl W3 Maracana Stadium) -> W4 @ HOU
- **BAL** (intl W3 Maracana Stadium) -> W4 vs TEN
- **WAS** (intl W4 Tottenham Hotspur Stadium) -> W5 vs NYG
- **IND** (intl W4 Tottenham Hotspur Stadium) -> W5 @ PIT
- **JAX** (intl W5 Tottenham Hotspur Stadium) -> W6 vs HOU
- **PHI** (intl W5 Tottenham Hotspur Stadium) -> W6 vs CAR
- **JAX** (intl W6 Wembley Stadium) -> W8 vs IND
- **HOU** (intl W6 Wembley Stadium) -> W7 vs NYG
- **NO** (intl W7 Stade de France) -> W9 vs CLE
- **PIT** (intl W7 Stade de France) -> W8 vs CLE
- **ATL** (intl W9 Bernabeu) -> W10 vs KC
- **CIN** (intl W9 Bernabeu) -> W10 vs PIT
- **DET** (intl W10 FC Bayern Munich Stadium) -> W11 vs TB
- **NE** (intl W10 FC Bayern Munich Stadium) -> W12 @ LAC
- **SF** (intl W11 Estadio Banorte) -> W12 vs SEA
- **MIN** (intl W11 Estadio Banorte) -> W12 vs ATL

## Recommendation

Given the muted historical effect, treat the return week as a **soft fade**, not a hard rule. The cleanest spots to fade are teams whose international game was a **true road trip** (the away team) AND whose return-week game is **also on the road** (compounding travel). For 2026 those teams to watch are: **BAL, CIN, DAL, HOU, IND, MIN, NE, PHI, PIT, SF**. Avoid over-fading anchor stars on teams that get a bye week between the international trip and the return game (check `weeks_off` column in data.parquet).
