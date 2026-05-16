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
