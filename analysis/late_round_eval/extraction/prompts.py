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
