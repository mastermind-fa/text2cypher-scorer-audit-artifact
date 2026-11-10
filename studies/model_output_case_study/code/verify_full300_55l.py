"""S55L independent verification (separate implementation; does not import the analysis script or the evaluators)."""
import csv, hashlib, json, math, random, sys, zipfile
from collections import Counter, defaultdict
from pathlib import Path
T = Path(sys.argv[1]); A = json.loads(Path(sys.argv[2]).read_text()); out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=False)
G = T / "gate40_scoring_runs"; J = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines()]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
chk = {}; ok = lambda n, c, d=None: chk.__setitem__(n, {"pass": bool(c), "detail": d})
tr = {"gate40": J(G / "s55f_score_01/execution_traces.jsonl"), "ext260": J(G / "s55l_score260_01/execution_traces.jsonl")}
raw = {"gate40": json.loads((G / "s55h_scorer_replay_01/raw_native_outputs.json").read_text()), "ext260": json.loads((G / "s55l_scorer_replay260_01/raw_native_outputs.json").read_text())}
pk = {"gate40": [r["question_id"] for r in J(T / "data/packet_mtq_gate40.jsonl")], "ext260": [r["question_id"] for r in J(T / "data/packet_mtq_remaining260.jsonl")]}
ok("units_520_ext", len(tr["ext260"]) == 520 and Counter(t["model"] for t in tr["ext260"]) == Counter({"qwen": 260, "mistral": 260}))
ok("units_600_combined", sum(len(v) for v in tr.values()) == 600)
for st in tr:
    for m in ("qwen", "mistral"):
        ok("%s_%s_ids_exact" % (st, m), [t["question_id"] for t in tr[st] if t["model"] == m] == pk[st])
ok("stages_disjoint", not set(pk["gate40"]) & set(pk["ext260"]))
# predictions in traces equal the archive's extracted queries
z = zipfile.ZipFile(T / "inference260_import/s55_ext260_m41bt92n_artifacts.zip")
for m in ("qwen", "mistral"):
    arch = {r["question_id"]: r for r in map(json.loads, z.read("s55_%s_mtq_ext260.jsonl" % m).decode().splitlines())}
    ok("ext_%s_trace_predictions_equal_archive" % m, all(t["predicted_query"] == arch[t["question_id"]]["extracted_query"] for t in tr["ext260"] if t["model"] == m))
# gold identical across models; invalid references model-independent
for st in tr:
    by = defaultdict(set)
    skipped = [t["question_id"] for t in tr[st] if t["status"] == "extract_error"]   # frozen adapter executes nothing for extract errors
    for t in tr[st]:
        if t["status"] != "extract_error": by[t["question_id"]].add((t["reference_query"], json.dumps(t.get("reference"), sort_keys=True, default=str), t["status"] == "invalid_reference"))
    ok("%s_gold_identical_across_models" % st, all(len(v) == 1 for v in by.values()), {"skipped_extract_error_units": skipped})
# recount project metric
for st in ("gate40", "ext260"):
    for m in ("qwen", "mistral"):
        rows = [t for t in tr[st] if t["model"] == m]
        k = sum(t["status"] == "scored" and t["verdict"] == 1 for t in rows); ev = sum(t["status"] in ("scored", "execution_error", "extract_error") for t in rows)
        a = A["stages"][st]["per_model"][m]["primary"]; ok("%s_%s_project_k_and_evaluable" % (st, m), (k, ev) == (a["k"], a["N_evaluable"]), (k, ev))
        ok("%s_%s_errors_never_accepted" % (st, m), not any(t["verdict"] == 1 for t in rows if t["status"] != "scored"))
for m in ("qwen", "mistral"):
    c = A["stages"]["combined300"]["per_model"][m]["primary"]; g, e = (A["stages"][s]["per_model"][m]["primary"] for s in ("gate40", "ext260"))
    ok("combined_%s_is_sum_of_stages" % m, c["k"] == g["k"] + e["k"] and c["N_evaluable"] == g["N_evaluable"] + e["N_evaluable"] and c["N_total"] == 300)
# recount every replayed scorer from raw native outputs
for st in raw:
    scored = {(t["model"], t["question_id"]) for t in tr[st] if t["status"] == "scored"}
    for s, d in raw[st].items():
        ok("%s_%s_raw_units_equal_scored" % (st, s), {tuple(k.split("|", 1)) for k in d} == scored)
        for m in ("qwen", "mistral"):
            k = sum(1 for kk, v in d.items() if kk.startswith(m + "|") and v["verdict"] == 1)
            ok("%s_%s_%s_k" % (st, s, m), k == A["stages"][st]["per_scorer"][s][m]["primary"]["k"], k)
        ok("%s_%s_exceptions_explicit" % (st, s), all(v["verdict"] in (0, 1) or str(v["verdict"]).startswith("ERROR:") for v in d.values()))
