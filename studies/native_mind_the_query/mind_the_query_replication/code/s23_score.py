#!/usr/bin/env python3
"""study S23 scoring + pre-specified replication classification (s23-score-v1). Runs ONLY on a frozen, hash-verified
S23 input package and a frozen, hash-verified preregistration.

Each of the 7 primary (+2 secondary, context only) scorers is invoked once per case through the FROZEN Study-14
runner (run_experiment_v1_1.py: frozen Study-13 adapters, hash-checked; network blocked; per-case 120 s limit), set
name "s23" (passed through unchanged, as "s20" was). No scorer logic is changed. Descriptive statistics only, per class
(the study S18 `analyse` function, unchanged); classes are never pooled. The replication status of each class is
computed by the frozen s23_replication rubric against the reference patterns frozen in the preregistration.
  python s23_score.py <frozen_input_dir> <prereg_dir> <out_dir>
"""
import csv, hashlib, json, os, re, subprocess, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "studies", "native_cypherturn_validation", "native_cypher", "code"))
from s18_score import analyse, PRIMARY, SECONDARY, RUNNER  # frozen S18 analysis, reused unchanged
import s23_replication as REP

ABBR = {"cypherturn": "CT", "cypherbench": "CB", "gqlbench": "GQ", "tugraph": "TG", "pipecypher": "PIPE",
        "cypherlens": "CL", "cyspider": "CS"}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def verify(d):
    for l in open(os.path.join(d, "hashes.sha256")):
        h, fn = l.split()
        assert sha(os.path.join(d, fn)) == h, f"freeze violated: {d}/{fn}"


def is_cypher(q): return bool(re.search(r"\bRETURN\b", q, re.I)) and not re.search(r"\bSELECT\b", q, re.I)


def pattern_str(cats):
    acc = [ABBR[s] for s in PRIMARY if cats[s] == "ACCEPT"]; rej = [ABBR[s] for s in PRIMARY if cats[s] == "REJECT"]
    oth = [f"{ABBR[s]}:{cats[s]}" for s in PRIMARY if cats[s] not in ("ACCEPT", "REJECT")]
    return "; ".join(x for x in [("accept " + "/".join(acc)) if acc else "", ("reject " + "/".join(rej)) if rej else "",
                                 ", ".join(oth)] if x)


