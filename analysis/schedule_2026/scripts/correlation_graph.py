"""Schedule correlation graph for the NFL 2026 schedule.

For each pair of teams (A, B), compute the Jaccard similarity of their opponent
sets in 2026. Build a graph with 32 nodes and edges where jaccard >= threshold
(tuned so we get ~50-100 edges). Visualize with spring layout, node color by
division, edge thickness by jaccard, and label the top-5 most similar pairs.

Run:
    cd /Users/nick/projects/dynasty-dashboard && \
        uv run python analysis/schedule_2026/scripts/correlation_graph.py
"""
from __future__ import annotations

import sys
from itertools import combinations

sys.path.insert(0, "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026")

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd

from _shared import nflverse, output, teams

SLUG = "correlation_graph"

# Division color palette
DIVISION_COLORS = {
    "AFC East": "#1f77b4",
    "AFC North": "#ff7f0e",
    "AFC South": "#2ca02c",
    "AFC West": "#d62728",
    "NFC East": "#9467bd",
    "NFC North": "#8c564b",
    "NFC South": "#e377c2",
    "NFC West": "#17becf",
}


def build_opponent_sets(sched: pd.DataFrame) -> dict[str, set[str]]:
    """Return team -> set of opponents played in 2026 (regular season)."""
    opps: dict[str, set[str]] = {t: set() for t in teams.ALL_TEAMS}
    for row in sched.itertuples(index=False):
        h, a = row.home_team, row.away_team
        opps[h].add(a)
        opps[a].add(h)
    return opps


def compute_pairs(opps: dict[str, set[str]]) -> pd.DataFrame:
    """For every unordered team pair, compute jaccard + common opponents list."""
    rows = []
    for a, b in combinations(sorted(opps.keys()), 2):
        common = opps[a] & opps[b]
        # Remove A and B from each other's opponent sets when computing union/common
        # so that A playing B doesn't pollute "shared opponents".
        common = common - {a, b}
        union = (opps[a] | opps[b]) - {a, b}
        jacc = len(common) / len(union) if union else 0.0
        rows.append(
            {
                "team_a": a,
                "team_b": b,
                "jaccard": jacc,
                "common_opps": ",".join(sorted(common)),
                "n_common": len(common),
                "n_union": len(union),
            }
        )
    df = pd.DataFrame(rows).sort_values("jaccard", ascending=False).reset_index(drop=True)
    return df


def pick_threshold(pairs: pd.DataFrame, target_low: int = 50, target_high: int = 100) -> float:
    """Pick a jaccard threshold that yields between 50 and 100 edges."""
    # Try a descending list of candidate thresholds; choose the highest one with
    # at least target_low edges, preferring within [target_low, target_high].
    candidates = [round(x, 3) for x in np.arange(0.30, 0.71, 0.01)]
    candidates.sort(reverse=True)
    best = None
    for t in candidates:
        n = int((pairs["jaccard"] >= t).sum())
        if target_low <= n <= target_high:
            return float(t)
        if n >= target_low and best is None:
            best = float(t)
    if best is not None:
        return best
    # Fallback: pick threshold giving closest to midpoint
    mid = (target_low + target_high) // 2
    diffs = [(abs(int((pairs["jaccard"] >= t).sum()) - mid), t) for t in candidates]
    diffs.sort()
    return float(diffs[0][1])


def build_graph(pairs: pd.DataFrame, threshold: float) -> nx.Graph:
    G = nx.Graph()
    for t in teams.ALL_TEAMS:
        G.add_node(t, division=teams.DIVISIONS[t])
    edges = pairs[pairs["jaccard"] >= threshold]
    for r in edges.itertuples(index=False):
        G.add_edge(r.team_a, r.team_b, weight=float(r.jaccard))
    return G


def detect_communities(G: nx.Graph) -> list[set[str]]:
    """Greedy modularity clustering on the thresholded graph."""
    try:
        from networkx.algorithms.community import greedy_modularity_communities

        # Only nodes that have at least one edge participate meaningfully
        H = G.copy()
        # Use only the connected subgraph nodes; isolated nodes will be reported separately
        comms = list(greedy_modularity_communities(H, weight="weight"))
        return [set(c) for c in comms]
    except Exception:
        return [set(c) for c in nx.connected_components(G)]


