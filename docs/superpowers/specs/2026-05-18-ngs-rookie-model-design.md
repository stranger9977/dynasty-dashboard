# NGS Rookie Ranking Model — Design

**Date:** 2026-05-18
**Status:** Draft for review
**Owner:** nick
**Sub-project:** 1 of 3 (NGS model; cfbfastR model and ensemble are separate specs)

## Goal

Build a per-position rookie ranking model that predicts best-season PPR FFPG (Y1–Y3) from NFL Next Gen Stats prospect data, and beats both Late Round Fantasy's published tiers (JJ) and an `age + log(draft_pick)` baseline at ranking incoming NFL prospects. Output predictions feed a new "Rookie Rankings" Streamlit view.

This is one of three loosely-coupled sub-projects: this NGS model, a cfbfastR model (separate spec, parallel build), and an ensemble model (third spec, after both above ship). All three share a fixed output schema so they can plug into the same Streamlit view and ensemble interchangeably.

## Scope

**In:** Four positions (WR, RB, TE, QB). Per-position glmnet (elastic net) trained on NGS CSV features. Boruta-SHAP feature selection for WR and RB (hand-picked sets for TE/QB due to small samples). Leave-one-class-out CV across 2023–2025. Predictions parquet + Streamlit view.

**Out:**
- cfbfastR-derived features (separate sub-project).
- Ensemble logic combining NGS and cfbfastR predictions (separate sub-project).
- Y2+ refinement layer using post-draft NGS player-tracking data.
- Models for non-skill positions.
- Live-inference Streamlit (predictions are pre-computed and read from parquet).
- Training years before 2023 (no NGS CSVs available).

## Inputs

Three CSVs in `~/Downloads/{2023,2024,2025}.csv`, to be copied into `analysis/rookie_model/data/ngs_prospect_scores/`. Each is panel data (multiple player-season rows per prospect; deduped to one row per `gsis_player_id`).

Skill-position counts after dedup with non-null `tm_production_score`:

| Year | WR | RB | TE | QB |
|---|---|---|---|---|
| 2023 | 27 | 14 | 17 | 10 |
| 2024 | 32 | 19 | 11 | 9 |
| 2025 | 32 | 30 | 14 | 10 |
| **Total** | **91** | **63** | **42** | **29** |

Columns used:
- IDs: `gsis_player_id`, `tm_full_name`, `tm_position`, `tm_dob`, `tm_college`, `tm_college_conf`
- Draft: `tm_draft_round`, `tm_draft_number_overall`, `tm_draft_year`
- Physical: `tm_height`, `tm_weight`, `tm_arm_length`, `tm_hand_span`, `tm_wing_span`
- Combine: `tm_40_time`, `tm_bench_reps`, `tm_broad_jump`, `tm_20_shuttle`, `tm_3_cone`, `tm_vert_jump`
- Pro-day fallbacks: `tm_proday_dash40`, `tm_proday_3cone`, `tm_proday_bench`, `tm_proday_long_jump`, `tm_proday_ss20`, `tm_proday_vert`
- NGS composites: `tm_athlete_score`, `tm_combine_score`, `tm_size_score`, `tm_production_score`
- Age: `tm_age_sep1`

Existing pipeline reuse:
- `analysis/late_round_eval/extraction/output/harmonized.parquet` — JJ's canonical_tier per matched player
- `analysis/late_round_eval/extraction/output/matches.parquet` — gsis_id ↔ guide player linkage
- `analysis/late_round_eval/data/player_stats.parquet` — NFL weekly stats for computing `best_ffppg_y1_y3`
- `analysis/late_round_eval/data/eval_df.parquet` — already-joined eval frame with production_tier + JJ tier (extend to include NGS predictions)

## Architecture

