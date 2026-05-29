# ingestion/blend.py
"""Pure equal/weighted blend + disagreement-spread math over per-source ranks."""


def blend_rank(source_ranks: dict, weights: dict):
    """Weighted mean of present source ranks, renormalized over present sources.
    source_ranks: {key: rank or None}. weights: {key: weight}. None if none present."""
    num = 0.0
    den = 0.0
    for key, rank in source_ranks.items():
        if rank is None:
            continue
        w = weights.get(key, 0.0)
        if w <= 0:
            continue
        num += rank * w
        den += w
    return num / den if den > 0 else None


def rank_spread(source_ranks: dict):
    """(spread, high_source, low_source) over present ranks; needs >=2 present.
    high_source = most bullish (lowest rank number), low_source = most bearish."""
    present = {k: r for k, r in source_ranks.items() if r is not None}
    if len(present) < 2:
        return None, None, None
    high = min(present, key=present.get)
    low = max(present, key=present.get)
    return present[low] - present[high], high, low