def main():
    fin, prereg_dir, out = sys.argv[1:4]
    verify(fin); verify(prereg_dir)
    pre = json.load(open(os.path.join(prereg_dir, "preregistration.json")))
    for name, h in pre["code_sha256"].items():
        assert sha(os.path.join(HERE, name)) == h, f"code changed after preregistration: {name}"
    src = json.load(open(os.path.join(fin, "source_manifest.json")))
    assert src["preregistration_hashes_sha256"] == sha(os.path.join(prereg_dir, "hashes.sha256")), "prereg mismatch"
    cases = [json.loads(l) for l in open(os.path.join(fin, "cases.jsonl"))]
    assert all(is_cypher(c["reference"]["query"]) and is_cypher(c["prediction"]["query"]) for c in cases), "non-Cypher side"
    assert all(c["reference"]["query"] != c["prediction"]["query"] for c in cases), "identical query text"
    os.makedirs(os.path.join(out, "raw"), exist_ok=False)
    cls = {c["case_id"]: c["meta"]["family"] for c in cases}
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    verdicts = {c["case_id"]: {} for c in cases}
    log = {"runner": RUNNER, "runner_sha256": sha(RUNNER), "input_hashes_sha256": sha(os.path.join(fin, "hashes.sha256")),
           "preregistration_hashes_sha256": sha(os.path.join(prereg_dir, "hashes.sha256")), "runs": []}
    for s in PRIMARY + SECONDARY:
        rp = os.path.join(out, "raw", f"{s}.jsonl")
        p = subprocess.run([sys.executable, RUNNER, s, "s23", os.path.join(fin, "cases.jsonl"), rp],
                           capture_output=True, text=True, env=env, timeout=3600)
        if p.returncode != 0: raise SystemExit(f"runner failed for {s}: {p.stderr[-800:]}")
        os.chmod(rp, 0o444); log["runs"].append(p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "")
        for l in open(rp):
            r = json.loads(l); verdicts[r["case_id"]][s] = r["verdict"]
    res = {"by_class": {}, "overall_descriptive_only": analyse(verdicts, cls)}
    for k in sorted(set(cls.values())):
        sub = {c: v for c, v in verdicts.items() if cls[c] == k}
        res["by_class"][k] = analyse(sub, {c: k for c in sub})
    # ---- pre-specified replication classification (frozen rubric) -----------------------------------------------
    s20, s1 = pre["reference_patterns"]["s20_by_class"], pre["reference_patterns"]["s1_prior_new_classes"]
    rep, status = {}, {}
    for k in sorted(set(cls.values()) | set(REP.S20_MAP) | set(REP.NEW_CLASSES) | set(REP.MECHANISM_CLASS)):
        ids = [c for c in verdicts if cls[c] == k]
        cats = {s: REP.category([verdicts[c][s] for c in ids]) for s in PRIMARY}
        per_graph = Counter(next(x["meta"]["graph"] for x in cases if x["case_id"] == c) for c in ids)
        entry = {"n": len(ids), "per_graph": per_graph, "mtq_categories": cats, "mtq_pattern": pattern_str(cats) if ids else "—"}
        if k in REP.S20_MAP:
            ref = s20[REP.S20_MAP[k]]; st, mism = REP.classify(ref, cats, len(ids))
            entry.update({"reference": "study S20 " + REP.S20_MAP[k], "reference_categories": ref,
                          "reference_pattern": pattern_str(ref), "status": st, "mismatching_scorers": mism})
        elif k in REP.MECHANISM_CLASS:
            cs = [{"case_id": c["case_id"], "null_columns": (c["meta"]["oracle_detail"] or {}).get("null_columns")}
                  for c in cases if cls[c["case_id"]] == k]
            st, mism, extra = REP.classify_r8(cs, verdicts)
            entry.update({"reference": "study S20 D5 mechanism (GQLBench numeric NULL -> NaN)", "status": st,
                          "mismatching_scorers": mism, **extra,
                          "reference_pattern": "accept all except GQ rejects numeric-NULL cases"})
        elif k in REP.NEW_CLASSES:
            ref = s1[k]; st1, mism = REP.classify(ref, cats, len(ids), ("CONSISTENT_WITH_S1", "PARTIALLY_CONSISTENT_WITH_S1",
                                                                       "INCONSISTENT_WITH_S1"))
            st = "NOT_TESTABLE" if st1 == "NOT_TESTABLE" else "NEW_EVIDENCE"
            entry.update({"reference": "none in study S20; S1 prior " + ",".join(REP.NEW_CLASSES[k]),
                          "reference_categories": ref, "reference_pattern": "S1: " + pattern_str(ref), "status": st,
                          "s1_consistency": st1, "mismatching_scorers_vs_s1": mism})
        rep[k] = entry; status[k] = entry.get("status")
    decision, why = REP.session_decision(status)
    res["replication"] = rep; res["study_decision_by_frozen_rule"] = {"decision": decision, **why}
    json.dump(res, open(os.path.join(out, "s23_statistics.json"), "w"), indent=1, default=dict)
    json.dump(log, open(os.path.join(out, "run_log.json"), "w"), indent=1)
    with open(os.path.join(out, "s23_verdicts.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["case_id", "class", "equivalence_class", "graph"] + PRIMARY + SECONDARY)
        for c in cases:
            w.writerow([c["case_id"], cls[c["case_id"]], c["meta"]["equivalence_class"], c["meta"]["graph"]]
                       + [verdicts[c["case_id"]][s] for s in PRIMARY + SECONDARY])
    with open(os.path.join(out, "cross_benchmark_table.md"), "w") as f:
        f.write("| Policy class | n (MtQ) | Reference pattern | Mind the Query pattern | Status |\n|---|---:|---|---|---|\n")
        for k, e in rep.items():
            extra = f" (S1: {e['s1_consistency']})" if "s1_consistency" in e else ""
            f.write(f"| {k} | {e['n']} | {e.get('reference_pattern', '—')} | {e['mtq_pattern']} | {e['status']}{extra} |\n")
        f.write(f"\nSession decision by the frozen rule: **{decision}**\n")
    lines = [f"{sha(os.path.join(dp, f))}  {os.path.relpath(os.path.join(dp, f), out)}"
             for dp, _, fs in sorted(os.walk(out)) for f in sorted(fs) if f != "hashes.sha256"]
    open(os.path.join(out, "hashes.sha256"), "w").write("\n".join(lines) + "\n")
    print(open(os.path.join(out, "cross_benchmark_table.md")).read())


if __name__ == "__main__":
    main()
