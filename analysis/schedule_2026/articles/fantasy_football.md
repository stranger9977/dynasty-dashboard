# 2026 Fantasy Football schedule, decoded — buys, sells, and the matchups that matter

The 2026 NFL schedule is out. Here's what the schedule actually tells you for fantasy — without the recycled "easy SoS / hard SoS" lazy take, and without using last year's FPA as if rosters haven't turned over.

I built two things you don't usually get:

1. A **defensive quality composite** that blends FPA with cap spend, ESPN FPI, and Vegas — so we're not pretending it's still 2024.
2. **Per-position schedule tables** for QB / RB / WR / TE — each one shows your starter's top dynasty option and the slate of defenses they'll see.

Charts and bullets below. Buys, sells, and start-em signals at the bottom.

---

## 1. The defensive quality composite — the foundation

Last year's FPA is noisy. NFL defenses turn over hard every offseason (free agency, draft, scheme/coordinator). So I built a composite per team: **50% recency-weighted 3-yr FPA** + **20% cap spend on defense (OverTheCap)** + **20% ESPN FPI defensive efficiency** + **10% Vegas season win total**.

Higher = stronger defense to play against.

![Defensive Quality Composite](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/defensive_quality/chart.png)

- **Top 5 defenses:** HOU (90.8), KC (85.9), SEA (82.0), CLE (79.8), MIN (79.8).
- **Bottom 5:** WAS (20.5), DAL (21.2), ARI (21.5), TEN (23.4), NYG (25.3).
- HOU is consensus elite (high on all four signals). CLE rates highly on cap+FPI+FPA, but Vegas hasn't priced it in yet — interesting tell.

This composite feeds the next four slides.

---

## 2. Position SoS — composite-adjusted heatmap

Same composite, but per position. Position-specific FPA (50%) does the scheme-fit work; the team-level signals (cap, FPI, WT) provide forward-looking adjustment.

![Position SoS Composite](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/position_sos_composite/chart.png)

- Toughest RB schedules: **CAR, BUF, LV, LAC, CHI**.
- Easiest RB schedules: **PHI, DET, SEA, CLE, MIN**.
- BUF & LV move up the difficulty list when 2026 defensive investment registers — a signal you'd miss with FPA-only.

---

## 3. RB schedule strength — who faces the toughest run defenses?

Each team's top dynasty RB paired with their schedule's avg opposing run defense.

![RB Schedule Strength](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/position_schedules/rb_schedule.png)

- **Toughest schedules:** Chase Brown (CIN), D'Andre Swift (CHI).
- **Softest schedules:** **Saquon Barkley (PHI)** and **Jahmyr Gibbs (DET)** — already-elite RBs getting the soft slate. League-winner setups.
- Bijan Robinson (ATL) right in the middle.

This is the single biggest piece of bad news for Chase Brown truthers and good news for anyone holding Saquon or Gibbs at near-1.01 redraft cost.

---

## 4. WR schedule strength — vs CB units

Each team's WR1 vs the CB rooms they'll face. CB unit scores use Ourlads depth charts × PFR coverage stats.

![WR Schedule Strength](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/cb_wr_matchup/wr_schedule.png)

- **Toughest:** Metcalf (PIT), Brian Thomas Jr. (JAX), Hunter Renfrow (CAR), Chase (CIN).
- **Easiest:** WRs in LV, KC (Rashee Rice), TEN, IND.
- Spread is narrow — ~10 points — so this is more useful for trade-margin calls than headline-grabbing rankings.

---

## 5. TE schedule strength — schedule-dependent by nature

TE production is famously schedule-driven. A single soft TE-defense week can be the difference between TE1 and TE5 in your league.

![TE Schedule Strength](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/position_schedules/te_schedule.png)

- **Toughest:** Mason Taylor (NYJ), Colston Loveland (CHI), Chig Okonkwo (WAS).
- **Easiest:** **Mark Andrews (BAL)** and **Kyle Pitts (ATL)** — both already-elite TEs with softer slates. Premium hold candidates.

---

## 6. QB schedule strength — vs pass defenses

QB-specific FPA per defense, recency-weighted.

![QB Schedule Strength](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/position_schedules/qb_schedule.png)

- **Toughest QB schedules:** Geno Smith (LV), Aidan O'Connell, Malik Willis, Drake Maye (NE), Caleb Williams (CHI). All in AFC East / NFC North — divisions stacked with good pass defenses.
- **Easiest:** **Jalen Hurts**, Jaxson Dart (NYG), Shedeur Sanders, **Jayden Daniels (WAS)**, Cam Ward. NFC East cluster.

Hurts and Daniels both get top-5 easy schedules. Caleb Williams gets a top-5 tough one. Treat accordingly.

---

## 7. CB/WR matchup index — coverage tier list

Composite team CB unit scores from Ourlads depth chart × PFR coverage stats.

![CB Units](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/cb_wr_matchup/chart.png)

- **Top CB units:** HOU (Stingley + Lassiter), BAL (Wiggins + Awuzie + Humphrey), NE, PHI, PIT.
- **Bottom units:** GB, WAS, ATL, NYG, NYJ.
- WR1s opposite those bottom units have legitimate weekly ceiling lift on schedule alone.

---

## 8. Marquee WR-vs-CB matchups — the cinema games

For the top 40 dynasty WRs, scored every game as WR quality × opposing CB unit. Top 18 reunions of best-vs-best.

