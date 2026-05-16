# Late Round Prospect Guide Evaluation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an Rmd → HTML report at `analysis/late_round_eval/analysis.html` that evaluates Late Round Fantasy's 2022–2025 rookie guides (WR + RB) against NFL fantasy production, comparing to an age + log(draft capital) baseline.

**Architecture:** Three stages with committed intermediate artifacts: (1) Python subagent extraction + tier harmonization from 5 PDFs → JSON + harmonized.parquet; (2) Python birthday-anchored matcher/auditor loop → matches.parquet; (3) R nflreadr joins → ordinal classification + linear regression vs baseline → Rmd render.

**Tech Stack:** Python 3.12 (uv) for extraction & matching (Pydantic, rapidfuzz, pdftotext subprocess). R for stats & report (nflreadr, tidyverse, arrow, MASS::polr, pROC, ggplot2 + patchwork, Rmd). Claude subagents via the Agent tool for PDF extraction, tier harmonization, and match auditing.

**Spec:** `docs/superpowers/specs/2026-05-16-late-round-eval-design.md`

---

## File Structure

```
analysis/late_round_eval/
├── guides/
│   ├── 2022_lateround.pdf
│   ├── 2023_lateround.pdf
│   ├── 2024_lateround.pdf
│   ├── 2025_lateround.pdf
│   ├── 2026_lateround.pdf
│   └── text_dumps/
│       └── YYYY_dump.txt              # pdftotext -layout output, committed
├── extraction/
│   ├── __init__.py
│   ├── schemas.py                     # Pydantic models
│   ├── prompts.py                     # subagent prompt templates
│   ├── validate.py                    # source-quote grep, coverage checks
│   ├── orchestrate.py                 # post-subagent aggregation + spot-check report
│   ├── harmonize.py                   # tier_map.json builder + harmonized.parquet
│   ├── match_funnel.py                # matcher stages
│   ├── audit.py                       # auditor prompt + result handling
│   ├── enrich_birthdays.py            # sleeper + nflreadr birthday lookup
│   └── output/
│       ├── 2022_players.json
│       ├── 2022_metadata.json
│       ├── ...
│       ├── tier_map.json
│       ├── harmonized.parquet
│       ├── matches.parquet
│       ├── manual_review.csv
│       └── extraction_review.md
├── tests/
│   ├── __init__.py
│   ├── test_schemas.py
│   ├── test_validate.py
│   ├── test_harmonize.py
│   ├── test_enrich_birthdays.py
│   └── test_match_funnel.py
├── data_pipeline.R                    # nflreadr → eval_df.parquet
├── analysis.Rmd                       # models + render
├── analysis.html                      # rendered (committed)
├── charts/                            # ggplot PNGs (committed)
├── data/                              # cached nflreadr parquet
└── tests_R/
    └── test-data-pipeline.R           # testthat
```

---

## Task 1: Scaffolding, PDF migration, and text dumps

**Files:**
- Create: `analysis/late_round_eval/guides/` (directory)
- Create: `analysis/late_round_eval/guides/text_dumps/` (directory)
- Create: `analysis/late_round_eval/extraction/` (directory)
- Create: `analysis/late_round_eval/extraction/output/` (directory)
- Create: `analysis/late_round_eval/tests/` (directory)
- Create: `analysis/late_round_eval/charts/` (directory)
- Create: `analysis/late_round_eval/data/` (directory)
- Create: `analysis/late_round_eval/tests_R/` (directory)
- Move: 5 PDFs from `~/Desktop/late_round_guides/` to `analysis/late_round_eval/guides/`
- Create: `analysis/late_round_eval/guides/text_dumps/*.txt` (5 files via pdftotext)
- Modify: `pyproject.toml` (add deps)

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p analysis/late_round_eval/{guides/text_dumps,extraction/output,tests,charts,data,tests_R}
touch analysis/late_round_eval/extraction/__init__.py
touch analysis/late_round_eval/tests/__init__.py
```

- [ ] **Step 2: Move and rename PDFs**

The `PostDraftV6` PDF year is unknown; the extraction stage will confirm. Rename as `2023_lateround.pdf` for now (best guess based on V6 numbering following V3=2022). If extraction reveals a different year, rename and rerun.

```bash
mv ~/Desktop/late_round_guides/LateRoundProspectGuide22_V3.pdf analysis/late_round_eval/guides/2022_lateround.pdf
mv ~/Desktop/late_round_guides/LateRoundProspectGuide_PostDraftV6.pdf analysis/late_round_eval/guides/2023_lateround.pdf
mv ~/Desktop/late_round_guides/LateRoundProspectGuide24_PostDraftV2.pdf analysis/late_round_eval/guides/2024_lateround.pdf
mv ~/Desktop/late_round_guides/LateRoundProspectGuide2025_V2.pdf analysis/late_round_eval/guides/2025_lateround.pdf
mv ~/Desktop/late_round_guides/LateRoundProspectGuide26_PostDraft.pdf analysis/late_round_eval/guides/2026_lateround.pdf
ls analysis/late_round_eval/guides/
```

Expected: 5 PDFs listed.

- [ ] **Step 3: Verify pdftotext is available**

```bash
which pdftotext || brew install poppler
pdftotext -v
```

Expected: version string (≥4.x). Install via `brew install poppler` if missing.

- [ ] **Step 4: Generate text dumps**

```bash
for year in 2022 2023 2024 2025 2026; do
  pdftotext -layout "analysis/late_round_eval/guides/${year}_lateround.pdf" "analysis/late_round_eval/guides/text_dumps/${year}_dump.txt"
done
ls -la analysis/late_round_eval/guides/text_dumps/
```

Expected: 5 .txt files, each non-empty (>10KB).

- [ ] **Step 5: Add Python dependencies**

Modify `pyproject.toml` — add to `dependencies` list:

```toml
    "pydantic>=2.0",
    "rapidfuzz>=3.0",
```

Then:

```bash
uv sync
```

Expected: dependencies install cleanly.

- [ ] **Step 6: Commit**

```bash
git add analysis/late_round_eval/ pyproject.toml uv.lock
git commit -m "feat(late-round-eval): scaffold dirs, migrate PDFs, generate text dumps

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Pydantic schemas for extraction output

**Files:**
- Create: `analysis/late_round_eval/extraction/schemas.py`
- Create: `analysis/late_round_eval/tests/test_schemas.py`

- [ ] **Step 1: Write failing test**

Create `analysis/late_round_eval/tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError
from analysis.late_round_eval.extraction.schemas import GuidePlayer, GuideMetadata


def test_guide_player_valid():
    p = GuidePlayer(
        guide_year=2024,
        name="Ladd McConkey",
        position="WR",
        original_tier_label="High-End Starter",
        original_tier_rank=2,
        overall_rank=14,
        college="Georgia",
        blurb="Polished route runner...",
        source_page=23,
        source_quote="2. Ladd McConkey, WR, Georgia",
    )
    assert p.name == "Ladd McConkey"
    assert p.position == "WR"


def test_guide_player_invalid_position():
    with pytest.raises(ValidationError):
        GuidePlayer(
            guide_year=2024,
            name="X",
            position="OL",  # not allowed
            original_tier_label="X",
            original_tier_rank=1,
            overall_rank=1,
            college="X",
            blurb="X",
            source_page=1,
            source_quote="X",
        )


def test_guide_player_missing_source_quote_rejected():
    with pytest.raises(ValidationError):
        GuidePlayer(
            guide_year=2024,
            name="X",
            position="WR",
            original_tier_label="X",
            original_tier_rank=1,
            overall_rank=1,
            college="X",
            blurb="X",
            source_page=1,
            # source_quote missing
        )


def test_guide_player_blurb_max_length():
    with pytest.raises(ValidationError):
        GuidePlayer(
            guide_year=2024,
            name="X",
            position="WR",
            original_tier_label="X",
            original_tier_rank=1,
            overall_rank=1,
            college="X",
            blurb="x" * 501,  # exceeds 500
            source_page=1,
            source_quote="X",
        )


def test_guide_metadata_valid():
    m = GuideMetadata(
        guide_year=2024,
        version="Post-Draft V2",
        methodology_text="We use breakout age and dominator...",
        features_mentioned=["age", "breakout age", "dominator"],
        tier_definitions={"Elite": "Top of the class", "Starter": "Likely producer"},
    )
    assert m.guide_year == 2024
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest analysis/late_round_eval/tests/test_schemas.py -v
```

Expected: ImportError or all FAIL.

- [ ] **Step 3: Implement schemas**

Create `analysis/late_round_eval/extraction/schemas.py`:

```python
"""Pydantic models for extracted guide data."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


Position = Literal["WR", "RB", "TE", "QB"]


class GuidePlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_year: int = Field(ge=2022, le=2026)
    name: str = Field(min_length=2, max_length=80)
    position: Position
    original_tier_label: str = Field(min_length=1, max_length=80)
    original_tier_rank: int = Field(ge=1, le=20)
    overall_rank: int | None = Field(default=None, ge=1, le=500)
    college: str = Field(min_length=2, max_length=80)
    blurb: str = Field(max_length=500)
    source_page: int = Field(ge=1, le=500)
    source_quote: str = Field(min_length=1, max_length=120)


class GuideMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_year: int = Field(ge=2022, le=2026)
    version: str
    methodology_text: str
    features_mentioned: list[str]
    tier_definitions: dict[str, str]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest analysis/late_round_eval/tests/test_schemas.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/late_round_eval/extraction/schemas.py analysis/late_round_eval/tests/test_schemas.py
git commit -m "feat(late-round-eval): pydantic schemas for extracted guide data

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Source-quote validation utility

**Files:**
- Create: `analysis/late_round_eval/extraction/validate.py`
- Create: `analysis/late_round_eval/tests/test_validate.py`

- [ ] **Step 1: Write failing test**

Create `analysis/late_round_eval/tests/test_validate.py`:

```python
from analysis.late_round_eval.extraction.validate import (
    source_quote_in_dump,
    name_appears_on_page,
    coverage_count,
)


DUMP = """\
Page 1 content
Some intro text about the guide.

2. Ladd McConkey, WR, Georgia
Polished route runner with elite separation.

3. Brian Thomas Jr., WR, LSU
Big-bodied X with contested catch upside.
"""


def test_source_quote_exact_match():
    assert source_quote_in_dump("2. Ladd McConkey, WR, Georgia", DUMP) is True


def test_source_quote_fuzzy_match():
    # Slight typo: missing comma
    assert source_quote_in_dump("2. Ladd McConkey WR Georgia", DUMP, threshold=0.85) is True


def test_source_quote_no_match():
    assert source_quote_in_dump("99. Someone Fake, WR, Nowhere", DUMP) is False


def test_name_appears_on_page():
    # Pages are 1-indexed in our convention; the dump is one logical page here
    pages = [DUMP]  # list of page strings
    assert name_appears_on_page("Ladd McConkey", pages, page=1, window=1) is True
    assert name_appears_on_page("Someone Fake", pages, page=1, window=1) is False


def test_coverage_count():
    rows = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    assert coverage_count(rows, stated_total=3) == (3, 3, True)
    assert coverage_count(rows, stated_total=5)[2] is False  # below 70% threshold check
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest analysis/late_round_eval/tests/test_validate.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement validation utilities**

Create `analysis/late_round_eval/extraction/validate.py`:

```python
"""Validation utilities for extracted guide data."""
from rapidfuzz import fuzz


def source_quote_in_dump(quote: str, dump: str, threshold: float = 0.95) -> bool:
    """Return True if `quote` appears in `dump` exactly or with fuzzy match >= threshold.

    Slides a window of len(quote) across dump and checks max partial_ratio.
    """
    if quote in dump:
        return True
    # rapidfuzz partial_ratio returns 0-100; convert threshold to that scale
    score = fuzz.partial_ratio(quote, dump) / 100.0
    return score >= threshold


def name_appears_on_page(name: str, pages: list[str], page: int, window: int = 1) -> bool:
    """Return True if `name` appears in any page within [page-window, page+window].

    `pages` is a list of page-string contents indexed from 1 (pages[0] = page 1).
    """
    lo = max(1, page - window)
    hi = min(len(pages), page + window)
    return any(name in pages[i - 1] for i in range(lo, hi + 1))


def coverage_count(rows: list[dict], stated_total: int | None) -> tuple[int, int | None, bool]:
    """Compare extracted row count to a stated total.

    Returns (extracted_count, stated_total, within_tolerance).
    within_tolerance is True if either stated_total is None, or
    extracted >= 0.7 * stated_total (catches gross under-extraction).
    """
    extracted = len(rows)
    if stated_total is None:
        return (extracted, None, True)
    within = extracted >= 0.7 * stated_total
    return (extracted, stated_total, within)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest analysis/late_round_eval/tests/test_validate.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/late_round_eval/extraction/validate.py analysis/late_round_eval/tests/test_validate.py
git commit -m "feat(late-round-eval): source-quote and coverage validation utilities

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Subagent extraction prompts and orchestration

**Files:**
- Create: `analysis/late_round_eval/extraction/prompts.py`
- Create: `analysis/late_round_eval/extraction/orchestrate.py`
- Create: `analysis/late_round_eval/extraction/output/2022_players.json` (live run output)
- Create: `analysis/late_round_eval/extraction/output/2022_metadata.json` (live run output)
- Create: similar for 2023, 2024, 2025, 2026
- Create: `analysis/late_round_eval/extraction/output/extraction_review.md` (spot-check report)

### Static code (unit-tested)

- [ ] **Step 1: Write failing test for prompt builder**

Create `analysis/late_round_eval/tests/test_prompts.py`:

```python
from analysis.late_round_eval.extraction.prompts import build_extraction_prompt