# pairwise disagreement recount (ext260 and gate40), project vs every replayed column, and CypherTurn vs CypherBench
proj = {st: {(t["model"], t["question_id"]): (1 if t["verdict"] == 1 else 0) for t in tr[st] if t["status"] == "scored"} for st in tr}
for st in raw:
    for s in raw[st]:
        el = [k for k in proj[st] if raw[st][s]["%s|%s" % k]["verdict"] in (0, 1)]
        dis = sum(proj[st][k] != raw[st][s]["%s|%s" % k]["verdict"] for k in el)
        rec = A["stages"][st]["pairwise"].get("s55_project_ex_official|" + s)
        ok("%s_pair_project_%s" % (st, s), rec and (rec["eligible"], rec["disagree"]) == (len(el), dis), (len(el), dis))
# paired statistics reproduced independently (project metric, combined, primary)
units = {}
for st in tr:
    for t in tr[st]:
        rr = (t.get("reference") or {}).get("rows") if isinstance(t.get("reference"), dict) else None
        units[(t["model"], t["question_id"])] = (None if t["status"] in ("invalid_reference", "unsupported") else int(t["status"] == "scored" and t["verdict"] == 1), t["graph"],
                                                 rr is not None and ((not rr) or all(c is None for r in rr for c in r)))
flags = {r["question_id"]: (r["near_manual_train_jaccard_ge_0_8"] == "1", r["internal_near_cluster_id"]) for r in csv.DictReader((T / "data/near_overlap_flags.csv").open())}
for view in ("primary", "sensitivity"):
    d = [(q, units[("qwen", q)][0] - units[("mistral", q)][0]) for q in pk["gate40"] + pk["ext260"] if units[("qwen", q)][0] is not None and units[("mistral", q)][0] is not None
         and not (view == "sensitivity" and (units[("qwen", q)][2] or units[("mistral", q)][2]))]
    n = len(d); b = sum(x == 1 for _, x in d); c = sum(x == -1 for _, x in d)
    p = min(1.0, 2 * sum(math.comb(b + c, i) for i in range(min(b, c) + 1)) / 2 ** (b + c))
    rng = random.Random(55); vals = [x for _, x in d]; bs = sorted(sum(vals[rng.randrange(n)] for _ in range(n)) / n for _ in range(10000))
    R = A["stages"]["combined300"]["ranking"]["s55_project_ex_official"][view]
    ok("stats_%s_reproduced" % view, (n, b - c, round(p, 6), [round(bs[249], 4), round(bs[9749], 4)]) == (R["n_paired"], R["qwen_minus_mistral_count"], R["mcnemar_exact_p"], R["question_bootstrap95"]),
       {"n": n, "diff": b - c, "b": b, "c": c, "p": p, "qCI": [bs[249], bs[9749]]})
# overlap membership and graph coverage
ok("overlap_counts", (sum(flags[q][0] for q in pk["ext260"]), sum(flags[q][0] for q in pk["gate40"] + pk["ext260"])) == (74, 84))
for m in ("qwen", "mistral"):
    ok("overlap_%s_reconciles" % m, sum(A["stages"]["combined300"]["overlap"][m][x]["N"] for x in ("flagged", "unflagged")) == 300 and A["stages"]["combined300"]["overlap"][m]["flagged"]["N"] == 84)
gc = Counter(t["graph"] for t in tr["ext260"] if t["model"] == "qwen"); ok("ext_graph_coverage", gc == Counter({"er": 130, "wwc": 84, "healthcare": 44, "bloom": 2}), dict(gc))
# graph integrity before/after
man = json.loads((G / "s55l_score260_01/execution_manifest.json").read_text())
ok("integrity_before_after", all(man["preflight"][g]["stable_snapshot"] == man["stable_snapshot_after"][g] for g in man["stable_snapshot_after"]) and len(man["stable_snapshot_after"]) == 4)
ok("write_denied_all_four", all(man["preflight"][g].get("write_denied") for g in man["preflight"]))
ok("score_sha256sums", all(sha(G / "s55l_score260_01" / n) == h for h, n in (l.split("  ", 1) for l in (G / "s55l_score260_01/SHA256SUMS").read_text().splitlines())))
ok("frozen_metric_adapter_hashes", sha(T / "evaluation/project_ex.py") == man["evaluator_sha256"] and sha(T / "evaluation/score_predictions.py") == man["adapter_sha256"])
ok("archive_hash_in_manifest", man["predictions_archive_sha256"] == "32c4731bd0791492b69c58d878a464e48bce29df66b76304ee0ab2ed2364def7")
res = {"all_pass": all(v["pass"] for v in chk.values()), "n_checks": len(chk), "checks": chk}
(out / "independent_verification.json").write_text(json.dumps(res, indent=1, default=str))
print(res["all_pass"], res["n_checks"], [k for k, v in chk.items() if not v["pass"]])