![Marquee Matchups](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/cb_wr_matchup/marquee_matchups.png)

- **#1 — Jaxon Smith-Njigba @ DEN, W6.** WR 92 × CB 94. The premier 2026 coverage matchup.
- **#2 — Ja'Marr Chase @ HOU, W2.** WR 93 × CB 92.
- **#3 — Puka Nacua vs DEN, W3.** WR 87 × CB 94.
- Chase appears 5× in the top 18 — CIN's schedule runs through several top CB units. Treat his floor weeks differently than usual.

These are the games to set DFS alerts for, and the weeks to think twice before locking in a marquee WR.

---

## 9. Game-script RB SoS — who plays from in front?

RBs need positive game script to maximize touches. Implied spreads → win probabilities → expected leading-game-share across 17 games.

![Game-script RB](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/game_script_rb/chart.png)

- **Best RB game-script:** BAL (9.24) — 8 games as a 3+ pt favorite, zero as a 3+ pt dog. Henry / Hill ceiling lift.
- SF, DET, PHI, SEA round out the top 5 — Christian McCaffrey, Gibbs, Saquon, Walker.
- **Worst:** MIA (7.37), ARI, LV — 6–8 games projected as 3+ pt underdogs. Caps Achane / Conner / Jeanty volume.

---

## 10. Pace × pace projected play volume

Volume = plays. 3-yr blended team pace × opp defensive pace, with a Vegas-tilt for game-control effects.

![Pace Volume](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/pace_volume/chart.png)

- **Most volume:** DAL (1,092), HOU (1,082), CHI, LA, DET.
- **Least:** LV (971), MIA, NYJ, TEN, ARI.
- ~121-play spread top-to-bottom (~7/game) — meaningful at the margins.

Pass-catcher floors get a real lift in the top 5. Conversely, the bottom 5 get a touch-count discount you should bake into rankings.

---

## 11. Revenge games — top 10 by dynasty value

Two views. **Recent move** — players facing a team they played for in 2024 or 2025:

![Revenge — Recent](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/revenge_games/table.png)

**Drafted team** — career-long reunions, vs the franchise that drafted them:

![Revenge — Drafted](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/revenge_games/table_drafted.png)

- Marquee draft-class revenge: **Saquon vs NYG (W18)**, **A.J. Brown vs TEN (W2)**, **Henry vs TEN (W4)**, **Davante vs GB (W12)**, **D'Andre Swift vs DET (W17)**.
- Marquee recent-move revenge: Waddle (DEN, ex-MIA, W13), Daniel Jones (IND, ex-MIN, W7), DJ Moore (BUF, ex-CHI, W15), Pittman (PIT, ex-IND, W5).

Narrative juice — and weeks worth a small DFS bump if you're inclined.

---

## 12. FF playoffs SoS (Weeks 14–16)

The only weeks that matter. Same FPA methodology filtered to W14–W16.

![FF Playoffs SoS](https://raw.githubusercontent.com/stranger9977/dynasty-dashboard/main/analysis/schedule_2026/output/ff_playoffs_sos/chart.png)

- **Best RB playoff slates:** SF, NYG, WAS.
- **Best WR slates:** ARI*, NE, DEN. **Best TE:** CLE, SEA, DET.
- **⚠ Bye in Week 14:** ARI and DAL. Only 2 of 3 playoff games. Penalize at draft.
- **Worst playoff slates:** NO RBs, TEN WRs, CAR TEs.

---

## Bottom line — signals to act on

**Buy candidates (favorable schedule on top of talent):**
- **Saquon Barkley (PHI)** — easiest RB slate of any top-3 RB.
- **Jahmyr Gibbs (DET)** — same story.
- **Jalen Hurts** — easiest QB schedule in the league.
- **Mark Andrews (BAL)** — top dynasty TE on a softer-than-usual TE-D slate.

**Sell-from-strength candidates:**
- **Chase Brown (CIN)** — toughest run-D schedule in the league.
- **Ja'Marr Chase (CIN)** — 5 marquee matchups in the top 18 = elevated bust weeks.
- **D'Andre Swift (CHI)** — top-5 toughest RB schedule.

**Discount in rankings:**
- **ARI and DAL skill players** — W14 bye = 2 of 3 FF playoff games.
- **MIA / LV RB rooms** (Achane, Jeanty) — projected dog scripts most of the season.
- **Caleb Williams** — top-5 toughest QB pass-D schedule.

**Volume tailwind:**
- **DAL and HOU pass-catchers** — projected highest play volume of any offense.

**Weeks to mark on the FF calendar:**
- **Wk 2:** Chase @ HOU — toughest matchup of his season.
- **Wk 6:** JSN @ DEN — premier WR-vs-CB matchup of 2026.
- **Wk 11 / W14:** revenge-loaded slates.
- **MIN Wk 8–11:** the league's worst opponent gauntlet (DET / BUF / GB / SF).

---

*Charts built from nflverse PBP & schedule data, Vegas win totals via Rotowire/DraftKings, CB depth charts via Ourlads, defensive cap data via OverTheCap, climate via meteostat. Dynasty rankings blend FantasyCalc + KeepTradeCut + LateRound. Code + source on [GitHub](https://github.com/stranger9977/dynasty-dashboard/tree/main/analysis/schedule_2026).*