def test_extraction_prompt_includes_pdf_path():
    prompt = build_extraction_prompt(pdf_path="analysis/late_round_eval/guides/2024_lateround.pdf")
    assert "2024_lateround.pdf" in prompt


def test_extraction_prompt_includes_schema_fields():
    prompt = build_extraction_prompt(pdf_path="x.pdf")
    for field in ["name", "position", "original_tier_label", "original_tier_rank",
                  "college", "source_page", "source_quote", "blurb"]:
        assert field in prompt, f"missing field: {field}"


def test_extraction_prompt_includes_anti_hallucination_rules():
    prompt = build_extraction_prompt(pdf_path="x.pdf")
    assert "verbatim" in prompt.lower()
    assert "source_quote" in prompt
    assert "do not invent" in prompt.lower() or "do not hallucinate" in prompt.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest analysis/late_round_eval/tests/test_prompts.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement prompt builder**

Create `analysis/late_round_eval/extraction/prompts.py`:

```python
"""Subagent prompt templates."""

EXTRACTION_PROMPT_TEMPLATE = """\
You are extracting structured data from a fantasy football rookie prospect guide PDF.

PDF: {pdf_path}

Read the PDF using the Read tool. The PDF contains tiered player rankings (e.g.,
"Elite", "High-End Starter", "Dart Throw"). Extract EVERY ranked WR, RB, TE, and
QB. Do NOT include defensive players, kickers, or punters.

For each player, return a JSON row with these fields:
- guide_year (int): year of the guide cover (e.g., 2024)
- name (str): player's full name as written
- position (str): "WR", "RB", "TE", or "QB"
- original_tier_label (str): exact tier label from the guide (verbatim)
- original_tier_rank (int): 1 = highest tier, 2 = next, etc.
- overall_rank (int or null): overall position in the guide if numbered, else null
- college (str): the college listed for this player
- blurb (str): the analysis paragraph for this player, max 500 chars, truncate if longer
- source_page (int): the page number in the PDF where this player appears
- source_quote (str): a VERBATIM string from the PDF, max 120 chars, that contains
  this player's name AND their tier or rank. This will be programmatically validated
  against a text dump of the PDF. If you cannot quote verbatim, omit the player.

Also return guide-level metadata as a separate object:
- guide_year (int)
- version (str): e.g., "Post-Draft V2"
- methodology_text (str): verbatim text of any "Methodology" / "How I evaluate" /
  "Process" section. If none exists, use empty string.
- features_mentioned (list[str]): traits/stats the author cites as inputs to their
  evaluation (e.g., "age", "breakout age", "dominator rating", "athletic testing",
  "draft capital", "target share").
- tier_definitions (dict[str, str]): tier label → definition as written in the guide.

CRITICAL RULES — DO NOT VIOLATE:
1. Do NOT invent players. If you are not sure a player is in the guide, omit them.
2. source_quote MUST be verbatim. Do not paraphrase. Do not normalize punctuation.
3. Do NOT hallucinate tier labels. Only use labels that appear in the guide.
4. If a section is unclear, leave fields empty rather than guessing.

OUTPUT FORMAT:
Write your output to TWO files:
- {players_out_path} (JSON array of player rows)
- {metadata_out_path} (single JSON object with metadata)

Use the Write tool to create both files. Do not print the JSON to stdout —
write it directly to the files.
"""


HARMONIZER_PROMPT_TEMPLATE = """\
You are harmonizing tier labels across multiple fantasy football guides.

Five guides exist, each with its own tier labels. Read the tier_definitions
from these metadata files:
{metadata_paths}

Build a mapping from (year, original_label) → canonical_tier where canonical_tier
is one of: "Elite", "Starter", "Flex", "Depth", "Dart Throw" (in descending order
of expected production).

Guidelines:
- "Elite", "Top Tier", "Round 1 Talent" → Elite
- "High-End Starter", "Starter", "Likely Producer" → Starter
- "Flex Option", "Solid Backup", "Bench Producer" → Flex
- "Depth", "Camp Body", "Roster Hold" → Depth
- "Dart Throw", "Lottery Ticket", "Deep Sleeper", "Long Shot" → Dart Throw

If a guide has fewer than 5 tiers, map them to the most appropriate canonical
levels. If a guide has more than 5, collapse adjacent tiers.

OUTPUT: Write a JSON file to {output_path} with structure:
{{
  "{{year}}": {{"{{original_label}}": "{{canonical_tier}}", ...}},
  ...
}}

Also include a "rationale" key at the top level explaining any non-obvious mappings:
{{"rationale": "For 2023, 'Borderline Starter' was mapped to Flex because..."}}
"""


def build_extraction_prompt(
    pdf_path: str,
    players_out_path: str | None = None,
    metadata_out_path: str | None = None,
) -> str:
    """Build the extraction prompt for one PDF."""
    year = pdf_path.rsplit("/", 1)[-1].split("_")[0]
    if players_out_path is None:
        players_out_path = f"analysis/late_round_eval/extraction/output/{year}_players.json"
    if metadata_out_path is None:
        metadata_out_path = f"analysis/late_round_eval/extraction/output/{year}_metadata.json"
    return EXTRACTION_PROMPT_TEMPLATE.format(
        pdf_path=pdf_path,
        players_out_path=players_out_path,
        metadata_out_path=metadata_out_path,
    )


def build_harmonizer_prompt(metadata_paths: list[str], output_path: str) -> str:
    return HARMONIZER_PROMPT_TEMPLATE.format(
        metadata_paths="\n".join(f"  - {p}" for p in metadata_paths),
        output_path=output_path,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest analysis/late_round_eval/tests/test_prompts.py -v
```

Expected: all PASS.

- [ ] **Step 5: Write failing test for orchestrator aggregation**

Append to `analysis/late_round_eval/tests/test_prompts.py` (or create `test_orchestrate.py`):

```python
import json
from pathlib import Path
from analysis.late_round_eval.extraction.orchestrate import (
    load_and_validate_extraction,
    build_spot_check_report,
)


def test_load_and_validate_drops_invalid_rows(tmp_path):
    players = [
        {
            "guide_year": 2024, "name": "Ladd McConkey", "position": "WR",
            "original_tier_label": "Starter", "original_tier_rank": 2,
            "overall_rank": 14, "college": "Georgia", "blurb": "x",
            "source_page": 23, "source_quote": "2. Ladd McConkey, WR, Georgia",
        },
        {
            "guide_year": 2024, "name": "Bad Row", "position": "WR",
            "original_tier_label": "Starter", "original_tier_rank": 1,
            "overall_rank": 1, "college": "X", "blurb": "x",
            "source_page": 1,
            # source_quote missing — should be dropped
        },
    ]
    players_path = tmp_path / "players.json"
    players_path.write_text(json.dumps(players))

    valid, dropped = load_and_validate_extraction(str(players_path))
    assert len(valid) == 1
    assert valid[0]["name"] == "Ladd McConkey"
    assert len(dropped) == 1


def test_spot_check_report_includes_10_rows_per_year(tmp_path):
    # Build a fake aggregated dataset with 50 rows per year, 3 years
    rows = []
    for year in [2022, 2023, 2024]:
        for i in range(50):
            rows.append({
                "guide_year": year, "name": f"Player {year}-{i}", "position": "WR",
                "original_tier_label": "Starter", "original_tier_rank": 2,
                "overall_rank": i + 1, "college": "X", "blurb": "x",
                "source_page": i + 1, "source_quote": f"Player {year}-{i}",
            })
    md = build_spot_check_report(rows, samples_per_year=10, seed=42)
    for year in [2022, 2023, 2024]:
        assert f"## {year}" in md
    # 30 sample lines total
    assert md.count("| ") >= 30
```

- [ ] **Step 6: Run test to verify it fails**

```bash
uv run pytest analysis/late_round_eval/tests/test_orchestrate.py -v
```

Expected: ImportError.

- [ ] **Step 7: Implement orchestrator**

Create `analysis/late_round_eval/extraction/orchestrate.py`:

```python
"""Aggregation, validation, and spot-check report generation for extraction output."""
import json
import random
from pathlib import Path
from pydantic import ValidationError

from analysis.late_round_eval.extraction.schemas import GuidePlayer
from analysis.late_round_eval.extraction.validate import source_quote_in_dump


def load_and_validate_extraction(players_path: str) -> tuple[list[dict], list[dict]]:
    """Load player rows from JSON and validate against GuidePlayer schema.

    Returns (valid_rows_as_dicts, dropped_rows_as_dicts). Dropped rows include
    the original payload plus a `_validation_error` field.
    """
    raw = json.loads(Path(players_path).read_text())
    valid: list[dict] = []
    dropped: list[dict] = []
    for row in raw:
        try:
            GuidePlayer(**row)
            valid.append(row)
        except ValidationError as e:
            dropped.append({**row, "_validation_error": str(e)})
    return valid, dropped


def validate_against_dump(rows: list[dict], dump_path: str) -> tuple[list[dict], list[dict]]:
    """Filter rows whose source_quote fuzzy-matches into the PDF text dump.

    Returns (verified, unverified).
    """
    dump = Path(dump_path).read_text()
    verified, unverified = [], []
    for row in rows:
        if source_quote_in_dump(row["source_quote"], dump, threshold=0.95):
            verified.append(row)
        else:
            unverified.append({**row, "_reason": "source_quote not found in dump"})
    return verified, unverified


def build_spot_check_report(rows: list[dict], samples_per_year: int = 10, seed: int = 42) -> str:
    """Build a markdown report sampling N rows per year for human review."""
    rng = random.Random(seed)
    lines = ["# Extraction Spot-Check Report",
             "",
             "Each row shows extracted name | tier | source_quote | page. ",
             "Verify the source_quote actually appears on the listed page in the PDF.",
             ""]
    by_year: dict[int, list[dict]] = {}
    for r in rows:
        by_year.setdefault(r["guide_year"], []).append(r)
    for year in sorted(by_year):
        lines.append(f"## {year}")
        lines.append("")
        lines.append("| Name | Position | Tier | Page | Source Quote |")
        lines.append("|---|---|---|---|---|")
        sample = rng.sample(by_year[year], min(samples_per_year, len(by_year[year])))
        for r in sample:
            q = r["source_quote"].replace("|", "\\|")
            lines.append(f"| {r['name']} | {r['position']} | {r['original_tier_label']} | {r['source_page']} | {q} |")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
uv run pytest analysis/late_round_eval/tests/ -v
```

Expected: all PASS.

- [ ] **Step 9: Commit static code**

```bash
git add analysis/late_round_eval/extraction/prompts.py \
        analysis/late_round_eval/extraction/orchestrate.py \
        analysis/late_round_eval/tests/test_prompts.py \
        analysis/late_round_eval/tests/test_orchestrate.py
git commit -m "feat(late-round-eval): extraction prompts and orchestration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

### Live subagent run (manual execution step)

- [ ] **Step 10: Dispatch 5 extraction subagents in parallel**

Use the Agent tool to spawn 5 subagents in a single message (parallel execution). For each year (2022, 2023, 2024, 2025, 2026), spawn one general-purpose agent with the prompt from `build_extraction_prompt(pdf_path=...)`. The subagent's job: read the PDF via the Read tool, write `extraction/output/{year}_players.json` and `{year}_metadata.json`.

Pseudo-invocation (the executor uses Agent with these params):
```
Agent(
  description="Extract {year} late round guide",
  subagent_type="general-purpose",
  prompt=build_extraction_prompt("analysis/late_round_eval/guides/{year}_lateround.pdf"),
)
```

5 agents = 5 simultaneous Agent calls in one message.

- [ ] **Step 11: Validate extraction output**

Create `analysis/late_round_eval/extraction/run_validation.py`:

```python
"""Run validation across all 5 extraction outputs. Writes spot-check report."""
import json
from pathlib import Path

