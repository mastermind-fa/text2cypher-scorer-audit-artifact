#!/usr/bin/env python3
"""Paper headline numbers recomputed from the released frozen verdicts (artifact v1.0.0). No network, no scorer run.

  python3 scripts/paper_numbers.py                        # artifact only
  CORPUS_DIR=/path/to/text2cypher-corpus python3 scripts/paper_numbers.py   # adds the provenance split (needs the corpus)

Each EXPECTED value is the number stated in the paper. A mismatch prints FAIL and the script exits 1. Complements
quick_check.py (pairwise test, S2, native suites)."""
import csv, itertools, json, math, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AUDIT = os.path.join(ROOT, "studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final")
REPAIR = os.path.join(ROOT, "studies/validation_repair/validity_repair")
PRIMARY = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
IN_DOMAIN = [s for s in PRIMARY if s != "cypherlens"]  # CypherLens receives SQL text as candidate query (out of domain)
Z = 2.8227138814289363  # one-sided, alpha = 0.05 / 21
EXPECTED = {
    "S3 acceptances (of 563)": {"cypherturn": 529, "cypherbench": 529, "gqlbench": 524, "tugraph": 542, "pipecypher": 536,
                                "cypherlens": 171, "cyspider": 542},
    "S3 in-domain pairs meeting the criterion (of 15)": 5,
    "S3 all primary pairs meeting the criterion (of 21)": 11,
    "S3 in-domain acceptance range (%)": (93.1, 96.3),
    "Text2GQL pipeline evaluator (metrics.py) accepts (of 563)": 542,
    "Text2GQL reference evaluator (ea_cypher.py) accepts (of 563)": 556,
    "Text2GQL evaluators differ on (of 563)": 14,
    "S1 corrected: agreement with oracle (of 106)": {"cypherturn": 71, "cypherbench": 99, "gqlbench": 97, "tugraph": 90,
                                                     "pipecypher": 76, "cypherlens": 89, "cyspider": 80},
    "Model level: correct of 138 (qwen3-4b, phi3.5-mini-instruct)": {"cypherturn": (0, 0), "cypherbench": (2, 3),
                                                                     "gqlbench": (2, 3), "tugraph": (2, 3), "pipecypher": (2, 3),
                                                                     "cypherlens": (14, 2), "cyspider": (2, 3)},
    "S3 six-scorer non-unanimous: project-written / BIRD-derived": ((20, 99), (21, 464)),
}
FAIL = []


def check(name, got):
    ok = got == EXPECTED[name]
    FAIL.extend([] if ok else [name])
    print(f"[{'OK' if ok else 'FAIL'}] {name}: {got}" + ("" if ok else f" (paper: {EXPECTED[name]})"))


def lower(k, n):
    p = k / n; d = 1 + Z * Z / n
    return (p + Z * Z / (2 * n) - Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n))) / d


def meeting(rows, scorers):
    return sum(lower(sum(r[a] != r[b] for r in rows), len(rows)) > 0.02 for a, b in itertools.combinations(scorers, 2))


def main():
    s3 = list(csv.DictReader(open(os.path.join(AUDIT, "s3_results.csv"))))
    check("S3 acceptances (of 563)", {s: sum(r[s] == "1" for r in s3) for s in PRIMARY})
    check("S3 in-domain pairs meeting the criterion (of 15)", meeting(s3, IN_DOMAIN))
    check("S3 all primary pairs meeting the criterion (of 21)", meeting(s3, PRIMARY))
    rates = [100 * sum(r[s] == "1" for r in s3) / len(s3) for s in IN_DOMAIN]
    check("S3 in-domain acceptance range (%)", (round(min(rates), 1), round(max(rates), 1)))

    t2 = [r for r in csv.DictReader(open(os.path.join(REPAIR, "text2gql/ea_cypher_verdicts.csv"))) if r["set"] == "s3"]
    check("Text2GQL pipeline evaluator (metrics.py) accepts (of 563)", sum(r["metrics_py_verdict"] == "1" for r in t2))
    check("Text2GQL reference evaluator (ea_cypher.py) accepts (of 563)", sum(r["ea_cypher_verdict"] == "1" for r in t2))
    check("Text2GQL evaluators differ on (of 563)", sum(r["agree"] != "True" for r in t2))

    s1 = [r for r in csv.DictReader(open(os.path.join(REPAIR, "s1_corrected/s1_corrected_results.csv")))
          if r["expected"] != "INTENT_DEPENDENT"]
    agree = lambda r, s: (r[s] == "1" and r["expected"] == "EQUIV") or (r[s] == "0" and r["expected"] == "NONEQUIV")
    check("S1 corrected: agreement with oracle (of 106)", {s: sum(agree(r, s) for r in s1) for s in PRIMARY})

    ml = {m["scorer"]: (int(m["qwen3-4b_correct"]), int(m["phi3.5-mini-instruct_correct"]))
          for m in csv.DictReader(open(os.path.join(REPAIR, "model_level_sensitivity/model_level_ex.csv")))}
    check("Model level: correct of 138 (qwen3-4b, phi3.5-mini-instruct)", {s: ml[s] for s in PRIMARY})

    corpus = os.environ.get("CORPUS_DIR")
    rec = os.path.join(corpus or "", "corpus", "records_release_candidate.jsonl")
    if corpus and os.path.exists(rec):
        cls = {}
        for line in open(rec, encoding="utf-8"):
            r = json.loads(line); cls[r["s3_case_id"]] = r["provenance_class"].startswith("R-C")
        non = [r for r in s3 if len({r[s] for s in IN_DOMAIN}) > 1]
        pw = sum(cls[r["case_id"]] for r in non)
        check("S3 six-scorer non-unanimous: project-written / BIRD-derived",
              ((pw, sum(cls.values())), (len(non) - pw, len(cls) - sum(cls.values()))))
    else:
        print("[SKIP] provenance split: set CORPUS_DIR to the corpus repository (https://github.com/mastermind-fa/text2cypher-corpus)")
    print(f"\nPAPER NUMBERS: {'PASS' if not FAIL else 'FAIL'} ({len(FAIL)} failures)")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
