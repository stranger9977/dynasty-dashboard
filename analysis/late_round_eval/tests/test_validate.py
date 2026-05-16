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