def make_chart(G: nx.Graph, pairs: pd.DataFrame, threshold: float, path) -> None:
    # Layout — use edge weights so high-jaccard pairs pull together.
    # k controls ideal distance between nodes; larger k spreads clusters out so
    # tightly-bound divisional cliques don't collapse into unreadable blobs.
    pos = nx.spring_layout(G, weight="weight", seed=7, k=1.6, iterations=400)

    node_colors = [DIVISION_COLORS[teams.DIVISIONS[n]] for n in G.nodes]
    edges = list(G.edges(data=True))
    weights = np.array([d["weight"] for _, _, d in edges]) if edges else np.array([])

    fig, ax = plt.subplots(figsize=(15, 13))

    # Edge thickness scaled to jaccard
    if len(weights):
        wmin, wmax = weights.min(), weights.max()
        denom = max(wmax - wmin, 1e-9)
        edge_widths = 0.6 + 4.4 * (weights - wmin) / denom
        # Edge alpha also scaled
        edge_alphas = 0.25 + 0.65 * (weights - wmin) / denom
    else:
        edge_widths = []
        edge_alphas = []

    # Draw edges one by one to vary alpha (matplotlib LineCollection supports arrays of alpha in newer versions but be safe)
    for (u, v, d), w, a in zip(edges, edge_widths, edge_alphas):
        ax.plot(
            [pos[u][0], pos[v][0]],
            [pos[u][1], pos[v][1]],
            color="#555555",
            linewidth=w,
            alpha=a,
            zorder=1,
        )

    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        node_size=750,
        edgecolors="black",
        linewidths=1.0,
        ax=ax,
    )
    nx.draw_networkx_labels(
        G, pos, font_size=9, font_weight="bold", font_color="white", ax=ax
    )

    # Highlight top-5 most similar pairs that are present in the graph.
    # First draw the highlighted edges; then place labels with a callout line
    # offset from the cluster, so labels don't overlap inside tight cliques.
    top5 = pairs.head(5)
    # Determine a sensible offset distance from the global span.
    xs = np.array([p[0] for p in pos.values()])
    ys = np.array([p[1] for p in pos.values()])
    span = max(xs.max() - xs.min(), ys.max() - ys.min())
    off = span * 0.07

    label_anchors: list[tuple[float, float]] = []
    for i, r in enumerate(top5.itertuples(index=False)):
        if not G.has_edge(r.team_a, r.team_b):
            continue
        ax.plot(
            [pos[r.team_a][0], pos[r.team_b][0]],
            [pos[r.team_a][1], pos[r.team_b][1]],
            color="#ffcc00",
            linewidth=3.4,
            alpha=0.95,
            zorder=2,
        )
        mx = (pos[r.team_a][0] + pos[r.team_b][0]) / 2
        my = (pos[r.team_a][1] + pos[r.team_b][1]) / 2

        # Push the label away from the global centroid so each cluster's
        # labels fan outward instead of stacking on top of each other.
        cx, cy = float(xs.mean()), float(ys.mean())
        dx, dy = mx - cx, my - cy
        norm = (dx * dx + dy * dy) ** 0.5 or 1.0
        lx = mx + (dx / norm) * off * (1.2 + 0.4 * i)
        ly = my + (dy / norm) * off * (1.2 + 0.4 * i)

        # Connector line from midpoint to label
        ax.plot([mx, lx], [my, ly], color="#cc9900", linewidth=0.7, alpha=0.7, zorder=2)

        ax.text(
            lx,
            ly,
            f"{r.team_a}–{r.team_b}\n{r.jaccard:.3f}",
            fontsize=9,
            ha="center",
            va="center",
            color="black",
            bbox=dict(
                boxstyle="round,pad=0.3",
                facecolor="#fff7d6",
                edgecolor="#cc9900",
                linewidth=0.9,
                alpha=0.95,
            ),
            zorder=4,
        )
        label_anchors.append((lx, ly))

    # Legend for divisions
    from matplotlib.patches import Patch

    legend_elems = [
        Patch(facecolor=color, edgecolor="black", label=div)
        for div, color in DIVISION_COLORS.items()
    ]
    legend_elems.append(
        Patch(facecolor="#ffcc00", edgecolor="black", label="Top-5 most similar pair")
    )
    ax.legend(handles=legend_elems, loc="lower left", framealpha=0.95, fontsize=9)

    ax.set_title(
        f"NFL 2026 Schedule Correlation Graph — Jaccard ≥ {threshold:.2f} "
        f"({G.number_of_edges()} edges, nodes colored by division)",
        fontsize=13,
    )
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def describe_clusters(communities: list[set[str]]) -> str:
    # Sort communities by size desc
    communities = sorted(communities, key=lambda c: -len(c))
    lines = []
    for i, c in enumerate(communities, 1):
        if len(c) < 2:
            continue
        members = sorted(c)
        # Tally divisions in the cluster
        from collections import Counter

        div_counts = Counter(teams.DIVISIONS[t] for t in members)
        div_str = ", ".join(f"{d}×{n}" for d, n in div_counts.most_common())
        lines.append(f"  {i}. ({len(members)} teams) {', '.join(members)} — [{div_str}]")
    return "\n".join(lines) if lines else "  (no non-trivial clusters)"