from analysis.late_round_eval.extraction.orchestrate import (
    load_and_validate_extraction,
    validate_against_dump,
    build_spot_check_report,
)


def main():
    output_dir = Path("analysis/late_round_eval/extraction/output")
    dump_dir = Path("analysis/late_round_eval/guides/text_dumps")
    all_verified: list[dict] = []
    summary: list[dict] = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        players_path = output_dir / f"{year}_players.json"
        if not players_path.exists():
            print(f"MISSING: {players_path}")
            continue
        valid, dropped_schema = load_and_validate_extraction(str(players_path))
        verified, unverified = validate_against_dump(valid, str(dump_dir / f"{year}_dump.txt"))
        all_verified.extend(verified)
        summary.append({
            "year": year, "raw": len(valid) + len(dropped_schema),
            "schema_valid": len(valid), "dump_verified": len(verified),
            "dropped_schema": len(dropped_schema), "unverified_quote": len(unverified),
        })
        # Persist unverified for review
        unverified_path = output_dir / f"{year}_unverified.json"
        unverified_path.write_text(json.dumps(dropped_schema + unverified, indent=2))

    print("\nValidation summary:")
    for s in summary:
        print(f"  {s['year']}: raw={s['raw']} valid={s['schema_valid']} verified={s['dump_verified']}")

    review = build_spot_check_report(all_verified)
    (output_dir / "extraction_review.md").write_text(review)
    print(f"\nSpot-check report: {output_dir / 'extraction_review.md'}")
    print("REVIEW THIS FILE BEFORE PROCEEDING TO TASK 5.")


if __name__ == "__main__":
    main()
```

Run:
```bash
uv run python -m analysis.late_round_eval.extraction.run_validation
```

Expected: per-year counts. Any year with `dump_verified < 0.9 * raw` or `raw < 30` warrants re-running that year's extraction with a tightened prompt (or fallback to per-page extraction).

- [ ] **Step 12: Human spot-check gate**

Open `analysis/late_round_eval/extraction/output/extraction_review.md`. Verify by opening the corresponding PDFs at the listed pages that the extracted tier and source_quote are accurate. If any are wrong, re-run the offending year's extraction (Step 10) with a tightened prompt.

**Do not proceed to Task 5 until spot-check passes.**

- [ ] **Step 13: Commit extraction artifacts**

```bash
git add analysis/late_round_eval/extraction/output/ analysis/late_round_eval/extraction/run_validation.py
git commit -m "feat(late-round-eval): committed extraction output for 2022-2026 guides

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Tier harmonization

**Files:**
- Create: `analysis/late_round_eval/extraction/harmonize.py`
- Create: `analysis/late_round_eval/tests/test_harmonize.py`
- Create: `analysis/late_round_eval/extraction/output/tier_map.json` (live run)
- Create: `analysis/late_round_eval/extraction/output/harmonized.parquet` (live run)

- [ ] **Step 1: Write failing test**

Create `analysis/late_round_eval/tests/test_harmonize.py`:

```python
import json
from pathlib import Path
import pandas as pd
import pytest

from analysis.late_round_eval.extraction.harmonize import (
    apply_tier_map,
    build_harmonized_table,
    CANONICAL_TIERS,
)


def test_canonical_tiers_ordered():
    assert CANONICAL_TIERS == ["Elite", "Starter", "Flex", "Depth", "Dart Throw"]


def test_apply_tier_map_basic():
    rows = [
        {"guide_year": 2024, "name": "X", "position": "WR",
         "original_tier_label": "High-End Starter", "original_tier_rank": 2,
         "overall_rank": 1, "college": "C", "blurb": "b",
         "source_page": 1, "source_quote": "X"},
    ]
    tier_map = {"2024": {"High-End Starter": "Starter"}}
    result = apply_tier_map(rows, tier_map)
    assert result[0]["canonical_tier"] == "Starter"


def test_apply_tier_map_missing_mapping_raises():
    rows = [
        {"guide_year": 2024, "name": "X", "position": "WR",
         "original_tier_label": "Mystery Tier", "original_tier_rank": 1,
         "overall_rank": 1, "college": "C", "blurb": "b",
         "source_page": 1, "source_quote": "X"},
    ]
    tier_map = {"2024": {"Other Label": "Starter"}}
    with pytest.raises(KeyError, match="Mystery Tier"):
        apply_tier_map(rows, tier_map)


def test_build_harmonized_table(tmp_path):
    rows = [
        {"guide_year": 2024, "name": "A", "position": "WR",
         "original_tier_label": "Elite", "original_tier_rank": 1,
         "overall_rank": 1, "college": "C", "blurb": "b",
         "source_page": 1, "source_quote": "A"},
        {"guide_year": 2024, "name": "B", "position": "RB",
         "original_tier_label": "Dart Throw", "original_tier_rank": 5,
         "overall_rank": 50, "college": "C", "blurb": "b",
         "source_page": 50, "source_quote": "B"},
    ]
    tier_map = {"2024": {"Elite": "Elite", "Dart Throw": "Dart Throw"}}
    df = build_harmonized_table(rows, tier_map)
    assert len(df) == 2
    assert set(df["canonical_tier"]) == {"Elite", "Dart Throw"}
    # ordered factor
    assert df["canonical_tier"].dtype.name == "category"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest analysis/late_round_eval/tests/test_harmonize.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement harmonizer**

Create `analysis/late_round_eval/extraction/harmonize.py`:

```python
"""Tier harmonization: per-year labels → canonical 5-tier scheme."""
import json
from pathlib import Path
import pandas as pd


CANONICAL_TIERS = ["Elite", "Starter", "Flex", "Depth", "Dart Throw"]


def apply_tier_map(rows: list[dict], tier_map: dict) -> list[dict]:
    """Attach canonical_tier to each row based on (year, original_label) lookup.

    Raises KeyError if a row's tier label is not in the map.
    """
    out = []
    for r in rows:
        year_key = str(r["guide_year"])
        year_table = tier_map.get(year_key) or tier_map.get(int(year_key))
        if year_table is None:
            raise KeyError(f"No tier mapping for year {year_key}")
        label = r["original_tier_label"]
        if label not in year_table:
            raise KeyError(f"Unmapped tier label '{label}' for year {year_key}")
        out.append({**r, "canonical_tier": year_table[label]})
    return out


def build_harmonized_table(rows: list[dict], tier_map: dict) -> pd.DataFrame:
    """Apply tier map and return a DataFrame with canonical_tier as ordered category."""
    mapped = apply_tier_map(rows, tier_map)
    df = pd.DataFrame(mapped)
    df["canonical_tier"] = pd.Categorical(
        df["canonical_tier"], categories=CANONICAL_TIERS, ordered=True
    )
    return df


def load_all_extractions(output_dir: str) -> list[dict]:
    """Load and concatenate all *_players.json files from output_dir."""
    output_path = Path(output_dir)
    rows: list[dict] = []
    for year in [2022, 2023, 2024, 2025, 2026]:
        path = output_path / f"{year}_players.json"
        if path.exists():
            rows.extend(json.loads(path.read_text()))
    return rows


def main():
    output_dir = Path("analysis/late_round_eval/extraction/output")
    tier_map_path = output_dir / "tier_map.json"
    if not tier_map_path.exists():
        raise FileNotFoundError(
            f"{tier_map_path} not found. Run harmonizer subagent first (Task 5 Step 4)."
        )
    tier_map = json.loads(tier_map_path.read_text())
    # Strip rationale key if present
    tier_map = {k: v for k, v in tier_map.items() if k != "rationale"}

    rows = load_all_extractions(str(output_dir))
    df = build_harmonized_table(rows, tier_map)
    out_path = output_dir / "harmonized.parquet"
    df.to_parquet(out_path, index=False)
    print(f"Wrote {len(df)} rows to {out_path}")
    print(df.groupby(["guide_year", "canonical_tier"], observed=True).size().unstack(fill_value=0))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest analysis/late_round_eval/tests/test_harmonize.py -v
```

Expected: all PASS.

- [ ] **Step 5: Dispatch harmonizer subagent**

Use the Agent tool with the prompt from `build_harmonizer_prompt`:

```python
from analysis.late_round_eval.extraction.prompts import build_harmonizer_prompt
prompt = build_harmonizer_prompt(
    metadata_paths=[
        f"analysis/late_round_eval/extraction/output/{y}_metadata.json"
        for y in [2022, 2023, 2024, 2025, 2026]
    ],
    output_path="analysis/late_round_eval/extraction/output/tier_map.json",
)
```

Dispatch one general-purpose Agent with this prompt.

Expected output: `tier_map.json` exists with structure `{"2022": {...}, ..., "rationale": "..."}`.

- [ ] **Step 6: Build harmonized.parquet**

```bash
uv run python -m analysis.late_round_eval.extraction.harmonize
```

Expected: stdout shows row counts per (year × canonical_tier). Visually scan: roughly more Dart Throws than Elites per year; WR + RB row counts ≥ 20 per year for 2022–2024.

- [ ] **Step 7: Commit**

```bash
git add analysis/late_round_eval/extraction/harmonize.py \
        analysis/late_round_eval/tests/test_harmonize.py \
        analysis/late_round_eval/extraction/output/tier_map.json \
        analysis/late_round_eval/extraction/output/harmonized.parquet
git commit -m "feat(late-round-eval): tier harmonization and harmonized.parquet

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Birthday enrichment

**Files:**
- Create: `analysis/late_round_eval/extraction/enrich_birthdays.py`
- Create: `analysis/late_round_eval/tests/test_enrich_birthdays.py`

- [ ] **Step 1: Write failing test**

Create `analysis/late_round_eval/tests/test_enrich_birthdays.py`:

```python
import json
import pandas as pd
import pytest

from analysis.late_round_eval.extraction.enrich_birthdays import (
    lookup_sleeper_birthday,
    enrich_with_birthdays,
)


SLEEPER_FIXTURE = {
    "1234": {"full_name": "Ladd McConkey", "position": "WR", "birth_date": "2001-11-02"},
    "5678": {"full_name": "Bijan Robinson", "position": "RB", "birth_date": "2002-01-30"},
    "9999": {"full_name": "Ja'Marr Chase", "position": "WR", "birth_date": "2000-03-01"},
}


def test_lookup_sleeper_birthday_exact():
    assert lookup_sleeper_birthday("Ladd McConkey", "WR", SLEEPER_FIXTURE) == "2001-11-02"


def test_lookup_sleeper_birthday_apostrophe():
    # Match Jamar Chase (no apostrophe) to Ja'Marr Chase
    assert lookup_sleeper_birthday("Jamar Chase", "WR", SLEEPER_FIXTURE) == "2000-03-01"


def test_lookup_sleeper_birthday_missing():
    assert lookup_sleeper_birthday("Fake Person", "WR", SLEEPER_FIXTURE) is None


def test_enrich_with_birthdays_flags_conflict():
    rows = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "guide_year": 2024},
    ])
    sleeper = SLEEPER_FIXTURE
    nfl_birthdays = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "birth_date": "1999-01-01"},  # conflict
    ])
    enriched = enrich_with_birthdays(rows, sleeper, nfl_birthdays)
    assert enriched.loc[0, "birthday_conflict"] is True
    # When conflict, birthday is set to None
    assert pd.isna(enriched.loc[0, "birthday"])


def test_enrich_with_birthdays_agreement():
    rows = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "guide_year": 2024},
    ])
    nfl_birthdays = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "birth_date": "2001-11-02"},
    ])
    enriched = enrich_with_birthdays(rows, SLEEPER_FIXTURE, nfl_birthdays)
    assert enriched.loc[0, "birthday"] == "2001-11-02"
    assert enriched.loc[0, "birthday_conflict"] is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest analysis/late_round_eval/tests/test_enrich_birthdays.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement enrichment**

Create `analysis/late_round_eval/extraction/enrich_birthdays.py`:

```python
"""Birthday enrichment from Sleeper and nflreadr."""
import json
import unicodedata
from pathlib import Path
import pandas as pd


