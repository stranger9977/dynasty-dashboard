# Late Round Prospect Guide — Evaluation Pipeline

**Date:** 2026-05-16
**Status:** Draft for review
**Owner:** nick

## Goal

Evaluate Late Round Fantasy's annual rookie guide (2022–2025 classes; 2026 listed but not evaluated yet) against NFL fantasy production. Quantify whether his tier calls add information beyond what NFL draft capital + age already encode, identify the position and round where he's strongest, and assess his late-round (day-3 + UDFA) sleeper detection.

## Scope

**In:** WR and RB only. Classes 2022, 2023, 2024 (full Y1–Y3 windows), 2025 (Y1 only, flagged), 2026 (rankings displayed, not evaluated).

**Out:** TE (sample too small), QB (different evaluation framework), TE/QB tier mapping. Multi-guide aggregation (this is single-source). Year-over-year prediction drift modeling.

## Inputs

Five PDFs currently at `/Users/nick/Desktop/late_round_guides/`:

| File | Class year | Version |
|---|---|---|
| `LateRoundProspectGuide22_V3.pdf` | 2022 | V3 |
| `LateRoundProspectGuide_PostDraftV6.pdf` | 2023 (assumed — confirm on extract) | Post-Draft V6 |
| `LateRoundProspectGuide24_PostDraftV2.pdf` | 2024 | Post-Draft V2 |
| `LateRoundProspectGuide2025_V2.pdf` | 2025 | V2 |
| `LateRoundProspectGuide26_PostDraft.pdf` | 2026 | Post-Draft |

PDFs are moved into the repo at `analysis/late_round_eval/guides/YYYY_lateround.pdf`.

External data via `nflreadr` (cached parquet under `analysis/late_round_eval/data/`):
- `load_draft_picks(season)` — NFL draft round/pick → `draft_capital`
- `load_rosters(season)` — UDFA detection, birthdate enrichment
- `load_player_stats(season, stat_type="offense")` — weekly FFPPG
- `load_ff_playerids()` — ID crosswalk for joining
- `data/sleeper_players.json` (already in repo) — secondary birthdate source

## Architecture

Three stages, each producing committed artifacts so downstream stages are deterministic.

```
analysis/late_round_eval/
├── guides/                              # input PDFs
├── extraction/
│   ├── extract_guide.py                 # stage 1: PDF → per-guide JSON via subagents
│   ├── harmonize.py                     # stage 1b: canonical tier map
│   ├── match_funnel.py                  # stage 2: matcher + auditor loop
│   └── output/
│       ├── 2022_players.json
│       ├── 2022_metadata.json
│       ├── ...
│       ├── tier_map.json
│       ├── harmonized.parquet
│       ├── matches.parquet
│       └── manual_review.csv
├── data_pipeline.R                      # stage 3a: join to nflreadr, build eval_df
├── analysis.Rmd                         # stage 3b: model + render
├── analysis.html                        # rendered (committed)
├── charts/                              # PNG outputs (committed)
└── data/                                # cached parquet from nflreadr
```

## Stage 1 — Extraction

**Tooling:** subagents read PDFs natively via the `Read` tool (Claude vision on PDF). `pdftotext -layout` dumps each PDF to text for programmatic validation. Both committed.

**Two-pass design:**

Pass 1 — five parallel subagents, one per PDF. Each returns:
- `players.json`: one row per ranked player
- `metadata.json`: guide-level info (year, version, methodology text, features mentioned, tier definitions)

Per-player schema (Pydantic-validated):
```python
{
  "guide_year": int,
  "name": str,
  "position": Literal["WR", "RB", "TE", "QB"],   # all extracted; filtered to WR/RB downstream
  "original_tier_label": str,                     # verbatim from guide
  "original_tier_rank": int,                      # 1 = highest tier in guide
  "overall_rank": int | None,
  "college": str,
  "blurb": str,                                   # ≤500 chars
  "source_page": int,
  "source_quote": str,                            # ≤120 chars, verbatim
}
```

Pass 2 — one harmonizer subagent reads all five `metadata.json` tier definitions, emits `tier_map.json`:
```python
{("2024", "High-End Starter"): "Starter", ...}
```
Canonical scheme: **Elite / Starter / Flex / Depth / Dart Throw** (5 ordered tiers).

**Anti-hallucination guarantees:**

1. **Schema validation.** Rows missing required fields (incl. `source_page`, `source_quote`) are dropped.
2. **Source-quote grep.** Every `source_quote` must fuzzy-match (SequenceMatcher ≥ 0.95) into the `pdftotext` dump. Failures quarantined to `unverified.json`, never reach modeling.
3. **Name presence.** Player `name` must appear in the dump on `source_page ± 1`.
4. **External cross-check.** Every extracted drafted player must resolve to `load_draft_picks` for the appropriate class. Invented players surface here.
5. **Coverage sanity.** Per-guide row count compared against any in-guide summary table; >30% deviation triggers re-extraction.
6. **Determinism.** Each PDF extracted twice; if row diff >5%, prompt is tightened and all five re-run.
7. **Human spot-check.** Validator outputs `extraction_review.md` with 10 random rows per guide (name | tier | source_quote | page). **User approval gate before stage 2 runs.**

