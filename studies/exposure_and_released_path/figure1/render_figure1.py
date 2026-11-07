#!/usr/bin/env python3
"""Render paper Figure 1 (v1.2.1): pairwise verdict disagreement of the six in-domain scorers on the 563 corpus pairs.

Rendering only. Reads the frozen corpus-audit outputs, asserts every plotted rate equals the frozen statistics, and
writes figure1_s3_heatmap.png next to this script. CypherLens receives SQL candidate text outside its input contract;
its 65-68% pairs would dominate the colour scale, so it is left out of the heatmap and kept in s3_pairwise_disagreement.csv.
  python3 studies/exposure_and_released_path/figure1/render_figure1.py
"""
import csv
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
FR = os.path.join(HERE, "../../corpus_audit/audit_final/frozen/20261029T190431Z_audit_final")
SIX = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cyspider"]
LABEL = {"cypherturn": "CypherTurn", "cypherbench": "CypherBench", "gqlbench": "GQLBench", "tugraph": "Text2GQL driver",
         "pipecypher": "PIPE-Cypher", "cyspider": "CySpider"}
INK, INK2, SURF = "#0b0b0b", "#52514e", "#fcfcfb"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "figure.facecolor": SURF, "axes.facecolor": SURF})
stats = json.load(open(os.path.join(FR, "audit_statistics.json")))
frozen = {(r["scorer_a"], r["scorer_b"]): r for r in stats["s3"]["pairwise"]}
pw = list(csv.DictReader(open(os.path.join(FR, "s3_pairwise_disagreement.csv"))))
n = len(SIX); M = [[0.0] * n for _ in range(n)]
for r in pw:
    f = frozen[(r["scorer_a"], r["scorer_b"])]
    assert int(r["disagreements"]) == f["disagreements"] and float(r["rate"]) == f["rate"], r
    if r["scorer_a"] in SIX and r["scorer_b"] in SIX:
        i, j = SIX.index(r["scorer_a"]), SIX.index(r["scorer_b"]); M[i][j] = M[j][i] = float(r["rate"])
assert sum(1 for i in range(n) for j in range(i + 1, n) if M[i][j] > 0) == 15
seq = LinearSegmentedColormap.from_list("seqblue", ["#f4f8fe", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])
vmax = max(max(x) for x in M)
fig, ax = plt.subplots(figsize=(5.4, 4.5))
im = ax.imshow(M, cmap=seq, vmin=0, vmax=vmax)
for i in range(n):
    for j in range(n):
        ax.text(j, i, "—" if i == j else f"{100 * M[i][j]:.1f}", ha="center", va="center", fontsize=9,
                color=INK2 if i == j else ("#ffffff" if M[i][j] > 0.55 * vmax else INK))
labs = [LABEL[s] for s in SIX]
ax.set_xticks(range(n), labs, rotation=40, ha="right"); ax.set_yticks(range(n), labs)
for s in ax.spines.values(): s.set_visible(False)
cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
cb.ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{100 * x:.0f}%")); cb.outline.set_visible(False)
ax.set_title("Pairwise verdict disagreement, six in-domain scorers (% of 563 pairs)", color=INK, fontsize=9)
fig.tight_layout(); fig.savefig(os.path.join(HERE, "figure1_s3_heatmap.png"), dpi=220); plt.close(fig)
print("rendered; values asserted identical to frozen statistics")
