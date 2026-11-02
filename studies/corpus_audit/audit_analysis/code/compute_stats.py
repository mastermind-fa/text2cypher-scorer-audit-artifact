#!/usr/bin/env python3
"""Compute all pre-specified MAIN_AUDIT statistics from frozen raw verdicts (audit-compute-stats-v1).

  python compute_stats.py <final_dir>

Reads <final_dir>/raw/{s1,s3,s2}/<scorer>.jsonl, <final_dir>/pairs/*.jsonl and the frozen S1 suite.
Writes CSV/JSON tables, figures/ and audit_decision_trace.json into <final_dir>. Qualitative topic-gate fields are NOT
computed here; they are marked REQUIRES_HUMAN_INTERPRETATION.
"""
import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import audit_analysis as K  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
S1 = os.path.join(ROOT, "studies", "controlled_suite", "audit", "s1", "s1_cases.jsonl")
ALL = K.PRIMARY + K.SECONDARY
LABEL = {"cypherturn": "CypherTurn", "cypherbench": "CypherBench", "gqlbench": "GQLBench", "tugraph": "TuGraph",
         "pipecypher": "PIPE-Cypher", "cypherlens": "CypherLens", "cyspider": "CySpider",
         "neo4jlabs": "neo4j-labs*", "pc_v1_1": "pc-v1.1*"}


def load_verdicts(final, set_name):
    v = collections.defaultdict(dict)
    native = collections.defaultdict(dict)
    for s in ALL:
        for line in open(os.path.join(final, "raw", set_name, f"{s}.jsonl")):
            r = json.loads(line)
            v[r["case_id"]][s] = r["verdict"]
            native[r["case_id"]][s] = r["native"]
    return dict(v), dict(native)


def write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else [])
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def per_unit_rows(verdicts, pairs, extra=None):
    for cid in sorted(verdicts):
        row = {"case_id": cid}
        row.update({s: verdicts[cid][s] for s in ALL})
        prim = [verdicts[cid][s] for s in K.PRIMARY]
        row["primary_unanimous"] = all(K.is_binary(x) for x in prim) and len({int(x) for x in prim}) == 1
        row["primary_pass_count"] = sum(1 for x in prim if K.is_binary(x) and int(x) == 1)
        row["features"] = ";".join(K.features(pairs[cid])) if cid in pairs else ""
        if extra:
            row.update(extra(cid))
        yield row


def taxonomy(verdicts, pairs):
    """Mechanical features of disagreeing units + verdict signatures (which primary scorers pass)."""
    feat = collections.Counter()
    sig = collections.Counter()
    pair_feat = collections.defaultdict(collections.Counter)
    n_dis = 0
    for cid, v in verdicts.items():
        prim = {s: v[s] for s in K.PRIMARY}
        if not all(K.is_binary(x) for x in prim.values()) or len({int(x) for x in prim.values()}) == 1:
            continue
        n_dis += 1
        fs = K.features(pairs[cid]) or ["NO_DECLARED_FEATURE"]
        feat.update(fs)
        sig["pass:" + ",".join(s for s in K.PRIMARY if int(prim[s]) == 1)] += 1
        for a, b in K.pairs_of(K.PRIMARY):
            if int(prim[a]) != int(prim[b]):
                pair_feat[f"{a}|{b}"].update(fs)
    return {"n_disagreeing_units": n_dis, "feature_counts": dict(feat.most_common()),
            "verdict_signatures": dict(sig.most_common()),
            "pair_top_features": {p: dict(c.most_common(4)) for p, c in pair_feat.items()}}