def normalize_name(name: str) -> str:
    """Lowercase, strip punctuation/diacritics/suffixes, collapse whitespace."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = s.lower()
    for ch in [".", ",", "'", "-"]:
        s = s.replace(ch, "")
    for suffix in [" jr", " sr", " ii", " iii", " iv", " v"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = " ".join(s.split())
    return s


def lookup_sleeper_birthday(name: str, position: str, sleeper_db: dict) -> str | None:
    """Look up a player's birthday in the Sleeper players DB.

    Matches by normalized name + position.
    """
    target = normalize_name(name)
    for _, player in sleeper_db.items():
        if not isinstance(player, dict):
            continue
        if player.get("position") != position:
            continue
        full = player.get("full_name") or ""
        if normalize_name(full) == target:
            return player.get("birth_date")
    return None


def enrich_with_birthdays(
    guide_df: pd.DataFrame,
    sleeper_db: dict,
    nfl_birthdays: pd.DataFrame,
) -> pd.DataFrame:
    """Add `birthday` and `birthday_conflict` columns to guide_df.

    Birthday is set when both sources agree (or only one has it).
    Conflict flag is set when both sources disagree.
    """
    nfl_lookup = {
        (normalize_name(r["name"]), r["position"]): r["birth_date"]
        for _, r in nfl_birthdays.iterrows()
    }

    out = guide_df.copy()
    birthdays: list[str | None] = []
    conflicts: list[bool] = []
    for _, row in out.iterrows():
        sb = lookup_sleeper_birthday(row["name"], row["position"], sleeper_db)
        nb = nfl_lookup.get((normalize_name(row["name"]), row["position"]))
        if sb and nb and sb != nb:
            birthdays.append(None)
            conflicts.append(True)
        elif sb:
            birthdays.append(sb)
            conflicts.append(False)
        elif nb:
            birthdays.append(nb)
            conflicts.append(False)
        else:
            birthdays.append(None)
            conflicts.append(False)
    out["birthday"] = birthdays
    out["birthday_conflict"] = conflicts
    return out


def load_sleeper_db(path: str = "data/sleeper_players.json") -> dict:
    return json.loads(Path(path).read_text())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest analysis/late_round_eval/tests/test_enrich_birthdays.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/late_round_eval/extraction/enrich_birthdays.py \
        analysis/late_round_eval/tests/test_enrich_birthdays.py
git commit -m "feat(late-round-eval): birthday enrichment from sleeper + nflreadr

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Match funnel stages

**Files:**
- Create: `analysis/late_round_eval/extraction/match_funnel.py`
- Create: `analysis/late_round_eval/tests/test_match_funnel.py`

- [ ] **Step 1: Write failing test**

Create `analysis/late_round_eval/tests/test_match_funnel.py`:

```python
import pandas as pd
import pytest

from analysis.late_round_eval.extraction.match_funnel import (
    stage_1_exact_name_position_birthday,
    stage_3_fuzzy_name_position_birthday,
    stage_5_fuzzy_name_position_year_college,
    run_funnel,
)


GUIDE = pd.DataFrame([
    {"name": "Ladd McConkey", "position": "WR", "guide_year": 2024,
     "birthday": "2001-11-02", "college": "Georgia"},
    {"name": "Jamar Chase", "position": "WR", "guide_year": 2021,
     "birthday": "2000-03-01", "college": "LSU"},  # nickname for Ja'Marr Chase
    {"name": "Mystery Player", "position": "RB", "guide_year": 2024,
     "birthday": None, "college": "Nowhere State"},
])

NFL = pd.DataFrame([
    {"player_id": "P1", "name": "Ladd McConkey", "position": "WR",
     "birth_date": "2001-11-02", "draft_year": 2024, "college": "Georgia"},
    {"player_id": "P2", "name": "Ja'Marr Chase", "position": "WR",
     "birth_date": "2000-03-01", "draft_year": 2021, "college": "LSU"},
])


def test_stage_1_matches_exact_birthday():
    matched = stage_1_exact_name_position_birthday(GUIDE, NFL)
    assert len(matched) == 1
    assert matched.iloc[0]["player_id"] == "P1"


def test_stage_3_fuzzy_name_matches_nickname():
    # After stage 1, Ja'Marr / Jamar shouldn't match exactly
    remaining = GUIDE.iloc[[1, 2]].reset_index(drop=True)
    matched = stage_3_fuzzy_name_position_birthday(remaining, NFL)
    assert len(matched) == 1
    assert matched.iloc[0]["name"] == "Jamar Chase"
    assert matched.iloc[0]["player_id"] == "P2"
    assert matched.iloc[0]["fuzzy_score"] >= 0.85


def test_run_funnel_unmatched_goes_to_review():
    matches, unmatched = run_funnel(GUIDE, NFL, auditor_fn=None)
    # First two match, third doesn't
    assert len(matches) == 2
    assert len(unmatched) == 1
    assert unmatched.iloc[0]["name"] == "Mystery Player"


def test_run_funnel_invokes_auditor_per_stage():
    calls = []
    def fake_auditor(stage_num, candidates):
        calls.append((stage_num, len(candidates)))
        return pd.DataFrame()  # no false positives
    matches, unmatched = run_funnel(GUIDE, NFL, auditor_fn=fake_auditor)
    # Auditor was called for each stage that produced new candidates
    assert len(calls) >= 1
    assert all(c[1] > 0 for c in calls)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest analysis/late_round_eval/tests/test_match_funnel.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement match funnel**

Create `analysis/late_round_eval/extraction/match_funnel.py`:

```python
"""Birthday-anchored matcher with stage-by-stage relaxation."""
from typing import Callable
import pandas as pd
from rapidfuzz import fuzz

from analysis.late_round_eval.extraction.enrich_birthdays import normalize_name


def _candidate_join(
    guide: pd.DataFrame,
    nfl: pd.DataFrame,
    keys: list[tuple[str, str]],
    fuzzy_name: bool = False,
    fuzzy_threshold: float = 0.85,
) -> pd.DataFrame:
    """Join guide → nfl using `keys` (each tuple = (guide_col, nfl_col)).

    If fuzzy_name is True, the name pair (first tuple) is matched via SequenceMatcher
    ratio >= fuzzy_threshold instead of exact equality.
    """
    rows = []
    for _, g in guide.iterrows():
        for _, n in nfl.iterrows():
            ok = True
            score = None
            for i, (gcol, ncol) in enumerate(keys):
                gv, nv = g[gcol], n[ncol]
                if pd.isna(gv) or pd.isna(nv):
                    ok = False
                    break
                if i == 0 and fuzzy_name:
                    score = fuzz.ratio(normalize_name(str(gv)), normalize_name(str(nv))) / 100.0
                    if score < fuzzy_threshold:
                        ok = False
                        break
                else:
                    if i == 0:
                        if normalize_name(str(gv)) != normalize_name(str(nv)):
                            ok = False
                            break
                    else:
                        if gv != nv:
                            ok = False
                            break
            if ok:
                merged = {**g.to_dict(), **n.to_dict()}
                merged["fuzzy_score"] = score if score is not None else 1.0
                rows.append(merged)
    return pd.DataFrame(rows)


def stage_1_exact_name_position_birthday(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("birthday", "birth_date")],
        fuzzy_name=False,
    )
    out["match_stage"] = 1
    return out


def stage_2_normalized_name_position_birthday(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("birthday", "birth_date")],
        fuzzy_name=False,
    )
    out["match_stage"] = 2
    return out


def stage_3_fuzzy_name_position_birthday(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("birthday", "birth_date")],
        fuzzy_name=True,
        fuzzy_threshold=0.85,
    )
    out["match_stage"] = 3
    return out


def stage_4_exact_name_position_year_college(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"),
              ("guide_year", "draft_year"), ("college", "college")],
        fuzzy_name=False,
    )
    out["match_stage"] = 4
    return out


def stage_5_fuzzy_name_position_year_college(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"),
              ("guide_year", "draft_year"), ("college", "college")],
        fuzzy_name=True,
        fuzzy_threshold=0.85,
    )
    out["match_stage"] = 5
    return out


def stage_6_fuzzy_name_position_year(guide: pd.DataFrame, nfl: pd.DataFrame) -> pd.DataFrame:
    out = _candidate_join(
        guide, nfl,
        keys=[("name", "name"), ("position", "position"), ("guide_year", "draft_year")],
        fuzzy_name=True,
        fuzzy_threshold=0.80,
    )
    out["match_stage"] = 6
    return out


STAGES: list[tuple[int, Callable]] = [
    (1, stage_1_exact_name_position_birthday),
    (2, stage_2_normalized_name_position_birthday),
    (3, stage_3_fuzzy_name_position_birthday),
    (4, stage_4_exact_name_position_year_college),
    (5, stage_5_fuzzy_name_position_year_college),
    (6, stage_6_fuzzy_name_position_year),
]


def run_funnel(
    guide: pd.DataFrame,
    nfl: pd.DataFrame,
    auditor_fn: Callable | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run all stages sequentially, removing matched players after each stage.

    If auditor_fn is provided, it's called with (stage_num, candidates_df) and
    returns a DataFrame of confirmed false positives. Confirmed FPs are removed
    from accepted matches.

    Returns (all_matches, unmatched_guide_rows).
    """
    remaining = guide.copy().reset_index(drop=True)
    all_matches: list[pd.DataFrame] = []
    for stage_num, fn in STAGES:
        if remaining.empty:
            break
        candidates = fn(remaining, nfl)
        if candidates.empty:
            continue
        if auditor_fn is not None:
            fps = auditor_fn(stage_num, candidates)
            if not fps.empty:
                fp_keys = set(zip(fps["name"], fps["position"]))
                candidates = candidates[
                    ~candidates.apply(lambda r: (r["name"], r["position"]) in fp_keys, axis=1)
                ]
        all_matches.append(candidates)
        matched_names = set(zip(candidates["name"], candidates["position"]))
        remaining = remaining[
            ~remaining.apply(lambda r: (r["name"], r["position"]) in matched_names, axis=1)
        ].reset_index(drop=True)

    matches = pd.concat(all_matches, ignore_index=True) if all_matches else pd.DataFrame()
    return matches, remaining
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest analysis/late_round_eval/tests/test_match_funnel.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit static funnel code**

```bash
git add analysis/late_round_eval/extraction/match_funnel.py \
        analysis/late_round_eval/tests/test_match_funnel.py
git commit -m "feat(late-round-eval): birthday-anchored match funnel

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Auditor agent loop

**Files:**
- Create: `analysis/late_round_eval/extraction/audit.py`
- Create: `analysis/late_round_eval/extraction/run_matching.py`
- Create: `analysis/late_round_eval/extraction/output/matches.parquet` (live run)
- Create: `analysis/late_round_eval/extraction/output/manual_review.csv` (live run)

- [ ] **Step 1: Write the auditor prompt builder**

Create `analysis/late_round_eval/extraction/audit.py`:

```python
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
```

- [ ] **Step 2: Write the match runner**

Create `analysis/late_round_eval/extraction/run_matching.py`:

```python
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
```

- [ ] **Step 3: Smoke test without auditor**

(Cannot run end-to-end yet — depends on `nfl_universe.parquet` from Task 9. Skip and revisit after Task 9 completes.)

For now just verify imports compile:

```bash
uv run python -c "from analysis.late_round_eval.extraction.run_matching import main; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit static auditor code**

```bash
git add analysis/late_round_eval/extraction/audit.py \
        analysis/late_round_eval/extraction/run_matching.py
git commit -m "feat(late-round-eval): auditor prompt and match-funnel runner

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(Auditor live-run and matches.parquet generation happen in Task 10, after `nfl_universe.parquet` is available.)

---

## Task 9: R data pipeline — nflreadr pulls and NFL universe

**Files:**
- Create: `analysis/late_round_eval/data_pipeline.R`
- Create: `analysis/late_round_eval/tests_R/test-data-pipeline.R`
- Create: `analysis/late_round_eval/data/draft_picks.parquet` (live run)
- Create: `analysis/late_round_eval/data/rosters.parquet` (live run)
- Create: `analysis/late_round_eval/data/player_stats.parquet` (live run)
- Create: `analysis/late_round_eval/extraction/output/nfl_universe.parquet` (live run)

- [ ] **Step 1: Verify R packages installed**

```bash
Rscript -e 'pkgs <- c("nflreadr","tidyverse","arrow","testthat","MASS","pROC","ggplot2","patchwork","rmarkdown","knitr"); missing <- pkgs[!pkgs %in% installed.packages()[,"Package"]]; cat("Missing:", paste(missing, collapse=", "), "\n")'
```

Expected: `Missing: ` (empty). If missing, install with `Rscript -e 'install.packages(c(...))'`.

- [ ] **Step 2: Write failing testthat test**

Create `analysis/late_round_eval/tests_R/test-data-pipeline.R`:

```r
library(testthat)
library(arrow)
library(dplyr)

