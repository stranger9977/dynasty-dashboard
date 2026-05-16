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