def figures(final, s3_pairs, s1_dim, s1_cases):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    fd = os.path.join(final, "figures")
    os.makedirs(fd, exist_ok=True)
    ink, ink2, surf, grid = "#0b0b0b", "#52514e", "#fcfcfb", "#e4e3df"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": ink2, "axes.labelcolor": ink, "xtick.color": ink2,
                         "ytick.color": ink2, "figure.facecolor": surf, "axes.facecolor": surf})
    # 1. 7x7 heatmap of S3 disagreement rates (sequential blue)
    seq = LinearSegmentedColormap.from_list("seqblue", ["#f4f8fe", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab",
                                                         "#0d366b"])
    n = len(K.PRIMARY)
    M = [[0.0] * n for _ in range(n)]
    for r in s3_pairs:
        i, j = K.PRIMARY.index(r["scorer_a"]), K.PRIMARY.index(r["scorer_b"])
        M[i][j] = M[j][i] = r["rate"] or 0.0
    vmax = max(max(row) for row in M) or 1e-9
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    im = ax.imshow(M, cmap=seq, vmin=0, vmax=vmax)
    for i in range(n):
        for j in range(n):
            if i != j:
                ax.text(j, i, f"{100 * M[i][j]:.1f}", ha="center", va="center", fontsize=8,
                        color="#ffffff" if M[i][j] > 0.55 * vmax else ink)
            else:
                ax.text(j, i, "—", ha="center", va="center", color=ink2)
    labs = [LABEL[s] for s in K.PRIMARY]
    ax.set_xticks(range(n), labs, rotation=40, ha="right")
    ax.set_yticks(range(n), labs)
    ax.set_title(f"S3: pairwise verdict disagreement (% of n = {max(r['n'] for r in s3_pairs)} gold SQL↔Cypher pairs)", color=ink, fontsize=9.5)
    for s in ax.spines.values():
        s.set_visible(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{100 * x:.0f}%"))
    cb.outline.set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(fd, "fig1_s3_disagreement_heatmap.png"), dpi=200)
    plt.close(fig)
    # 2. dot plot of rates with two-sided Wilson 95% CI and Bonferroni one-sided lower bound; 2% reference line
    rows = sorted(s3_pairs, key=lambda r: r["rate"] or 0)
    fig, ax = plt.subplots(figsize=(6.2, 6.4))
    for y, r in enumerate(rows):
        ax.plot([r["wilson95_lo"], r["wilson95_hi"]], [y, y], color="#86b6ef", lw=2, solid_capstyle="round")
        ax.plot(r["rate"], y, "o", color="#2a78d6", ms=6, mec=surf, mew=1.5)
        ax.plot(r["lower_bonf_one_sided"], y, "|", color="#0d366b", ms=11, mew=2)
    ax.axvline(K.H_THRESHOLD, color="#eb6834", lw=1.5, ls="--")
    ax.text(K.H_THRESHOLD, len(rows) - 0.3, " 2% pre-registered threshold", color=ink2, fontsize=8, va="bottom")
    ax.set_yticks(range(len(rows)), [f"{LABEL[r['scorer_a']]} – {LABEL[r['scorer_b']]}" for r in rows], fontsize=8)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{100 * x:.0f}%"))
    ax.set_xlabel(f"Disagreement rate on S3 (n = {max(r['n'] for r in rows)} pairs; ERROR excluded per pair)")
    ax.grid(axis="x", color=grid, lw=0.8)
    ax.set_axisbelow(True)
    for s in ["top", "right", "left"]:
        ax.spines[s].set_visible(False)
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], marker="o", color="#2a78d6", ls="", label="rate"),
                       Line2D([], [], color="#86b6ef", lw=2, label="Wilson 95% (two-sided)"),
                       Line2D([], [], marker="|", color="#0d366b", ls="", ms=11, mew=2,
                              label="Bonferroni one-sided lower bound (α=0.05/21)")],
              loc="upper center", bbox_to_anchor=(0.4, -0.1), ncol=1, frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(fd, "fig3_s3_pairwise_rates_ci.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    # 3. S1 dimension x scorer matrix: blue = all oracle-correct, orange = >=1 incorrect, gray = policy-only dim
    dims = sorted({c["dimension"] for c in s1_cases.values()})
    exp = {d: {c["expected"] for c in s1_cases.values() if c["dimension"] == d} for d in dims}
    fig, ax = plt.subplots(figsize=(7.4, 9.2))
    for y, d in enumerate(dims):
        for x, s in enumerate(ALL):
            cell = s1_dim.get(d, {}).get(s)
            if cell:
                col = "#2a78d6" if cell["incorrect"] == 0 else "#eb6834"
                txt = f"{cell['correct']}/{cell['n']}"
            else:
                vals = [v for c in s1_cases.values() if c["dimension"] == d for v in [c["_v"][s]]]
                col, txt = "#c3c2b7", f"acc {sum(1 for v in vals if K.is_binary(v) and int(v) == 1)}/{len(vals)}"
            ax.add_patch(plt.Rectangle((x + 0.04, y + 0.06), 0.92, 0.88, color=col, lw=0))
            ax.text(x + 0.5, y + 0.5, txt, ha="center", va="center", fontsize=6.5,
                    color="#ffffff" if col != "#c3c2b7" else ink)
    ax.set_xlim(0, len(ALL))
    ax.set_ylim(len(dims), 0)
    ax.set_xticks([i + 0.5 for i in range(len(ALL))], [LABEL[s] for s in ALL], rotation=40, ha="right")
    ax.set_yticks([i + 0.5 for i in range(len(dims))], dims, fontsize=7)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    import matplotlib.patches as mp
    ax.legend(handles=[mp.Patch(color="#2a78d6", label="all oracle-defined cases correct (k/n)"),
                       mp.Patch(color="#eb6834", label="≥1 oracle-defined case incorrect (k/n correct)"),
                       mp.Patch(color="#c3c2b7", label="INTENT_DEPENDENT only: policy (accepted/n)")],
              loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=1, frameon=False, fontsize=7.5)
    ax.set_title("S1: scorer behaviour by dimension (* = secondary)", color=ink, fontsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(fd, "fig2_s1_dimension_matrix.png"), dpi=200)
    plt.close(fig)


def main():
    final = sys.argv[1]
    s1_cases = {}
    for line in open(S1):
        c = json.loads(line)
        s1_cases[c["case_id"]] = c
    s3_pairs = {json.loads(l)["case_id"]: json.loads(l) for l in open(os.path.join(final, "pairs", "s3_pairs.jsonl"))}
    s2_pairs = {json.loads(l)["case_id"]: json.loads(l) for l in open(os.path.join(final, "pairs", "s2_pairs.jsonl"))}
    v1, n1 = load_verdicts(final, "s1")
    v3, n3 = load_verdicts(final, "s3")
    v2, n2 = load_verdicts(final, "s2")
    assert set(v1) == set(s1_cases) and set(v3) == set(s3_pairs) and set(v2) == set(s2_pairs)

    # ---- S1
    meta = {cid: {"expected": c["expected"], "dimension": c["dimension"]} for cid, c in s1_cases.items()}
    s1_sc, s1_dim, s1_intent = K.s1_oracle(v1, meta, ALL)
    for cid in s1_cases:
        s1_cases[cid]["_v"] = v1[cid]
    write_csv(os.path.join(final, "s1_results.csv"),
              ({"case_id": cid, "dimension": c["dimension"], "expected": c["expected"], "rule": c["rule"],
                **{s: v1[cid][s] for s in ALL}} for cid, c in sorted(s1_cases.items())))
    dim_rows = []
    for d in sorted({c["dimension"] for c in s1_cases.values()}):
        for s in ALL:
            if d in s1_dim and s in s1_dim[d]:
                x = s1_dim[d][s]
                dim_rows.append({"dimension": d, "scorer": s, "kind": "ORACLE", "n": x["n"], "correct": x["correct"],
                                 "incorrect": x["incorrect"], "errors": x["errors"],
                                 "verdicts": " ".join(map(str, x["verdicts"]))})
            elif d in s1_intent.get(s, {}):
                vs = s1_intent[s][d]
                dim_rows.append({"dimension": d, "scorer": s, "kind": "POLICY_ONLY", "n": len(vs), "correct": "",
                                 "incorrect": "", "errors": vs.count("ERROR"), "verdicts": " ".join(map(str, vs))})
    write_csv(os.path.join(final, "s1_dimension_summary.csv"), dim_rows)

    # ---- S3 (primary)
    s3_pw = K.pairwise(v3, K.PRIMARY)
    h1 = K.h1_decision(s3_pw)
    write_csv(os.path.join(final, "s3_pairwise_disagreement.csv"), s3_pw)
    write_csv(os.path.join(final, "s3_results.csv"), per_unit_rows(v3, s3_pairs))
    s3_unan = K.unanimity(v3)
    s3_marg = K.marginals(v3, ALL)
    s3_err0 = K.pairwise(v3, K.PRIMARY, error_as_zero=True)
    s3_tax = taxonomy(v3, s3_pairs)
    sec_pw = [r for r in K.pairwise(v3, ALL) if r["scorer_a"] in K.SECONDARY or r["scorer_b"] in K.SECONDARY]

    # ---- S2 (secondary)
    clusters = {cid: p["meta"]["cluster"] for cid, p in s2_pairs.items()}
    s2_pw = K.pairwise(v2, K.PRIMARY)
    boot = K.cluster_bootstrap_pairwise(v2, clusters)
    for r in s2_pw:
        lo, hi = boot[(r["scorer_a"], r["scorer_b"])]
        r["cluster_boot95_lo"], r["cluster_boot95_hi"] = lo, hi
    write_csv(os.path.join(final, "s2_results.csv"),
              per_unit_rows(v2, s2_pairs, extra=lambda cid: {"model": s2_pairs[cid]["meta"]["model"],
                                                             "empty_prediction": s2_pairs[cid]["meta"]["empty_prediction"]}))
    write_csv(os.path.join(final, "s2_pairwise_disagreement.csv"), s2_pw)
    s2_empty = sum(p["meta"]["empty_prediction"] for p in s2_pairs.values())
    s2_tax = taxonomy(v2, s2_pairs)

    # ---- secondary scorers
    sec_rows = []
    for s in K.SECONDARY:
        for which, v in [("S1_oracle", None), ("S3", v3), ("S2", v2)]:
            if which == "S1_oracle":
                sec_rows.append({"scorer": s, "set": which, **{k: s1_sc[s][k] for k in
                                                               ["n_oracle_defined", "correct", "oracle_agreement"]}})
            else:
                m = K.marginals(v, [s])[s]
                sec_rows.append({"scorer": s, "set": which, "n": m["n"], "pass": m["pass"], "pass_rate": m["pass_rate"],
                                 "errors": m["errors"]})
    write_csv(os.path.join(final, "secondary_scorer_results.csv"), sec_rows,
              ["scorer", "set", "n_oracle_defined", "correct", "oracle_agreement", "n", "pass", "pass_rate", "errors"])

    stats = {
        "analysis_version": "audit-analysis-v1",
        "s1": {"n_cases": len(s1_cases), "n_oracle_defined": sum(c["expected"] != "INTENT_DEPENDENT" for c in s1_cases.values()),
               "n_intent_dependent": sum(c["expected"] == "INTENT_DEPENDENT" for c in s1_cases.values()),
               "per_scorer": s1_sc, "intent_dependent_profile": s1_intent},
        "s3": {"n": len(v3), "pairwise": s3_pw, "h1": h1, "unanimity": s3_unan, "marginals": s3_marg,
               "error_as_zero_sensitivity": [{k: r[k] for k in ["scorer_a", "scorer_b", "n", "disagreements", "rate",
                                                                  "lower_bonf_one_sided"]} for r in s3_err0],
               "taxonomy": s3_tax, "secondary_vs_all_pairwise": sec_pw},
        "s2": {"n": len(v2), "empty_prediction": s2_empty, "empty_fraction": s2_empty / len(v2),
               "pairwise": s2_pw, "unanimity": K.unanimity(v2), "marginals": K.marginals(v2, ALL), "taxonomy": s2_tax,
               "label": "SECONDARY / FLOOR-EFFECT ANALYSIS"},
    }
    json.dump(stats, open(os.path.join(final, "audit_statistics.json"), "w"), indent=1, default=str)

    trace = {
        "candidate": "MAIN_AUDIT", "primary_scorers": len(K.PRIMARY), "pairwise_comparisons": len(s3_pw),
        "h_threshold": K.H_THRESHOLD, "multiplicity_method": "Bonferroni", "family_alpha": K.FAMILY_ALPHA,
        "per_comparison_alpha": K.PER_COMPARISON_ALPHA, "z_one_sided": K.Z_BONF_ONE_SIDED,
        "hypothesis_name": "H1 in protocol audit-protocol-v1 (= H2 in the the main audit run brief)",
        "h_supported": h1["supported"], "n_pairs_meeting_threshold": h1["n_pairs_meeting"],
        "max_pair_disagreement": h1["max_rate"], "max_pair_disagreement_pair": h1["max_rate_pair"],
        "max_pair_lower_bound": h1["max_lower_bound"], "max_pair_lower_bound_pair": h1["max_lower_pair"],
        "s3_units": len(v3), "s3_unanimous": s3_unan["unanimous"],
        "s3_units_with_disagreement": s3_unan["at_least_one_disagreement"],
        "s1_oracle_agreement_by_scorer": {s: s1_sc[s]["oracle_agreement"] for s in ALL},
        "s1_interpretable_policy_differences": "REQUIRES_HUMAN_INTERPRETATION",
        "meaningful_real_disagreement": "REQUIRES_HUMAN_INTERPRETATION",
        "final_topic_decision": "REQUIRES_HUMAN_INTERPRETATION (recorded in audit_final_report.md / D-S14-01)",
    }
    json.dump(trace, open(os.path.join(final, "audit_decision_trace.json"), "w"), indent=2)
    figures(final, s3_pw, s1_dim, s1_cases)
    print(json.dumps({k: trace[k] for k in ["h_supported", "max_pair_disagreement", "max_pair_disagreement_pair",
                                            "max_pair_lower_bound", "s3_unanimous", "s3_units_with_disagreement"]}))


if __name__ == "__main__":
    main()