source("analysis/late_round_eval/data_pipeline.R", local = TRUE)

test_that("normalize_name strips Jr/Sr/punct and lowercases", {
  expect_equal(normalize_name("Ja'Marr Chase Jr."), "jamarr chase")
  expect_equal(normalize_name("D.J. Moore"), "dj moore")
  expect_equal(normalize_name("  Pete Carroll  "), "pete carroll")
})

test_that("classify_draft_round buckets correctly", {
  expect_equal(classify_draft_round(1), "1")
  expect_equal(classify_draft_round(2), "2")
  expect_equal(classify_draft_round(3), "3")
  expect_equal(classify_draft_round(4), "day-3")
  expect_equal(classify_draft_round(7), "day-3")
  expect_equal(classify_draft_round(NA), "UDFA")
})

test_that("p5_flag handles realignment", {
  expect_true(p5_flag("Georgia", 2023))
  expect_true(p5_flag("Oregon", 2023))     # Pac-12 in 2023
  expect_false(p5_flag("Oregon", 2024))    # Pac-12 collapsed
  expect_true(p5_flag("Notre Dame", 2024))
  expect_false(p5_flag("Appalachian State", 2024))
})

test_that("compute_best_ffppg picks max season FFPPG in Y1-Y3", {
  stats <- tibble::tribble(
    ~player_id, ~season, ~fantasy_points_ppr, ~games,
    "P1",       2022,    150,                 17,   # 8.82 PPG
    "P1",       2023,    200,                 16,   # 12.5 PPG  <- max
    "P1",       2024,    100,                 12,   # 8.33 PPG
    "P2",       2025,    50,                  10,   # 5.0 PPG
  )
  result <- compute_best_ffppg(stats, draft_year_lookup = c(P1 = 2022, P2 = 2025), max_years = 3)
  expect_equal(round(result$best_ffppg[result$player_id == "P1"], 2), 12.50)
  expect_equal(round(result$best_ffppg[result$player_id == "P2"], 2), 5.00)
})
```

- [ ] **Step 3: Run test to verify it fails**

```bash
Rscript -e 'testthat::test_file("analysis/late_round_eval/tests_R/test-data-pipeline.R")'
```

Expected: errors — `data_pipeline.R` does not exist yet.

- [ ] **Step 4: Implement data_pipeline.R helpers**

Create `analysis/late_round_eval/data_pipeline.R`:

```r
# Late Round Prospect Guide — Evaluation Data Pipeline
# Pulls nflreadr data, joins to harmonized guide players, builds eval_df.
#
# Usage:
#   Rscript analysis/late_round_eval/data_pipeline.R
#
# Outputs:
#   analysis/late_round_eval/data/{draft_picks,rosters,player_stats}.parquet
#   analysis/late_round_eval/extraction/output/nfl_universe.parquet
#   analysis/late_round_eval/data/eval_df.parquet

library(nflreadr)
library(tidyverse)
library(arrow)

DATA_DIR <- "analysis/late_round_eval/data"
EXTRACT_DIR <- "analysis/late_round_eval/extraction/output"
dir.create(DATA_DIR, recursive = TRUE, showWarnings = FALSE)

EVAL_CLASSES <- 2022:2025
STAT_SEASONS <- 2022:2026  # need 3 yrs post-draft for 2022 → 2024; 2025 → 2025 only

# --- Helpers ----------------------------------------------------------------

normalize_name <- function(x) {
  x |>
    str_to_lower() |>
    str_replace_all("[\\.,'\\-]", "") |>
    str_remove_all("\\b(jr|sr|ii|iii|iv|v)\\b") |>
    str_replace_all("\\s+", " ") |>
    str_trim()
}

classify_draft_round <- function(round) {
  case_when(
    is.na(round) ~ "UDFA",
    round == 1 ~ "1",
    round == 2 ~ "2",
    round == 3 ~ "3",
    round %in% 4:7 ~ "day-3",
    TRUE ~ NA_character_
  )
}

# P5 conferences by year (Pac-12 collapsed after 2023)
P5_BY_YEAR <- list(
  `2022` = c("SEC", "Big Ten", "Big 12", "ACC", "Pac-12"),
  `2023` = c("SEC", "Big Ten", "Big 12", "ACC", "Pac-12"),
  `2024` = c("SEC", "Big Ten", "Big 12", "ACC"),
  `2025` = c("SEC", "Big Ten", "Big 12", "ACC"),
  `2026` = c("SEC", "Big Ten", "Big 12", "ACC")
)

# College → conference lookup. Hardcoded for known programs.
# Notre Dame is always P5 (independent but treated as P5).
COLLEGE_CONFERENCE <- tibble::tribble(
  ~college,          ~conference,
  "Alabama",         "SEC",
  "Georgia",         "SEC",
  "LSU",             "SEC",
  "Florida",         "SEC",
  "Tennessee",       "SEC",
  "Auburn",          "SEC",
  "Arkansas",        "SEC",
  "Kentucky",        "SEC",
  "Mississippi",     "SEC",
  "Mississippi State","SEC",
  "Missouri",        "SEC",
  "South Carolina",  "SEC",
  "Texas A&M",       "SEC",
  "Vanderbilt",      "SEC",
  "Texas",           "SEC",        # joined 2024
  "Oklahoma",        "SEC",        # joined 2024
  "Ohio State",      "Big Ten",
  "Michigan",        "Big Ten",
  "Penn State",      "Big Ten",
  "Wisconsin",       "Big Ten",
  "Iowa",            "Big Ten",
  "Minnesota",       "Big Ten",
  "Illinois",        "Big Ten",
  "Indiana",         "Big Ten",
  "Purdue",          "Big Ten",
  "Michigan State",  "Big Ten",
  "Nebraska",        "Big Ten",
  "Maryland",        "Big Ten",
  "Rutgers",         "Big Ten",
  "Northwestern",    "Big Ten",
  "USC",             "Big Ten",    # joined 2024
  "UCLA",            "Big Ten",    # joined 2024
  "Oregon",          "Big Ten",    # joined 2024
  "Washington",      "Big Ten",    # joined 2024
  "Oklahoma State",  "Big 12",
  "Kansas",          "Big 12",
  "Kansas State",    "Big 12",
  "Iowa State",      "Big 12",
  "TCU",             "Big 12",
  "Baylor",          "Big 12",
  "Texas Tech",      "Big 12",
  "West Virginia",   "Big 12",
  "BYU",             "Big 12",
  "Cincinnati",      "Big 12",
  "Houston",         "Big 12",
  "UCF",             "Big 12",
  "Arizona",         "Big 12",     # joined 2024
  "Arizona State",   "Big 12",     # joined 2024
  "Colorado",        "Big 12",     # joined 2024
  "Utah",            "Big 12",     # joined 2024
  "Clemson",         "ACC",
  "Florida State",   "ACC",
  "Miami",           "ACC",
  "North Carolina",  "ACC",
  "NC State",        "ACC",
  "Duke",            "ACC",
  "Wake Forest",     "ACC",
  "Virginia",        "ACC",
  "Virginia Tech",   "ACC",
  "Louisville",      "ACC",
  "Pittsburgh",      "ACC",
  "Boston College",  "ACC",
  "Syracuse",        "ACC",
  "Georgia Tech",    "ACC",
  "California",      "ACC",        # joined 2024
  "Stanford",        "ACC",        # joined 2024
  "SMU",             "ACC",        # joined 2024
  "Stanford",        "Pac-12",     # pre-2024
  "Oregon State",    "Pac-12",
  "Washington State","Pac-12",
  "Notre Dame",      "Independent" # always treat as P5
)

p5_flag <- function(college, year) {
  year_key <- as.character(year)
  p5_confs <- P5_BY_YEAR[[year_key]]
  conf <- COLLEGE_CONFERENCE$conference[match(college, COLLEGE_CONFERENCE$college)]
  ifelse(college == "Notre Dame", TRUE,
         ifelse(!is.na(conf) & conf %in% p5_confs, TRUE, FALSE))
}

compute_best_ffppg <- function(stats, draft_year_lookup, max_years = 3) {
  # stats: long df with player_id, season, fantasy_points_ppr, games
  # draft_year_lookup: named vector or tibble player_id → draft_year
  if (is.list(draft_year_lookup) && !is.null(names(draft_year_lookup))) {
    dy <- tibble(player_id = names(draft_year_lookup),
                 draft_year = as.integer(unname(draft_year_lookup)))
  } else {
    dy <- draft_year_lookup
  }
  stats |>
    left_join(dy, by = "player_id") |>
    mutate(years_post = season - draft_year + 1) |>
    filter(years_post >= 1, years_post <= max_years, games > 0) |>
    mutate(ffppg = fantasy_points_ppr / games) |>
    group_by(player_id) |>
    summarise(best_ffppg = max(ffppg, na.rm = TRUE), .groups = "drop")
}

# --- Pulls ------------------------------------------------------------------

pull_data <- function() {
  cat("Pulling draft picks (2022-2026)...\n")
  draft_picks <- load_draft_picks(seasons = EVAL_CLASSES) |>
    select(season, round, pick, pfr_player_id, gsis_id, full_name = pfr_player_name,
           position = position, team, college = college)
  write_parquet(draft_picks, file.path(DATA_DIR, "draft_picks.parquet"))

  cat("Pulling rosters (2022-2026)...\n")
  rosters <- load_rosters(seasons = EVAL_CLASSES) |>
    select(season, gsis_id, full_name, position, birth_date,
           entry_year, draft_number, college) |>
    distinct(gsis_id, .keep_all = TRUE)
  write_parquet(rosters, file.path(DATA_DIR, "rosters.parquet"))

  cat("Pulling weekly player stats (2022-2026)...\n")
  player_stats <- load_player_stats(seasons = STAT_SEASONS, stat_type = "offense") |>
    filter(position %in% c("WR", "RB")) |>
    select(player_id, player_name, position, season, week, fantasy_points_ppr)
  write_parquet(player_stats, file.path(DATA_DIR, "player_stats.parquet"))

  cat("Done with pulls.\n")
}

build_nfl_universe <- function() {
  # Union of drafted players + UDFA rookies from rosters for EVAL_CLASSES
  draft_picks <- read_parquet(file.path(DATA_DIR, "draft_picks.parquet"))
  rosters <- read_parquet(file.path(DATA_DIR, "rosters.parquet"))

  drafted <- draft_picks |>
    filter(position %in% c("WR", "RB")) |>
    inner_join(rosters |> select(gsis_id, birth_date), by = "gsis_id") |>
    transmute(
      player_id = gsis_id,
      name = full_name,
      position,
      birth_date,
      draft_year = season,
      draft_pick = pick,
      college
    )

  # UDFAs: rookies in rosters with no draft pick, first season ∈ EVAL_CLASSES
  udfa <- rosters |>
    filter(position %in% c("WR", "RB"),
           is.na(draft_number),
           entry_year %in% EVAL_CLASSES) |>
    transmute(
      player_id = gsis_id,
      name = full_name,
      position,
      birth_date,
      draft_year = entry_year,
      draft_pick = 300,   # UDFA placeholder
      college
    )

  nfl <- bind_rows(drafted, udfa) |> distinct(player_id, .keep_all = TRUE)
  write_parquet(nfl, file.path(EXTRACT_DIR, "nfl_universe.parquet"))
  cat("nfl_universe.parquet:", nrow(nfl), "rows\n")
  nfl
}