```
analysis/rookie_model/
├── data/
│   ├── ngs_prospect_scores/
│   │   ├── 2023.csv
│   │   ├── 2024.csv
│   │   └── 2025.csv
│   ├── features.parquet               # stage 1: NGS deduped by gsis_id
│   ├── eval_df_ngs.parquet            # stage 2: features + target + JJ tier + baseline tier
│   ├── boruta_selected_features.json  # stage 3
│   ├── predictions_ngs.parquet        # stage 5: output contract
│   └── model_summary.json             # stage 4: snapshot metrics
├── ingest_ngs.R                 # read CSVs, dedupe by gsis_id, coalesce combine/pro-day
├── feature_engineering.R        # join NFL production target + JJ tier + per-position features
├── select_features.R            # Boruta-SHAP for WR/RB; pass-through hand-picked for TE/QB
├── train.R                      # glmnet per position; main + late-round-specialist; LOO CV
├── predict.R                    # writes predictions_ngs.parquet (schema-validated)
├── analysis.Rmd                 # eval report
├── analysis.html                # rendered (committed)
├── charts/
└── tests_R/
    ├── test-ingest-ngs.R
    ├── test-feature-engineering.R
    ├── test-train.R
    └── test-predict.R
```

```
views/rookie_rankings.py         # new Streamlit view, 4 position tabs
```

## Stage 1 — Ingest

`ingest_ngs.R`:
- Read each year CSV with `readr::read_csv` and column-type spec validated against expected schema.
- Filter to `tm_position %in% c("WR", "RB", "TE", "QB")`.
- Dedupe by `gsis_player_id`, keeping the first non-null score per player across rows.
- Coalesce combine + pro-day: e.g. `dash40 = coalesce(tm_40_time, tm_proday_dash40)`.
- Write `data/features.parquet` with one row per (gsis_player_id, draft_year).

Schema validation tests: column names match expected, dtypes correct, no duplicates after dedup, score columns numeric.

## Stage 2 — Feature engineering

`feature_engineering.R`:
- Join `features.parquet` to NFL `player_stats.parquet` to compute `best_ffppg_y1_y3` per player.
- Join to `matches.parquet` + `harmonized.parquet` to attach JJ's `canonical_tier` where matched.
- Join to `nfl_universe.parquet` for `draft_pick` (UDFA = 300).
- Compute derived features:
  - `log_draft_capital = log(draft_pick)`
  - `age = tm_age_sep1` (already in NGS)
  - `bmi = (weight / (height_in / 39.37)^2)` (rough metric)
  - Conference one-hot (P5: SEC, Big Ten, Big 12, ACC, Notre Dame; plus the realignment fix from `late_round_eval/data_pipeline.R` — reuse `canonicalize_college()` and `p5_flag()`).
- Production tier per position (cutoffs):
  - WR/RB: Elite ≥16.5, Starter 12–16.5, Flex 7–12, Depth 3–7, Dart <3
  - TE: Elite ≥11, Starter 8–11, Flex 5–8, Depth 2–5, Dart <2
  - QB (4pt pass TD): Elite ≥22, Starter 17–22, Flex 13–17, Depth 9–13, Dart <9
  - Add `assign_production_tier_per_position()` helper in `feature_engineering.R`.
- Missingness handling: for each numeric feature, impute with year×position-cohort median; add `<feature>_missing` indicator flag.
- Output: `data/eval_df_ngs.parquet` with one row per (gsis_player_id, draft_year), columns including target, all candidate features, and JJ/baseline tier joins.

## Stage 3 — Feature selection

`select_features.R`:
- **WR, RB:** run `Boruta::Boruta` with `xgboost` importance scores on the candidate feature set. Compute SHAP values via `SHAPforxgboost::shap.values` on the same xgboost auxiliary model. Output per-feature: Boruta status (`Confirmed | Tentative | Rejected`), mean SHAP value, mean abs SHAP. Selected feature set = `Confirmed` features.
- **TE, QB:** skip Boruta-SHAP (samples too small for stable selection). Use these exact hand-picked sets (do not vary at training time):
  - TE: `tm_production_score, tm_athlete_score, age, log_draft_capital, conference_p5, tm_40_time, tm_height, tm_weight`
  - QB: `tm_production_score, age, log_draft_capital, conference_p5, tm_athlete_score`
- Output: `data/boruta_selected_features.json`:
  ```json
  {
    "WR": {"confirmed": [...], "tentative": [...], "rejected": [...], "shap": {...}},
    "RB": {"confirmed": [...], "tentative": [...], "rejected": [...], "shap": {...}},
    "TE": {"hand_picked": [...]},
    "QB": {"hand_picked": [...]}
  }
  ```
