#!/usr/bin/env python3
"""study S23 overlap check (s23-overlap-v1). OFFLINE, read-only.

Compares every ELIGIBLE Mind the Query source (normalised NL question, normalised gold Cypher, SHA-256 of the
normalised Cypher) with: the Works-Cycles project corpus (database/dataset.json), the project splits
(dataset/neo4j/{train,test}.jsonl, dataset/val.jsonl), CypherTurn released utterances and gold Cypher, and the
study S18 / study S20 frozen case queries. Normalisation: lower-case, collapse every non-alphanumeric run to one space.
  python s23_overlap.py <mtq_dir> <out.json>
"""
import glob, hashlib, json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
sys.path.insert(0, HERE)
from s23_rules import load_sources


def norm(s): return re.sub(r"[^0-9a-z]+", " ", (s or "").lower()).strip()
def h(s): return hashlib.sha256(norm(s).encode()).hexdigest()


def collect():
    sets = {}
    d = json.load(open(os.path.join(ROOT, "database", "dataset.json")))
    sets["works_cycles_corpus"] = ({norm(x["question"]) for x in d}, {h(x["cypher"]) for x in d})
    q, c = set(), set()
    for f in ["dataset/neo4j/train.jsonl", "dataset/neo4j/test.jsonl", "dataset/val.jsonl"]:
        for l in open(os.path.join(ROOT, f)):
            r = json.loads(l); q.add(norm(r.get("question"))); c.add(h(r.get("cypher") or ""))
    sets["project_splits_neo4j_val"] = (q, c)
    q, c = set(), set()
    for f in glob.glob(os.path.join(ROOT, "external", "cypherturn", "data", "scenarios", "*.json")):
        for s in json.load(open(f)):
            for t in s["turns"]: q.add(norm(t.get("user_utterance"))); c.add(h(t.get("gold_cypher") or ""))
    sets["cypherturn"] = (q, c)
    for name, p in [("native_cypherturn_validation", "studies/native_cypherturn_validation/native_cypher/frozen/20261030T083217Z_native_cypher_input/cases.jsonl"),
                    ("native_cypherturn_stress", "studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143740Z_input/cases.jsonl")]:
        c = set()
        for l in open(os.path.join(ROOT, p)):
            x = json.loads(l); c.add(h(x["reference"]["query"])); c.add(h(x["prediction"]["query"]))
        sets[name] = (set(), c)
    return sets


def main():
    mtq, out = sys.argv[1:3]
    src, _ = load_sources(mtq)
    mq = {norm(s["question"]) for s in src}; mc = {h(s["gold_cypher"]) for s in src}
    rep = {"eligible_sources": len(src), "normalisation": "lower-case; non-alphanumeric runs -> single space",
           "comparisons": {}}
    for name, (q, c) in collect().items():
        rep["comparisons"][name] = {"question_overlap": len(mq & q) if q else None, "cypher_hash_overlap": len(mc & c),
                                    "reference_questions": len(q), "reference_queries": len(c)}
    rep["any_overlap"] = any((v["question_overlap"] or 0) + v["cypher_hash_overlap"] for v in rep["comparisons"].values())
    json.dump(rep, open(out, "w"), indent=2)
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