build_eval_df <- function() {
  matches <- read_parquet(file.path(EXTRACT_DIR, "matches.parquet"))
  player_stats <- read_parquet(file.path(DATA_DIR, "player_stats.parquet"))

  # Aggregate weekly → season FFPPG
  season_stats <- player_stats |>
    group_by(player_id, season) |>
    summarise(
      fantasy_points_ppr = sum(fantasy_points_ppr, na.rm = TRUE),
      games = n_distinct(week),
      .groups = "drop"
    )

  # matches already contains player_id, draft_year, draft_pick, birth_date
  # from the NFL side of the funnel join.
  draft_year_lookup <- matches |> distinct(player_id, draft_year)
  best_ffppg <- compute_best_ffppg(season_stats, draft_year_lookup, max_years = 3)

  eval_df <- matches |>
    left_join(best_ffppg, by = "player_id") |>
    mutate(
      age = as.numeric(difftime(as.Date(paste0(draft_year, "-09-01")),
                                as.Date(birth_date), units = "days")) / 365.25,
      draft_round = classify_draft_round(
        # back out round from pick; pick 300 = UDFA
        case_when(draft_pick == 300 ~ NA_integer_,
                  draft_pick <= 32 ~ 1L,
                  draft_pick <= 64 ~ 2L,
                  draft_pick <= 96 ~ 3L,
                  draft_pick <= 224 ~ as.integer(ceiling(draft_pick / 32)),
                  TRUE ~ 7L)
      ),
      p5_flag = mapply(p5_flag, college, guide_year),
      best_ffppg = replace_na(best_ffppg, 0),
      hit_flag = best_ffppg >= 10,
      elite_flag = best_ffppg >= 15,
      bust_flag = best_ffppg < 5,
      eval_window = if_else(guide_year == 2025, "Y1-only", "Y1-Y3"),
      canonical_tier = factor(canonical_tier,
                              levels = c("Dart Throw","Depth","Flex","Starter","Elite"),
                              ordered = TRUE)
    ) |>
    filter(guide_year %in% EVAL_CLASSES)  # exclude 2026

  write_parquet(eval_df, file.path(DATA_DIR, "eval_df.parquet"))
  cat("eval_df.parquet:", nrow(eval_df), "rows\n")
  print(eval_df |> count(position, canonical_tier))
  eval_df
}

# --- Main -------------------------------------------------------------------

if (!interactive() && sys.nframe() == 0) {
  pull_data()
  build_nfl_universe()
  if (file.exists(file.path(EXTRACT_DIR, "matches.parquet"))) {
    build_eval_df()
  } else {
    cat("matches.parquet not found — run Task 10 matching before eval_df build.\n")
  }
}
```

- [ ] **Step 5: Run testthat tests to verify they pass**

```bash
Rscript -e 'testthat::test_file("analysis/late_round_eval/tests_R/test-data-pipeline.R")'
```

Expected: all PASS.

- [ ] **Step 6: Run the data pulls (live)**

```bash
Rscript analysis/late_round_eval/data_pipeline.R
```

Expected: `draft_picks.parquet`, `rosters.parquet`, `player_stats.parquet`, `nfl_universe.parquet` all written. `eval_df.parquet` skipped (matches not yet available).

- [ ] **Step 7: Spot-check Puka Nacua FFPPG**

```bash
Rscript -e '
library(arrow); library(dplyr)
stats <- read_parquet("analysis/late_round_eval/data/player_stats.parquet")
puka <- stats |> filter(player_name == "Puka Nacua", season == 2023) |>
  summarise(pts = sum(fantasy_points_ppr), gms = n_distinct(week), ppg = pts/gms)