**Contingency:** if quarantine rate >10% for any guide, fall back to per-page subagent (one subagent per 2-page chunk).

**Year inference for `PostDraftV6`.** Subagent reports `guide_year` from cover text; cross-checked against rookies named in the guide (e.g., Bijan Robinson → 2023). User confirms in spot-check.

## Stage 2 — Match funnel

**Goal:** join guide players to NFL identity with high recall and zero false positives.

**Enrichment:** for each guide player, look up birthdate from two independent sources:
- `nflreadr::load_rosters` (NFL post-draft)
- `data/sleeper_players.json` (NFL + many UDFAs)

If both report birthdates and disagree, the disagreement itself is evidence of an upstream mismatch — birthday is dropped as evidence for that candidate and the row is flagged.

**Funnel stages** (ratchet strict → loose, log counts per stage):

| Stage | Key | Notes |
|---|---|---|
| 1 | exact `name` + `position` + birthday | gold |
| 2 | normalized name (strip Jr/Sr/III/punct/diacritics, lowercase) + position + birthday | |
| 3 | fuzzy name (SequenceMatcher ≥ 0.85) + position + birthday exact | nicknames: Ja'Marr/Jamar, Chig/Chigoziem |
| 4 | exact name + position + class year + college | for players without birthday in either source |
| 5 | fuzzy name ≥ 0.85 + position + class year + college | |
| 6 | fuzzy name ≥ 0.80 + position + class year | last resort |
| 7 | unmatched → `manual_review.csv` | human gate |

**Two-agent loop:**

- **Matcher** advances one stage at a time, writes `proposed_matches_stage_N.csv` with evidence columns (`birthday_match`, `college_match`, `position_match`, `fuzzy_score`).
- **Auditor** samples `min(20, 20% of new matches)`, independently verifies via web search and known references, returns `false_positives_stage_N.csv`.
- Loop exit: cumulative match rate ≥ 90% AND auditor returns zero FPs on the most recent stage. Remaining → `manual_review.csv`.
- If auditor reports any FP, matcher tightens (raise fuzzy threshold or add evidence requirement) and retries the stage.

Final output: `matches.parquet` with `(guide_player_id, nfl_player_id, match_stage, evidence_json)`.

## Stage 3 — Evaluation

**Build `eval_df`** (`data_pipeline.R`):

Per matched (drafted or UDFA) WR/RB from classes 2022–2025:

| Column | Source / formula |
|---|---|
| `name`, `position`, `class_year` | from harmonized guide data |
| `canonical_tier` | factor: Elite / Starter / Flex / Depth / Dart Throw (ordered) |
| `age` | `(season_start - birthdate)` in years at start of rookie season |
| `draft_pick` | NFL pick number; UDFAs = 300 (well past last pick of any draft, simplifies cross-year `log` scaling) |
| `draft_capital` | `draft_pick` (`log(draft_capital)` used in models) |
| `draft_round` | factor: 1, 2, 3, "day-3" (4–7), "UDFA" |
| `college` | from guide |
| `p5_flag` | TRUE if college in P5 conference list for `class_year` |
| `best_ffppg` | max season FFPPG (PPR) across seasons 1–3 post-draft, where a season's FFPPG = total PPR points / games played (`load_player_stats` weekly rows aggregated). Y1-only for 2025 class. |
| `eval_window` | "Y1–Y3" or "Y1-only" (2025 class) |
| `hit_flag` | `best_ffppg ≥ 10` |
| `elite_flag` | `best_ffppg ≥ 15` |
| `bust_flag` | `best_ffppg < 5` OR out of league by end of Y3 |

PPR scoring sourced from `config.py` (PPR=1.0).

**P5 list (by year, accounting for realignment):**
- 2022–2023: SEC, Big Ten, Big 12, ACC, Pac-12, plus Notre Dame
- 2024+: SEC, Big Ten, Big 12, ACC, plus Notre Dame (Pac-12 collapse)

**Models, fit separately per position (WR, RB):**

```r
# Regression — does his tier add over age + draft capital?
baseline_reg <- lm(best_ffppg ~ age + log(draft_capital), data = eval_df)
guide_reg    <- lm(best_ffppg ~ age + log(draft_capital) + canonical_tier, data = eval_df)
# Compare: adj R², MAE, RMSE, nested F-test

# Classification — does his tier label beat ordinal logistic on the same predictors?
baseline_clf <- MASS::polr(canonical_tier ~ age + log(draft_capital), data = eval_df)
# His "model" = canonical_tier itself, treated as ordinal score 1–5 for AUC ranking
```

**Year is NOT a feature in either model.** Both models share the same predictor base (age + log draft capital); guide model adds his canonical_tier. Year-FE versions computed once as a sensitivity panel in the appendix.

**Metrics:**

Regression: adj R², MAE, RMSE, nested F-test p-value, ΔR² (guide − baseline).

Classification: accuracy, weighted F1, quadratic-weighted kappa, macro one-vs-rest AUC (binary AUC per tier, macro-averaged), confusion matrix.

