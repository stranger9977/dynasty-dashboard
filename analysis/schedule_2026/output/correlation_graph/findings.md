# Schedule Correlation Graph — NFL 2026

Each edge weights the **Jaccard similarity** of two teams' 2026 opponent sets:
`|A_opps ∩ B_opps| / |A_opps ∪ B_opps|` (excluding A and B from each other's lists).
Across all **496** unordered team pairs, mean jaccard = **0.293**,
median = **0.273**. The graph keeps only pairs with jaccard ≥ **0.52**,
yielding **56** edges.

## Top 5 most-entangled team pairs

- **DEN ↔ KC** — jaccard **0.625** (10/16 shared opponents): ARI, BUF, LA, LAC, LV, MIA, NE, NYJ, SEA, SF
- **DEN ↔ LV** — jaccard **0.625** (10/16 shared opponents): ARI, BUF, KC, LA, LAC, MIA, NE, NYJ, SEA, SF
- **KC ↔ LV** — jaccard **0.625** (10/16 shared opponents): ARI, BUF, DEN, LA, LAC, MIA, NE, NYJ, SEA, SF
- **KC ↔ LAC** — jaccard **0.625** (10/16 shared opponents): ARI, BUF, DEN, LA, LV, MIA, NE, NYJ, SEA, SF
- **JAX ↔ TEN** — jaccard **0.625** (10/16 shared opponents): BAL, CIN, CLE, DAL, HOU, IND, NYG, PHI, PIT, WAS

Of the top-5, **5/5** are intra-division pairs. Divisional rivals share
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
  1. (8 teams) BUF, DEN, KC, LAC, LV, MIA, NE, NYJ — [AFC East×4, AFC West×4]
  2. (8 teams) BAL, CIN, CLE, HOU, IND, JAX, PIT, TEN — [AFC North×4, AFC South×4]
  3. (4 teams) CHI, DET, GB, MIN — [NFC North×4]
  4. (4 teams) ARI, LA, SEA, SF — [NFC West×4]
  5. (4 teams) ATL, CAR, NO, TB — [NFC South×4]
  6. (4 teams) DAL, NYG, PHI, WAS — [NFC East×4]

## Reading the chart

Node color = division. Edge thickness scales with jaccard. Yellow highlighted edges
mark the top-5 pairs (with labels). The spring layout pulls high-similarity teams
together, so each division clumps and divisional-rotation neighbors hover nearby.