- Seeds set explicitly in Boruta and xgboost calls for reproducibility.

## Stage 4 — Training

`train.R`:
- Per position, fit `glmnet` (elastic net, `family = "gaussian"`, target = `best_ffppg`):
  - Inner CV: grid over `alpha ∈ {0, 0.25, 0.5, 0.75, 1.0}` × `glmnet::cv.glmnet` for `lambda` at each alpha. Select the (alpha, lambda.1se) pair minimizing inner-CV MSE. Fixed across positions.
  - Outer CV: leave-one-class-out across 2023/2024/2025 → 3 folds. Each held-out player gets a prediction from a model fit on the other two years.
- Two variants per position:
  - **Main:** trained on full draft-round pool.
  - **Late-round specialist:** trained on `draft_round ∈ {day-3, UDFA}` only.
- Final ship model per position: refit on all three years' data; used to score future classes (2026+ when those CSVs land).
- Snapshot metrics to `data/model_summary.json`:
  - Per (position × variant × fold): R², MAE, RMSE, accuracy, weighted F1, quadratic kappa, off-by-one rate
  - Per (position × variant) pooled: same metrics
  - Coefficients of final ship model (interpretable)

## Stage 5 — Predict

`predict.R`:
- Score every player in `eval_df_ngs.parquet`:
  - LOO held-out prediction (from the fold that didn't see the player) → `is_loo_prediction = TRUE`
  - Final-model prediction (trained on all data) → `is_loo_prediction = FALSE` (for the rankings view, since 2026 will only have this kind)
- Bucket continuous prediction into `predicted_tier` via per-position cutoffs.
- Compute `model_score_0_100 = percent_rank(predicted_ffppg) * 100` within `(position, draft_year)`.
- Write `data/predictions_ngs.parquet`.

**Output schema (CONTRACT — must match cfbfastR and ensemble models)**:

| Column | Type | Notes |
|---|---|---|
| `gsis_player_id` | str | NFL ID |
| `tm_full_name` | str | |
| `position` | enum | WR / RB / TE / QB |
| `draft_year` | int | 2023–2025 for NGS |
| `predicted_ffppg` | float | continuous prediction of best_ffppg_y1_y3 |
| `predicted_tier` | ord factor | derived from predicted_ffppg via per-position cutoffs |
| `model_score_0_100` | float | percentile rank within (position, draft_year) |
| `model_source` | enum | "ngs" for this sub-project |
| `model_version` | str | semver like "ngs-1.0.0" |
| `is_loo_prediction` | bool | TRUE = held-out (used in eval), FALSE = trained-on-all (used in Streamlit) |
| `model_variant` | enum | "main" or "late_round_specialist" |

Schema validated at write time (Pydantic-style assertion in R; if a column is missing or wrong type, fail loudly).

## Stage 6 — Evaluation

`analysis.Rmd`:
- Reuses `run_tier_eval()`, `score_correlations()`, `ranking_quality()`, and chart helpers from `analysis/late_round_eval/models.R` + `charts.R` (source from sibling directory).
- New section: NGS-model-specific feature importance (Boruta confirmation status + mean SHAP for WR/RB; glmnet coefficients for TE/QB).
- Four predictor comparison (one section per position):
  - Baseline (age + log draft capital)
  - JJ canonical_tier (where matched)
  - **NGS model** (from `predictions_ngs.parquet` filtered to `is_loo_prediction = TRUE`)
  - Production tier (truth)
- Per-position sections cover:
  1. LOO CV metrics per year + pooled
  2. Confusion matrix per predictor vs production tier
  3. Per-tier precision/recall/F1
  4. Top-K precision (K = 5, 10, 20, 30) per predictor
  5. Spearman rank correlation per predictor
  6. Cumulative production curve (dynasty drafting view)
  7. Late-round subset: main vs late-round-specialist vs JJ vs baseline
  8. Feature importance
  9. Named NGS-bump examples (where NGS disagrees with baseline; what happened)
- Headline executive summary table comparing the four predictors per position.

## Stage 7 — Streamlit view

`views/rookie_rankings.py`:
- Sidebar nav adds "Rookie Rankings"
- Tabs by position (WR / RB / TE / QB)
- Year selector defaults to latest available class
- Table:
  ```
  Rank | Name | Pos | Team | Round.Pick | College | Conf | NGS pred FFPG | NGS tier | JJ tier | Baseline tier | Agreement
  ```
- Filters: draft round, P5 vs non-P5, predicted tier, NGS-vs-JJ disagreement
- Expandable "Biggest disagreements" panel
- Reads from `analysis/rookie_model/data/predictions_ngs.parquet` (the `is_loo_prediction = FALSE` rows) joined with `harmonized.parquet` for JJ tier display
- For V1, only `model_source = "ngs"` shown. View is designed so adding `"cfb"` and `"ensemble"` source columns is a non-breaking column add.

## Testing strategy

| Layer | Test |
|---|---|
| Ingest | Schema validation per CSV. Dedup correctness: 1 row per gsis_id, scores coalesced from any non-null row. Combine/pro-day coalesce: combine takes precedence, pro-day fills NA. |
| Feature engineering | Imputation: median-imputed values + `<feature>_missing` flag both present. Position-specific production_tier cutoffs correct (TE Elite ≥11, QB Elite ≥22). Conference encoding stable across years. Canonical college handling reuses `late_round_eval`'s `canonicalize_college()`. |
| Feature selection | Reproducibility: same seed → same Boruta-confirmed set. Hand-picked TE/QB sets present. |
| Training | testthat: `nrow(eval_df) > 0` per position per fold. No NA in fitted coefficients. LOO CV runs 3 folds for each (position × variant). Snapshot test: `model_summary.json` round-trips. |
| Predict | Schema validation: every row has all required columns, valid enums. Every training-set player has both an LOO row and a final-model row (2 rows per player). |
| Eval | Reuses `late_round_eval` tests. New: model_tier vs production_tier confusion matrix totals == nrow(eval). |
| Streamlit | Smoke test via Streamlit's headless mode or manual: page renders for each position, table has rows, filters work, no broken references. |

## Reproducibility

- NGS CSVs committed to `analysis/rookie_model/data/ngs_prospect_scores/`
- All intermediate parquet (`features.parquet`, `eval_df_ngs.parquet`, `predictions_ngs.parquet`) committed
- `model_summary.json` committed for snapshot diffing on retraining
- Seeds set explicitly: Boruta (`seed = 1`), xgboost (`seed = 1`), glmnet CV (`set.seed(1)` before each call)
- `model_version` baked into predictions; bump on every retraining

## Risks & contingencies

| Risk | Mitigation |
|---|---|
| Small QB sample (n=29) → glmnet doesn't beat baseline | Documented expectation: QB result may be inconclusive. Late-round-specialist may help if QB sleeper pool is the use case. |
| Boruta-SHAP picks the same trivially-correlated set as baseline (just draft_pick + age) | If selected set is degenerate, fall back to hand-picked set including NGS composites. Documented in spec. |
| Production target compressed: 2024 has Y1–Y2, 2025 has Y1 only | Reported as caveat in eval. When 2024 Y3 / 2025 Y2+ data arrives, retraining is cheap (re-run pipeline, regenerate predictions). |
| NGS production_score correlates almost perfectly with NGS athlete_score for some positions | Boruta-SHAP handles collinearity by picking the more informative one; glmnet elastic net (α=0.5) also handles correlated features. |
| Cfbfastr sub-project changes the output schema mid-build | Schema locked in this spec; cfbfastR spec must adopt it verbatim. Ensemble spec inherits. |
| Streamlit view becomes stale if predictions parquet not regenerated after CSV updates | Document in repo README the retraining cadence (manual; run `train.R` + `predict.R` after dropping new year's CSV). |

## Out of scope (explicitly)

- cfbfastR data pulls or features (Sub-project 2).
- Ensemble/blender logic (Sub-project 3).
- Live inference in Streamlit (no on-demand scoring; users see pre-computed predictions only).
- TE/QB sample augmentation via earlier years (no NGS CSVs available pre-2023).
- Post-draft refinement using NGS NFL-tracking data (separate eventual sub-project).
- Recruiting composite ratings (cfbfastR sub-project may include them).