Production-threshold AUC (bonus): binarize `best_ffppg` at ≥10 and ≥15; compute AUC of `predict(baseline_reg)` and of `as.integer(canonical_tier)` against each threshold.

**Slices** (every metric replicated for):
1. Position (WR | RB) — primary inference, always reported
2. Draft round (1 | 2 | 3 | day-3 | UDFA) — marginal slice within each position
3. P5 vs non-P5 — marginal slice within each position
4. Late-round subset (day-3 + UDFA) — answers the explicit "sleeper detection" question

For the slice heatmap (section 7 of the report) only, all three dimensions are crossed (2 × 5 × 2 = 20 cells); empty cells shown as gray. Tables stay marginal to preserve sample sizes.

Headline inference uses pooled WR and pooled RB; slice tables are descriptive (no multiple-testing correction).

## Report layout — `analysis.html`

Single Rmd render with floating TOC. Sections:

1. **Executive summary** — headline ΔR², Δkappa, ΔAUC per position; one-sentence verdict per position; sleeper-detection headline (day-3 + UDFA only).
2. **Methodology evolution 2022–2025** — per-year narrative, features-mentioned table (rows = features × cols = years × cells ✓/✗), tier-label drift visualization (Sankey or stacked bar).
3. **Coverage 2022–2026** — players per year × position × canonical tier (stacked bars); match funnel results; 2026 noted as rankings-only.
4. **Production by tier** — per canonical tier × position: mean/median/IQR FFPPG, hit rate, bust rate. Boxplots. Faceted by year as drift-check secondary chart. Day-3+UDFA subset chart.
5. **Regression model comparison** — adj R², MAE, RMSE side-by-side; nested F-test; residual plots; coefficient table for `guide_reg`.
6. **Classification model comparison** — accuracy, weighted F1, kappa, macro AUC OvR; confusion matrices; production-threshold AUC.
7. **Slices** — same metrics faceted by position × draft round × P5; heatmap of ΔR² by slice.
8. **Sleeper detection deep dive** — day-3 + UDFA only. Hit rate on "Starter or better" calls vs base rate. Lift curve: order day-3+UDFA players by his canonical tier, plot cumulative hits vs ranking by draft capital alone. Named examples of biggest hits and misses.
9. **Year-by-year scorecard** — per year, table of his calls sorted by rank with realized FFPPG.
10. **Sensitivity appendix** — year-FE variant; 2025-class inclusion/exclusion; extraction quarantine + unmatched counts.

Charts: `ggplot2` + `patchwork`. PNG to `analysis/late_round_eval/charts/` (committed).

## Testing strategy

| Layer | Test |
|---|---|
| Extraction | Pydantic schema. Source-quote fuzzy ≥0.95 against pdftotext dump. Coverage count vs guide-stated total. Determinism (run twice, diff ≤5%). |
| Match funnel | Auditor zero-FP gate at each stage. Target: `manual_review.csv` ≤10% of total (soft target — pipeline continues with note in report if exceeded; not a hard halt). Per-stage match-rate logged. |
| Data joins | All drafted players resolve to nflreadr or are flagged. Spot-check FFPPG calc: Puka Nacua 2023 ≈ 17 PPR/g (105 rec / 1486 yds / 6 TD in 17 games). |
| Models | Per position: `nrow(eval_df) > 0`, baseline R² ∈ [0.10, 0.40], no `NA` coefficients. Snapshot test: committed model summary JSON; CI flags diffs. |
| Report | Rmd renders without warnings. Anchor links resolve. Expected chart count. |

## Reproducibility

`data_pipeline.R` caches intermediate parquet at each stage. Rmd can re-render from cache without re-fetching nflreadr. Extraction outputs (per-guide JSON, `tier_map.json`, `harmonized.parquet`, `matches.parquet`) committed so future runs are deterministic from the same PDFs.

## Risks & contingencies

| Risk | Mitigation |
|---|---|
| Extraction hallucination | Verbatim source-quote requirement, fuzzy-match validation, external nflreadr cross-check, human spot-check gate before stage 2. |
| Mismatched players (false positive) | Two-agent matcher/auditor loop with zero-FP exit criterion; birthday-anchored stages first. |
| Tier scheme doesn't fit canonical 5 cleanly | `tier_map.json` is committed and human-reviewable; harmonizer flags ambiguous mappings for manual override. |
| Sample too small per slice | Headline metrics report on pooled position; slices are descriptive only, noted in report. |
| 2026 PDF format differs from prior years | Extraction subagent is per-PDF, so format drift only breaks one guide at a time; spot-check catches it. |
| `polr` fails on small per-position samples | Documented fallback to multinomial logit (`nnet::multinom`); both metrics reported if so. |

## Out of scope (explicitly)

- TE and QB evaluation (sample size / different framework).
- Year-over-year prediction drift modeling (which year is "best").
- Comparing against other ranker sources (KTC, FantasyCalc) — separate analysis.
- Live integration into the Streamlit app — this is a one-shot analysis report; integration is a follow-up if findings warrant it.