def build_findings(
    pairs: pd.DataFrame,
    threshold: float,
    G: nx.Graph,
    communities: list[set[str]],
) -> str:
    top5 = pairs.head(5)
    bullet_lines = []
    for r in top5.itertuples(index=False):
        bullet_lines.append(
            f"- **{r.team_a} ↔ {r.team_b}** — jaccard **{r.jaccard:.3f}** "
            f"({r.n_common}/{r.n_union} shared opponents): {r.common_opps.replace(',', ', ')}"
        )

    # Quick stats
    median_j = pairs["jaccard"].median()
    mean_j = pairs["jaccard"].mean()
    n_pairs_total = len(pairs)
    n_edges = G.number_of_edges()

    # Are top-5 pairs divisional?
    same_div_top5 = sum(
        1 for r in top5.itertuples(index=False)
        if teams.DIVISIONS[r.team_a] == teams.DIVISIONS[r.team_b]
    )

    cluster_text = describe_clusters(communities)

    md = f"""# Schedule Correlation Graph — NFL 2026

Each edge weights the **Jaccard similarity** of two teams' 2026 opponent sets:
`|A_opps ∩ B_opps| / |A_opps ∪ B_opps|` (excluding A and B from each other's lists).
Across all **{n_pairs_total}** unordered team pairs, mean jaccard = **{mean_j:.3f}**,
median = **{median_j:.3f}**. The graph keeps only pairs with jaccard ≥ **{threshold:.2f}**,
yielding **{n_edges}** edges.

## Top 5 most-entangled team pairs

{chr(10).join(bullet_lines)}

Of the top-5, **{same_div_top5}/5** are intra-division pairs. Divisional rivals share
14 of 17 opponents by construction (same 4 division opps, plus the same 2 inter-division
slates), so divisions dominate the high end of the jaccard distribution. The non-divisional
entries in the top tier are usually teams from divisions whose rotating cross-conference
matchups happen to align in 2026.

## Visible clusters (greedy modularity)

The graph fragments into communities that line up almost perfectly with divisions —
unsurprising, since the NFL's scheduling formula bakes in 14 shared opponents for each
division. Mixed clusters appear where two divisions face the same pair of opposing
divisions in 2026 (e.g. an AFC division and its scheduled NFC counterpart).

Clusters with ≥ 2 teams:
{cluster_text}

## Reading the chart

Node color = division. Edge thickness scales with jaccard. Yellow highlighted edges
mark the top-5 pairs (with labels). The spring layout pulls high-similarity teams
together, so each division clumps and divisional-rotation neighbors hover nearby.
"""
    return md


def main() -> None:
    sched = nflverse.load_schedule_2026()
    if "game_type" in sched.columns:
        sched = sched[sched["game_type"] == "REG"].copy()

    opps = build_opponent_sets(sched)

    # Sanity: every team should have between 13 and 14 unique opponents (17 games incl. dupes).
    assert len(opps) == 32, f"expected 32 teams, got {len(opps)}"
    for t, s in opps.items():
        assert 10 <= len(s) <= 17, f"team {t} has odd opponent count: {len(s)}"

    pairs = compute_pairs(opps)
    assert len(pairs) == 32 * 31 // 2 == 496, f"expected 496 pairs, got {len(pairs)}"

    threshold = pick_threshold(pairs, target_low=50, target_high=100)
    G = build_graph(pairs, threshold)
    communities = detect_communities(G)

    # Persist data — schema required: team_a, team_b, jaccard, common_opps
    data_df = pairs[["team_a", "team_b", "jaccard", "common_opps"]].copy()
    data_path = output.write_data(SLUG, data_df)

    chart_p = output.chart_path(SLUG)
    make_chart(G, pairs, threshold, chart_p)

    findings_md = build_findings(pairs, threshold, G, communities)
    findings_path = output.write_findings(SLUG, findings_md)

    n_edges = G.number_of_edges()
    print(f"Threshold:      jaccard >= {threshold:.3f}")
    print(f"Edges:          {n_edges}")
    print(f"Communities:    {len([c for c in communities if len(c) >= 2])} non-trivial")
    print(f"Wrote data:     {data_path}  ({len(data_df)} rows)")
    print(f"Wrote chart:    {chart_p}")
    print(f"Wrote findings: {findings_path}")
    print()
    print("Top 10 pairs:")
    print(pairs.head(10)[["team_a", "team_b", "jaccard", "common_opps"]].to_string(index=False))


if __name__ == "__main__":
    main()
