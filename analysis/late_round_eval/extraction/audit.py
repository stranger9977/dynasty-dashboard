"""Auditor subagent prompt and result handling for match funnel."""
import json
import random
from pathlib import Path
import pandas as pd


AUDITOR_PROMPT_TEMPLATE = """\
You are auditing proposed player matches for false positives.

A sample of {n} proposed matches from match-funnel stage {stage_num} is below.
For each, independently verify that the guide player and NFL player are the SAME person.

Use WebSearch or your training knowledge. Pay attention to:
- Same college program in same era
- Position consistency
- Draft year alignment
- Distinct players with similar names (e.g., there are multiple "Mike Williams" WRs in NFL history)

Proposed matches (CSV):
{csv}

Return a JSON list of FALSE POSITIVES (matches that are wrong). Each FP entry:
  {{"name": "...", "position": "...", "reason": "brief explanation"}}

If no false positives, return [].

Write your output to: {output_path}
"""


def sample_for_audit(candidates: pd.DataFrame, sample_size: int = 20, seed: int = 42) -> pd.DataFrame:
    """Sample min(sample_size, 20% of candidates, len(candidates)) rows."""
    n = min(sample_size, max(int(0.2 * len(candidates)), 1), len(candidates))
    return candidates.sample(n=n, random_state=seed)


def build_auditor_prompt(stage_num: int, sample: pd.DataFrame, output_path: str) -> str:
    cols = ["name", "position", "guide_year", "college", "birthday",
            "player_id", "draft_year", "fuzzy_score"]
    use_cols = [c for c in cols if c in sample.columns]
    csv = sample[use_cols].to_csv(index=False)
    return AUDITOR_PROMPT_TEMPLATE.format(
        n=len(sample), stage_num=stage_num, csv=csv, output_path=output_path,
    )


def parse_auditor_result(output_path: str) -> pd.DataFrame:
    """Read auditor JSON output and return a DataFrame of false positives."""
    text = Path(output_path).read_text()
    fps = json.loads(text)
    if not fps:
        return pd.DataFrame(columns=["name", "position", "reason"])
    return pd.DataFrame(fps)