print(puka)
'
```

Expected: `ppg ≈ 17` (allow 16–18).

- [ ] **Step 8: Commit**

```bash
git add analysis/late_round_eval/data_pipeline.R \
        analysis/late_round_eval/tests_R/test-data-pipeline.R \
        analysis/late_round_eval/data/*.parquet \
        analysis/late_round_eval/extraction/output/nfl_universe.parquet
git commit -m "feat(late-round-eval): R data pipeline and NFL universe pulls

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Run match funnel end-to-end with live auditor

**Files:**
- Create: `analysis/late_round_eval/extraction/output/matches.parquet`
- Create: `analysis/late_round_eval/extraction/output/manual_review.csv`
- Create: `analysis/late_round_eval/data/eval_df.parquet`

- [ ] **Step 1: Run match funnel with auditor**

```bash
uv run python -m analysis.late_round_eval.extraction.run_matching
```

The script pauses at each stage and prints the auditor prompt path. At each pause:
1. Dispatch a general-purpose Agent with the prompt file's contents.
2. The agent writes to the result path (a JSON file of false positives).
3. Press Enter to continue.

Repeat for each stage that produces new candidates. Loop exit: stage 7 (no more candidates) or all-unmatched.

Expected end output:
- `matches.parquet` with ≥ 80% of WR/RB guide players matched
- `manual_review.csv` with the unmatched remainder

If match rate < 80%, inspect `manual_review.csv` and consider:
- College name normalization gaps
- Birthday source disagreements (look at `birthday_conflict` column upstream)
- Hand-mapping notable players via a `manual_overrides.csv` (out of scope for this plan if needed)

- [ ] **Step 2: Build eval_df**

```bash
Rscript -e 'source("analysis/late_round_eval/data_pipeline.R"); build_eval_df()'
```

Expected: `eval_df.parquet` with per-position × canonical_tier counts printed.

- [ ] **Step 3: Spot-check eval_df**

```bash
Rscript -e '
library(arrow); library(dplyr)
df <- read_parquet("analysis/late_round_eval/data/eval_df.parquet")
cat("Total rows:", nrow(df), "\n")
cat("By position × eval_window:\n")
print(df |> count(position, eval_window))
cat("By draft_round:\n")
print(df |> count(draft_round))
cat("Hit/Elite/Bust rates by tier (WR):\n")
print(df |> filter(position == "WR") |>
        group_by(canonical_tier) |>
        summarise(n=n(), hit_rate=mean(hit_flag), elite_rate=mean(elite_flag),
                  bust_rate=mean(bust_flag), .groups="drop"))
'
```

Expected: WR Elite tier has higher hit_rate than WR Dart Throw tier. RB same. If not, something is mis-mapped.

- [ ] **Step 4: Commit**

```bash
git add analysis/late_round_eval/extraction/output/matches.parquet \
        analysis/late_round_eval/extraction/output/manual_review.csv \
        analysis/late_round_eval/extraction/output/auditor_*.json \
        analysis/late_round_eval/data/eval_df.parquet
git commit -m "feat(late-round-eval): matches.parquet from live auditor loop, eval_df built

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 11: Models module (R)

**Files:**
- Create: `analysis/late_round_eval/models.R`
- Create: `analysis/late_round_eval/tests_R/test-models.R`
- Create: `analysis/late_round_eval/data/model_summary.json` (snapshot)

- [ ] **Step 1: Write failing testthat test**

Create `analysis/late_round_eval/tests_R/test-models.R`:

```r
library(testthat)
library(arrow)
library(dplyr)

source("analysis/late_round_eval/models.R", local = TRUE)

set.seed(42)
fake_df <- tibble::tibble(
  position = sample(c("WR", "RB"), 100, replace = TRUE),
  age = runif(100, 21, 25),
  draft_pick = sample(1:262, 100, replace = TRUE),
  canonical_tier = factor(sample(c("Dart Throw","Depth","Flex","Starter","Elite"), 100, replace = TRUE),
                          levels = c("Dart Throw","Depth","Flex","Starter","Elite"), ordered = TRUE),
  best_ffppg = pmax(0, rnorm(100, 8, 5))
)

test_that("fit_regression returns baseline and guide models with metrics", {
  res <- fit_regression(fake_df |> filter(position == "WR"))
  expect_true("baseline" %in% names(res))
  expect_true("guide" %in% names(res))
  expect_true("metrics" %in% names(res))
  expect_true(all(c("adj_r2_baseline", "adj_r2_guide", "delta_r2",
                    "mae_baseline", "mae_guide",
                    "rmse_baseline", "rmse_guide",
                    "f_test_p") %in% names(res$metrics)))
})

test_that("fit_classification returns kappa and AUC", {
  res <- fit_classification(fake_df |> filter(position == "RB"))
  expect_true("metrics" %in% names(res))
  for (m in c("acc_baseline","acc_guide","kappa_baseline","kappa_guide",
              "macro_auc_baseline","macro_auc_guide")) {
    expect_true(m %in% names(res$metrics))
  }
})

test_that("compute_threshold_auc returns AUC for hit and elite thresholds", {
  preds <- runif(100)
  truth_hit <- as.integer(preds > 0.4)
  res <- compute_threshold_auc(preds, fake_df$best_ffppg)
  expect_true("auc_hit" %in% names(res))
  expect_true("auc_elite" %in% names(res))
  expect_true(res$auc_hit >= 0 & res$auc_hit <= 1)
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
Rscript -e 'testthat::test_file("analysis/late_round_eval/tests_R/test-models.R")'
```

Expected: errors — `models.R` missing.

- [ ] **Step 3: Implement models.R**

Create `analysis/late_round_eval/models.R`:

```r
# Late Round Prospect Guide — Modeling
# Per-position regression and classification: baseline vs canonical_tier-augmented.

library(tidyverse)
library(MASS)
library(pROC)

fit_regression <- function(df) {
  df <- df |> filter(!is.na(best_ffppg), !is.na(age), !is.na(draft_pick), !is.na(canonical_tier))
  df$log_capital <- log(df$draft_pick)
  baseline <- lm(best_ffppg ~ age + log_capital, data = df)
  guide    <- lm(best_ffppg ~ age + log_capital + canonical_tier, data = df)

  pred_b <- predict(baseline)
  pred_g <- predict(guide)

  metrics <- list(
    n = nrow(df),
    adj_r2_baseline = summary(baseline)$adj.r.squared,
    adj_r2_guide    = summary(guide)$adj.r.squared,
    delta_r2        = summary(guide)$adj.r.squared - summary(baseline)$adj.r.squared,
    mae_baseline    = mean(abs(df$best_ffppg - pred_b)),
    mae_guide       = mean(abs(df$best_ffppg - pred_g)),
    rmse_baseline   = sqrt(mean((df$best_ffppg - pred_b)^2)),
    rmse_guide      = sqrt(mean((df$best_ffppg - pred_g)^2)),
    f_test_p        = anova(baseline, guide)$`Pr(>F)`[2]
  )

  list(baseline = baseline, guide = guide, metrics = metrics, df = df,
       pred_baseline = pred_b, pred_guide = pred_g)
}

quadratic_weighted_kappa <- function(actual, predicted, levels) {
  # 5x5 weight matrix; weight = (i-j)^2 / (k-1)^2
  k <- length(levels)
  a <- factor(actual, levels = levels)
  p <- factor(predicted, levels = levels)
  o <- table(a, p)
  # expected matrix
  rs <- rowSums(o); cs <- colSums(o); n <- sum(o)
  e <- outer(rs, cs) / n
  w <- outer(seq_len(k), seq_len(k), function(i, j) (i - j)^2 / (k - 1)^2)
  1 - sum(w * o) / sum(w * e)
}

fit_classification <- function(df) {
  df <- df |> filter(!is.na(best_ffppg), !is.na(age), !is.na(draft_pick), !is.na(canonical_tier))
  df$log_capital <- log(df$draft_pick)
  tier_levels <- c("Dart Throw","Depth","Flex","Starter","Elite")

  baseline_clf <- tryCatch(
    polr(canonical_tier ~ age + log_capital, data = df, Hess = TRUE),
    error = function(e) nnet::multinom(canonical_tier ~ age + log_capital, data = df, trace = FALSE)
  )

  baseline_pred_class <- predict(baseline_clf, df, type = "class")
  baseline_prob <- predict(baseline_clf, df, type = "probs")
  if (is.vector(baseline_prob)) {
    # multinom returns matrix; polr returns matrix; vector means single-row
    baseline_prob <- t(as.matrix(baseline_prob))
  }

  # His "prediction" = canonical_tier itself (a single label per row)
  guide_pred_class <- df$canonical_tier
  # His "probabilities" for AUC: one-hot
  guide_prob <- matrix(0, nrow = nrow(df), ncol = length(tier_levels))
  colnames(guide_prob) <- tier_levels
  for (i in seq_len(nrow(df))) {
    guide_prob[i, as.character(df$canonical_tier[i])] <- 1
  }

  # Macro one-vs-rest AUC (use ordinal score for guide since one-hot AUC degrades to accuracy)
  guide_ordinal_score <- as.integer(df$canonical_tier)
  macro_auc <- function(prob_mat, ordinal_score_alt = NULL) {
    aucs <- c()
    for (cls in tier_levels) {
      truth <- as.integer(df$canonical_tier == cls)
      if (length(unique(truth)) < 2) next
      score <- if (!is.null(ordinal_score_alt)) ordinal_score_alt else prob_mat[, cls]
      if (!is.null(ordinal_score_alt) && cls != "Elite") {
        # For "Elite" class, higher ordinal = more likely Elite. For "Dart Throw",
        # lower ordinal = more likely. Flip score sign for lower classes by ranking.
        rank_target <- match(cls, tier_levels)  # 1..5
        # Score = -|ordinal - rank_target|: highest when class matches
        score <- -abs(as.integer(df$canonical_tier) - rank_target)
      }
      aucs <- c(aucs, as.numeric(pROC::auc(pROC::roc(truth, score, quiet = TRUE))))
    }
    mean(aucs, na.rm = TRUE)
  }

  weighted_f1 <- function(truth, pred) {
    lvls <- levels(factor(truth, levels = tier_levels))
    f1s <- c(); weights <- c()
    for (cls in lvls) {
      tp <- sum(pred == cls & truth == cls)
      fp <- sum(pred == cls & truth != cls)
      fn <- sum(pred != cls & truth == cls)
      prec <- if (tp + fp == 0) 0 else tp / (tp + fp)
      rec  <- if (tp + fn == 0) 0 else tp / (tp + fn)
      f1 <- if (prec + rec == 0) 0 else 2 * prec * rec / (prec + rec)
      f1s <- c(f1s, f1)
      weights <- c(weights, sum(truth == cls))
    }
    sum(f1s * weights) / sum(weights)
  }

  metrics <- list(
    n = nrow(df),
    acc_baseline   = mean(baseline_pred_class == df$canonical_tier),
    acc_guide      = mean(guide_pred_class == df$canonical_tier),  # = 1.0 trivially
    weighted_f1_baseline = weighted_f1(df$canonical_tier, baseline_pred_class),
    weighted_f1_guide    = 1.0,  # trivially since he predicts his own label
    kappa_baseline = quadratic_weighted_kappa(df$canonical_tier, baseline_pred_class, tier_levels),
    kappa_guide    = NA_real_,  # he predicts his own label; kappa not meaningful
    macro_auc_baseline = macro_auc(baseline_prob),
    macro_auc_guide    = macro_auc(NULL, ordinal_score_alt = guide_ordinal_score)
  )

  confusion_baseline <- table(
    truth = df$canonical_tier,
    pred  = factor(baseline_pred_class, levels = tier_levels)
  )

  list(baseline = baseline_clf, metrics = metrics,
       confusion_baseline = confusion_baseline, df = df,
       baseline_prob = baseline_prob)
}

compute_threshold_auc <- function(pred_numeric, truth_ffppg) {
  hit <- as.integer(truth_ffppg >= 10)
  elite <- as.integer(truth_ffppg >= 15)
  auc_hit <- if (length(unique(hit)) == 2)
    as.numeric(pROC::auc(pROC::roc(hit, pred_numeric, quiet = TRUE))) else NA_real_
  auc_elite <- if (length(unique(elite)) == 2)
    as.numeric(pROC::auc(pROC::roc(elite, pred_numeric, quiet = TRUE))) else NA_real_
  list(auc_hit = auc_hit, auc_elite = auc_elite)
}

run_per_position_models <- function(eval_df) {
  out <- list()
  for (pos in c("WR", "RB")) {
    df_pos <- eval_df |> filter(position == pos)
    reg <- fit_regression(df_pos)
    clf <- fit_classification(df_pos)
    auc_b <- compute_threshold_auc(reg$pred_baseline, reg$df$best_ffppg)
    auc_g <- compute_threshold_auc(as.integer(reg$df$canonical_tier), reg$df$best_ffppg)
    out[[pos]] <- list(
      regression = reg,
      classification = clf,
      threshold_auc_baseline = auc_b,
      threshold_auc_guide = auc_g
    )
  }
  out
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
Rscript -e 'testthat::test_file("analysis/late_round_eval/tests_R/test-models.R")'
```

Expected: all PASS.

- [ ] **Step 5: Snapshot real model metrics**

```bash
Rscript -e '
source("analysis/late_round_eval/models.R")
library(arrow)
df <- read_parquet("analysis/late_round_eval/data/eval_df.parquet")
results <- run_per_position_models(df)
summary <- list(
  WR = list(regression = results$WR$regression$metrics,
            classification = results$WR$classification$metrics,
            threshold_auc_baseline = results$WR$threshold_auc_baseline,
            threshold_auc_guide = results$WR$threshold_auc_guide),
  RB = list(regression = results$RB$regression$metrics,
            classification = results$RB$classification$metrics,
            threshold_auc_baseline = results$RB$threshold_auc_baseline,
            threshold_auc_guide = results$RB$threshold_auc_guide)
)
jsonlite::write_json(summary, "analysis/late_round_eval/data/model_summary.json", pretty = TRUE, auto_unbox = TRUE)
print(summary)
'
```

Expected: prints metric tables. Sanity: `delta_r2 > 0` for at least one position (his tier adds *something* over baseline).

- [ ] **Step 6: Commit**

```bash
git add analysis/late_round_eval/models.R \
        analysis/late_round_eval/tests_R/test-models.R \
        analysis/late_round_eval/data/model_summary.json
git commit -m "feat(late-round-eval): regression + classification models vs baseline

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Charts module

**Files:**
- Create: `analysis/late_round_eval/charts.R`
- Create: `analysis/late_round_eval/charts/*.png` (generated)

- [ ] **Step 1: Implement charts.R**

Create `analysis/late_round_eval/charts.R`:

```r
# Chart functions for late round guide eval. Each returns a ggplot or list of plots.

library(ggplot2)
library(patchwork)
library(scales)

CHART_DIR <- "analysis/late_round_eval/charts"
dir.create(CHART_DIR, recursive = TRUE, showWarnings = FALSE)

TIER_COLORS <- c(
  "Elite" = "#1a9850",
  "Starter" = "#91cf60",
  "Flex" = "#fee08b",
  "Depth" = "#fc8d59",
  "Dart Throw" = "#d73027"
)

save_chart <- function(plot, name, width = 8, height = 5, dpi = 150) {
  path <- file.path(CHART_DIR, paste0(name, ".png"))
  ggsave(path, plot, width = width, height = height, dpi = dpi)
  path
}

chart_coverage <- function(eval_df, harmonized_all) {
  # harmonized_all includes 2026; eval_df does not
  harmonized_all |>
    filter(position %in% c("WR", "RB")) |>
    count(guide_year, position, canonical_tier) |>
    ggplot(aes(x = factor(guide_year), y = n, fill = canonical_tier)) +
    geom_col() +
    facet_wrap(~position) +
    scale_fill_manual(values = TIER_COLORS) +
    labs(x = "Guide year", y = "Players", fill = "Canonical tier",
         title = "Coverage by year, position, and canonical tier") +
    theme_minimal()
}

chart_production_by_tier <- function(eval_df) {
  eval_df |>
    ggplot(aes(x = canonical_tier, y = best_ffppg, fill = canonical_tier)) +
    geom_boxplot(outlier.size = 0.6) +
    facet_wrap(~position) +
    scale_fill_manual(values = TIER_COLORS, guide = "none") +
    labs(x = "Canonical tier", y = "Best FFPPG (PPR, Y1-Y3)",
         title = "Realized production by canonical tier") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 30, hjust = 1))
}

chart_confusion_matrix <- function(confusion, title) {
  df <- as.data.frame(confusion)
  ggplot(df, aes(x = pred, y = truth, fill = Freq)) +
    geom_tile() +
    geom_text(aes(label = Freq), color = "white") +
    scale_fill_gradient(low = "#cccccc", high = "#08519c") +
    labs(title = title, x = "Predicted tier", y = "True tier") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 30, hjust = 1))
}

chart_slice_heatmap <- function(eval_df, models_out) {
  # Per-slice delta R²
  slices <- expand.grid(
    position = c("WR", "RB"),
    draft_round = c("1","2","3","day-3","UDFA"),
    p5_flag = c(TRUE, FALSE),
    stringsAsFactors = FALSE
  )
  slices$delta_r2 <- NA_real_
  for (i in seq_len(nrow(slices))) {
    sub <- eval_df |>
      filter(position == slices$position[i],
             draft_round == slices$draft_round[i],
             p5_flag == slices$p5_flag[i])
    if (nrow(sub) < 8) next
    res <- tryCatch(fit_regression(sub), error = function(e) NULL)
    if (!is.null(res)) slices$delta_r2[i] <- res$metrics$delta_r2
  }
  slices$slice <- paste(slices$draft_round,
                        ifelse(slices$p5_flag, "P5", "non-P5"))
  ggplot(slices, aes(x = slice, y = position, fill = delta_r2)) +
    geom_tile() +
    geom_text(aes(label = ifelse(is.na(delta_r2), "—", sprintf("%.2f", delta_r2))),
              size = 3) +
    scale_fill_gradient2(low = "#d73027", mid = "#ffffbf", high = "#1a9850",
                         midpoint = 0, na.value = "#cccccc") +
    labs(title = "Slice heatmap: ΔR² of guide model over baseline",
         x = "Slice", y = "Position", fill = "ΔR²") +
    theme_minimal() +
    theme(axis.text.x = element_text(angle = 30, hjust = 1))
}

chart_lift_curve <- function(eval_df) {
  late <- eval_df |> filter(draft_round %in% c("day-3", "UDFA"))
  if (nrow(late) < 5) return(ggplot() + labs(title = "Insufficient late-round data"))
  late <- late |> arrange(desc(as.integer(canonical_tier)))
  late$cumulative_hits_by_him <- cumsum(late$hit_flag) / sum(late$hit_flag)
  late$cumulative_pct <- seq_len(nrow(late)) / nrow(late)

  # Baseline ordering: by log(draft_capital) ascending (better capital first)
  late_baseline <- eval_df |>
    filter(draft_round %in% c("day-3", "UDFA")) |>
    arrange(draft_pick)
  late_baseline$cumulative_hits_by_capital <- cumsum(late_baseline$hit_flag) / sum(late_baseline$hit_flag)
  late_baseline$cumulative_pct <- seq_len(nrow(late_baseline)) / nrow(late_baseline)

  curves <- bind_rows(
    late |> select(cumulative_pct, hits = cumulative_hits_by_him) |> mutate(method = "Guide tier rank"),
    late_baseline |> select(cumulative_pct, hits = cumulative_hits_by_capital) |> mutate(method = "Draft capital rank")
  )

  ggplot(curves, aes(x = cumulative_pct, y = hits, color = method)) +
    geom_line(linewidth = 1) +
    geom_abline(linetype = "dashed", color = "gray") +
    labs(x = "Cumulative share of day-3+UDFA players evaluated",
         y = "Cumulative share of hits (FFPPG ≥ 10) captured",
         title = "Late-round lift: ranking by guide vs draft capital",
         color = NULL) +
    theme_minimal()
}
```

- [ ] **Step 2: Smoke test charts**

```bash
Rscript -e '
source("analysis/late_round_eval/charts.R")
source("analysis/late_round_eval/models.R")
source("analysis/late_round_eval/data_pipeline.R")
library(arrow)
eval_df <- read_parquet("analysis/late_round_eval/data/eval_df.parquet")
harmonized_all <- arrow::read_parquet("analysis/late_round_eval/extraction/output/harmonized.parquet")
save_chart(chart_coverage(eval_df, harmonized_all), "coverage")
save_chart(chart_production_by_tier(eval_df), "production_by_tier")
list.files("analysis/late_round_eval/charts/")
'
```

Expected: at least `coverage.png`, `production_by_tier.png` exist.

- [ ] **Step 3: Commit**

```bash
git add analysis/late_round_eval/charts.R analysis/late_round_eval/charts/
git commit -m "feat(late-round-eval): charts module and smoke-tested coverage/production PNGs

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 13: Render report

**Files:**
- Create: `analysis/late_round_eval/analysis.Rmd`
- Create: `analysis/late_round_eval/analysis.html` (rendered)

- [ ] **Step 1: Write the Rmd**

Create `analysis/late_round_eval/analysis.Rmd`:

```rmd
---
title: "Late Round Prospect Guide — Evaluation 2022–2025"
author: "Nick Gurol"
output:
  html_document:
    toc: true
    toc_float: true
    self_contained: true
knit: (function(input, ...) rmarkdown::render(input, output_dir = dirname(input), ...))
---

```{css mobile-styles, echo=FALSE}
img { max-width: 100%; height: auto; }
.main-container { max-width: 1000px; }
table { display: block; overflow-x: auto; }
@media (max-width: 768px) {
  .main-container { max-width: 100% !important; padding: 8px !important; }
  table { font-size: 11px !important; }
  h1 { font-size: 1.5em; } h2 { font-size: 1.25em; } h3 { font-size: 1.1em; }
}
```

```{r setup, include=FALSE}
knitr::opts_chunk$set(echo = FALSE, warning = FALSE, message = FALSE,
                      fig.width = 9, fig.height = 5, dpi = 120)
library(tidyverse)
library(arrow)
library(knitr)

source("data_pipeline.R", local = TRUE)
source("models.R", local = TRUE)
source("charts.R", local = TRUE)

eval_df <- read_parquet("data/eval_df.parquet")
harmonized_all <- read_parquet("extraction/output/harmonized.parquet")
models_out <- run_per_position_models(eval_df)

fmt <- function(x, d = 2) ifelse(is.na(x), "—", sprintf(paste0("%.", d, "f"), x))
```

# Executive summary

```{r exec-summary}
wr_reg <- models_out$WR$regression$metrics
rb_reg <- models_out$RB$regression$metrics
wr_clf <- models_out$WR$classification$metrics
rb_clf <- models_out$RB$classification$metrics

tibble::tibble(
  Position = c("WR", "RB"),
  N        = c(wr_reg$n, rb_reg$n),
  `Baseline adj R²` = c(fmt(wr_reg$adj_r2_baseline), fmt(rb_reg$adj_r2_baseline)),
  `Guide adj R²`    = c(fmt(wr_reg$adj_r2_guide), fmt(rb_reg$adj_r2_guide)),
  `ΔR²`             = c(fmt(wr_reg$delta_r2), fmt(rb_reg$delta_r2)),
  `F-test p`        = c(fmt(wr_reg$f_test_p, 3), fmt(rb_reg$f_test_p, 3)),
  `Baseline κ`      = c(fmt(wr_clf$kappa_baseline), fmt(rb_clf$kappa_baseline)),
  `Macro AUC base`  = c(fmt(wr_clf$macro_auc_baseline), fmt(rb_clf$macro_auc_baseline)),
  `Macro AUC guide` = c(fmt(wr_clf$macro_auc_guide), fmt(rb_clf$macro_auc_guide))
) |> kable()
```

**Verdict (WR):** `r if (wr_reg$delta_r2 > 0.05) "His tier adds material signal over draft capital + age." else "His tier adds little beyond draft capital + age."`

**Verdict (RB):** `r if (rb_reg$delta_r2 > 0.05) "His tier adds material signal over draft capital + age." else "His tier adds little beyond draft capital + age."`

# Methodology evolution 2022–2025

```{r methodology-features}
# Collect per-year features_mentioned from metadata.json files
years <- 2022:2025
feature_rows <- lapply(years, function(y) {
  mp <- file.path("extraction/output", paste0(y, "_metadata.json"))
  if (!file.exists(mp)) return(NULL)
  m <- jsonlite::fromJSON(mp)
  tibble(year = y, feature = m$features_mentioned)
}) |> bind_rows()

feature_table <- feature_rows |>
  mutate(present = "✓") |>
  pivot_wider(names_from = year, values_from = present, values_fill = "·")
kable(feature_table, caption = "Features mentioned in methodology, by year")
```

```{r methodology-text, results='asis'}
for (y in 2022:2025) {
  mp <- file.path("extraction/output", paste0(y, "_metadata.json"))
  if (!file.exists(mp)) next
  m <- jsonlite::fromJSON(mp)
  cat(sprintf("\n### %d (%s)\n\n", y, m$version))
  cat(m$methodology_text, "\n\n")
}
```

# Coverage 2022–2026

```{r coverage}
chart_coverage(eval_df, harmonized_all)
```

```{r coverage-table}
harmonized_all |>
  filter(position %in% c("WR", "RB")) |>
  count(guide_year, position) |>
  pivot_wider(names_from = position, values_from = n, values_fill = 0) |>
  kable(caption = "WR + RB players per guide year")
```

**2026:** rankings extracted but not evaluated (NFL data not yet available for this class).

# Production by tier

```{r production-by-tier}
chart_production_by_tier(eval_df)
```

```{r tier-stats}
eval_df |>
  group_by(position, canonical_tier) |>
  summarise(n = n(),
            mean_ffppg = mean(best_ffppg, na.rm = TRUE),
            median_ffppg = median(best_ffppg, na.rm = TRUE),
            hit_rate = mean(hit_flag),
            elite_rate = mean(elite_flag),
            bust_rate = mean(bust_flag),
            .groups = "drop") |>
  arrange(position, desc(canonical_tier)) |>
  mutate(across(c(mean_ffppg, median_ffppg), ~ round(.x, 2)),
         across(c(hit_rate, elite_rate, bust_rate), ~ scales::percent(.x, accuracy = 1))) |>
  kable(caption = "Realized production by canonical tier and position")
```

# Regression model — does his tier add over draft capital + age?

```{r reg-coefs}
for (pos in c("WR", "RB")) {
  cat(sprintf("\n### %s\n", pos))
  m <- models_out[[pos]]$regression$guide
  print(broom::tidy(m) |> mutate(across(where(is.numeric), ~ round(.x, 3))) |> kable())
}
```

# Classification — confusion matrices and AUC

```{r confusion-wr}
chart_confusion_matrix(models_out$WR$classification$confusion_baseline,
                       "WR baseline ordinal logistic confusion (true vs predicted)")
```

```{r confusion-rb}
chart_confusion_matrix(models_out$RB$classification$confusion_baseline,
                       "RB baseline ordinal logistic confusion (true vs predicted)")
```

```{r threshold-auc}
tibble::tibble(
  Position = c("WR", "RB"),
  `Hit AUC (baseline FFPPG pred)` = c(
    fmt(models_out$WR$threshold_auc_baseline$auc_hit),
    fmt(models_out$RB$threshold_auc_baseline$auc_hit)
  ),
  `Hit AUC (guide tier as ordinal)` = c(
    fmt(models_out$WR$threshold_auc_guide$auc_hit),
    fmt(models_out$RB$threshold_auc_guide$auc_hit)
  ),
  `Elite AUC (baseline)` = c(
    fmt(models_out$WR$threshold_auc_baseline$auc_elite),
    fmt(models_out$RB$threshold_auc_baseline$auc_elite)
  ),
  `Elite AUC (guide)` = c(
    fmt(models_out$WR$threshold_auc_guide$auc_elite),
    fmt(models_out$RB$threshold_auc_guide$auc_elite)
  )
) |> kable(caption = "Production-threshold AUC")
```

# Slices

```{r slice-heatmap}
chart_slice_heatmap(eval_df, models_out)
```

```{r slice-table}
eval_df |>
  group_by(position, draft_round, p5_flag) |>
  summarise(n = n(), mean_ffppg = mean(best_ffppg, na.rm = TRUE),
            hit_rate = mean(hit_flag), .groups = "drop") |>
  mutate(mean_ffppg = round(mean_ffppg, 2),
         hit_rate = scales::percent(hit_rate, accuracy = 1)) |>
  kable(caption = "Production by position × draft round × P5")
```

# Sleeper detection — day-3 + UDFA

```{r lift}
chart_lift_curve(eval_df)
```

```{r late-named-examples}
eval_df |>
  filter(draft_round %in% c("day-3", "UDFA")) |>
  arrange(desc(best_ffppg)) |>
  head(10) |>
  select(name, position, guide_year, canonical_tier, draft_round, best_ffppg) |>
  mutate(best_ffppg = round(best_ffppg, 2)) |>
  kable(caption = "Top 10 day-3+UDFA hits, with his tier call")

eval_df |>
  filter(draft_round %in% c("day-3", "UDFA"),
         canonical_tier %in% c("Starter", "Elite")) |>
  filter(best_ffppg < 5) |>
  arrange(canonical_tier, best_ffppg) |>
  head(10) |>
  select(name, position, guide_year, canonical_tier, draft_round, best_ffppg) |>
  mutate(best_ffppg = round(best_ffppg, 2)) |>
  kable(caption = "10 day-3+UDFA he tagged Starter+ that didn't pan out")
```

# Year-by-year scorecard

```{r yearly, results='asis'}
for (y in 2022:2025) {
  cat(sprintf("\n## %d class\n", y))
  print(
    eval_df |>
      filter(guide_year == y) |>
      arrange(desc(as.integer(canonical_tier)), draft_pick) |>
      select(name, position, canonical_tier, draft_round, best_ffppg) |>
      mutate(best_ffppg = round(best_ffppg, 2)) |>
      kable()
  )
}
```

# Sensitivity appendix

```{r sensitivity}
# Year FE variant — refit per position with class_year added
wr_yearfe_b <- lm(best_ffppg ~ age + log(draft_pick) + factor(guide_year),
                  data = eval_df |> filter(position == "WR"))
wr_yearfe_g <- lm(best_ffppg ~ age + log(draft_pick) + factor(guide_year) + canonical_tier,
                  data = eval_df |> filter(position == "WR"))
rb_yearfe_b <- lm(best_ffppg ~ age + log(draft_pick) + factor(guide_year),
                  data = eval_df |> filter(position == "RB"))
rb_yearfe_g <- lm(best_ffppg ~ age + log(draft_pick) + factor(guide_year) + canonical_tier,
                  data = eval_df |> filter(position == "RB"))
tibble::tibble(
  Position = c("WR", "RB"),
  `ΔR² (no year FE)` = c(fmt(models_out$WR$regression$metrics$delta_r2),
                          fmt(models_out$RB$regression$metrics$delta_r2)),
  `ΔR² (with year FE)` = c(
    fmt(summary(wr_yearfe_g)$adj.r.squared - summary(wr_yearfe_b)$adj.r.squared),
    fmt(summary(rb_yearfe_g)$adj.r.squared - summary(rb_yearfe_b)$adj.r.squared)
  )
) |> kable(caption = "Effect of including year fixed effects")

cat("\n### Match funnel summary\n")
matches <- read_parquet("extraction/output/matches.parquet")
matches |> count(match_stage) |> kable()
```

---

*Built with the late round prospect guide evaluation pipeline. Spec: `docs/superpowers/specs/2026-05-16-late-round-eval-design.md`.*
```

- [ ] **Step 2: Render the Rmd**

```bash
Rscript -e 'rmarkdown::render("analysis/late_round_eval/analysis.Rmd")'
```

Expected: `analysis/late_round_eval/analysis.html` generated without errors. Open in a browser and verify all sections render with data (no missing-data warnings, all charts present).

- [ ] **Step 3: Commit**

```bash
git add analysis/late_round_eval/analysis.Rmd analysis/late_round_eval/analysis.html analysis/late_round_eval/charts/
git commit -m "feat(late-round-eval): analysis.Rmd renders to analysis.html

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 14: Final review and cleanup

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest analysis/late_round_eval/tests/ -v
Rscript -e 'testthat::test_dir("analysis/late_round_eval/tests_R")'
```

Expected: all PASS in both.

- [ ] **Step 2: Verify HTML opens and renders correctly**

```bash
open analysis/late_round_eval/analysis.html
```

Visual check: TOC populates, all sections have content, no missing charts.

- [ ] **Step 3: Verify spec requirements covered**

Open the spec (`docs/superpowers/specs/2026-05-16-late-round-eval-design.md`) and walk down the section list — each report section should match what was rendered.

- [ ] **Step 4: Final commit if anything was touched up**

```bash
git status
# Only commit if there are real changes
```

---

## Self-review against the spec

Spec section coverage:
- ✅ Stage 1 extraction with verbatim source-quote validation → Tasks 2, 3, 4
- ✅ Tier harmonization to canonical 5-tier scheme → Task 5
- ✅ Birthday enrichment from sleeper + nflreadr → Task 6
- ✅ Two-agent matcher/auditor funnel with stages 1–7 → Tasks 7, 8, 10
- ✅ nflreadr joins + eval_df construction → Tasks 9, 10
- ✅ Models: `lm(best_ffppg ~ age + log(draft_pick))` baseline vs `+ canonical_tier`; `polr` ordinal classifier baseline vs his tier; year NOT a feature → Task 11
- ✅ Metrics: adj R², MAE, RMSE, F-test, accuracy, weighted F1 (via per-class), QWK, macro AUC OvR, production-threshold AUC → Task 11
- ✅ All 10 report sections → Task 13
- ✅ Slicing: position, draft_round, P5 (marginal in tables, full crossing in heatmap) → Tasks 11, 12, 13
- ✅ Sleeper deep dive with lift curve → Tasks 12, 13
- ✅ Sensitivity panel (year FE, 2025 inclusion) → Task 13
- ✅ Testing: pytest + testthat → Tasks 2, 3, 6, 7, 9, 11
- ✅ Reproducibility: committed intermediates → all stages commit their parquet/JSON outputs
