"""End-to-end match funnel runner: load data, enrich, run stages, dispatch auditor."""
import json
import sys
from pathlib import Path
import pandas as pd

from analysis.late_round_eval.extraction.enrich_birthdays import (
    enrich_with_birthdays, load_sleeper_db,
)
from analysis.late_round_eval.extraction.match_funnel import run_funnel
from analysis.late_round_eval.extraction.audit import (
    sample_for_audit, build_auditor_prompt, parse_auditor_result,
)


OUTPUT_DIR = Path("analysis/late_round_eval/extraction/output")


def main(skip_auditor: bool = False):
    # Load harmonized guide data
    guide = pd.read_parquet(OUTPUT_DIR / "harmonized.parquet")
    # Filter to WR/RB only for matching purposes (eval scope)
    guide = guide[guide["position"].isin(["WR", "RB"])].reset_index(drop=True)

    # Load NFL data — produced by data_pipeline.R (Task 9 prereq).
    # Schema: name, position, birth_date, draft_year, college, player_id
    nfl = pd.read_parquet(OUTPUT_DIR / "nfl_universe.parquet")

    # Load Sleeper for birthday enrichment
    sleeper_db = load_sleeper_db()

    # Enrich guide with birthdays
    nfl_birthdays = nfl[["name", "position", "birth_date"]].rename(columns={"birth_date": "birth_date"})
    guide_enriched = enrich_with_birthdays(guide, sleeper_db, nfl_birthdays)

    # Conflict warnings
    n_conflicts = guide_enriched["birthday_conflict"].sum()
    if n_conflicts:
        print(f"WARNING: {n_conflicts} birthday conflicts (dropped birthday for those rows)")

    # Auditor function: dispatch one subagent per stage
    auditor_calls = []
    def auditor_fn(stage_num: int, candidates: pd.DataFrame) -> pd.DataFrame:
        if skip_auditor:
            return pd.DataFrame()
        sample = sample_for_audit(candidates)
        prompt_path = OUTPUT_DIR / f"auditor_prompt_stage_{stage_num}.txt"
        result_path = OUTPUT_DIR / f"auditor_fps_stage_{stage_num}.json"
        prompt = build_auditor_prompt(stage_num, sample, str(result_path))
        prompt_path.write_text(prompt)
        auditor_calls.append({"stage": stage_num, "prompt_path": str(prompt_path),
                              "result_path": str(result_path)})
        # When skip_auditor is False, the human/orchestrator must dispatch the
        # auditor agent against prompt_path and produce result_path before this
        # function continues. For automation, this is implemented as a pause +
        # poll. For the plan we run it manually (see Task 8 Step 4).
        print(f"\n=== AUDITOR NEEDED FOR STAGE {stage_num} ===")
        print(f"Dispatch agent with prompt at: {prompt_path}")
        print(f"Wait for result file at: {result_path}")
        input("Press Enter once result file is written...")
        return parse_auditor_result(str(result_path))

    matches, unmatched = run_funnel(guide_enriched, nfl, auditor_fn=auditor_fn)

    # Write outputs
    matches.to_parquet(OUTPUT_DIR / "matches.parquet", index=False)
    unmatched.to_csv(OUTPUT_DIR / "manual_review.csv", index=False)

    total = len(guide_enriched)
    matched = len(matches)
    print(f"\nMatched: {matched}/{total} ({100*matched/total:.1f}%)")
    print(f"Manual review: {len(unmatched)}")
    print(f"By stage:\n{matches['match_stage'].value_counts().sort_index().to_string()}")


if __name__ == "__main__":
    main(skip_auditor="--skip-auditor" in sys.argv)
