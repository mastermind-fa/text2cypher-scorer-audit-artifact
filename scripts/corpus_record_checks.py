#!/usr/bin/env python3
"""Network-free check of the corpus record statements of the paper (Sections III-B and VI) against the dataset release.

  python3 scripts/corpus_record_checks.py DATASET_DIR        (a clone of text2cypher-corpus at v1.0.1)

Checks the record counts (distinct questions, recurring SQL and Cypher strings, empty pairs, identical column names),
the defective records (one Cypher query shared by three unrelated questions; one record carrying another question's
queries), the pairs rejected by every scorer and their provenance, and the result features of the pairs S3-473, S3-479
and S3-512 discussed in Section VI. Reads only released files; exits 1 on any difference."""
import csv, json, sys
from collections import Counter
from pathlib import Path
if len(sys.argv) != 2:
    sys.exit(__doc__)
D = Path(sys.argv[1])
R = [json.loads(l) for l in (D / "corpus/records_release_candidate.jsonl").open()]
V = {r["case_id"]: r for r in csv.DictReader((D / "verdicts/corpus/s3_results.csv").open())}
PROV = {r["s3_case_id"]: r["provenance_class"] for r in csv.DictReader((D / "corpus/provenance.csv").open())}
BY = {r["s3_case_id"]: r for r in R}
SIX = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cyspider"]
ok = True


def chk(name, got, want):
    global ok
    good = got == want; ok &= good
    print(("OK  " if good else "FAIL"), name + ":", got, "" if good else "(paper: %s)" % (want,))


def recur(field):
    c = Counter(r[field].strip() for r in R); d = [n for n in c.values() if n > 1]
    return len(c), len(d), sum(d)


chk("records", len(R), 563)
chk("distinct questions", recur("question")[0], 562)
chk("SQL strings that recur", recur("SQL")[1], 2)
chk("Cypher strings that recur / records they cover", recur("cypher")[1:], (3, 7))
empty = [r for r in R if not r["sql_output"] and not r["neo4j_output"]]
chk("pairs empty on both sides", len(empty), 9)
chk("empty pairs accepted by all seven primary scorers",
    all(V[r["s3_case_id"]][s] == "1" for r in empty for s in SIX + ["cypherlens"]), True)
ne = [r for r in R if r["sql_output"] and r["neo4j_output"]]
same = sum(list(r["sql_output"][0]) == list(r["neo4j_output"][0]) for r in ne)
chk("non-empty pairs / with identical column names", (len(ne), same), (554, 545))
# defective records
cy = Counter(r["cypher"].strip() for r in R)
shared = [r for r in R if cy[r["cypher"].strip()] == 3]
chk("records sharing one Cypher query across three different questions",
    (len(shared), len({r["question"] for r in shared}), all(not r["sql_output"] and not r["neo4j_output"] for r in shared)), (3, 3, True))
print("     records:", sorted(r["record_id"] for r in shared))
dup = [(a["record_id"], b["record_id"]) for i, a in enumerate(R) for b in R[i + 1:]
       if a["SQL"].strip() == b["SQL"].strip() and a["cypher"].strip() == b["cypher"].strip() and a["question"] != b["question"]
       and cy[a["cypher"].strip()] == 2]
chk("record pairs with the same SQL and Cypher but different questions", dup, [("WC-400", "WC-432")])
# unanimous rejections and provenance
rej6 = [c for c, r in V.items() if all(r[s] == "0" for s in SIX)]
rej7 = [c for c in rej6 if V[c]["cypherlens"] == "0"]
chk("pairs rejected by all seven primary scorers / project-written among them",
    (len(rej7), sum("project_written" in PROV[c] for c in rej7)), (9, 9))
chk("further pair rejected by the six in-domain scorers only (BIRD official; CypherLens accepts)",
    [(c, "bird_official" in PROV[c], V[c]["cypherlens"]) for c in rej6 if c not in rej7], [("S3-201", True, "1")])
# Section VI pairs
def rows(c):
    r = BY[c]; return r["sql_output"], r["neo4j_output"]
a, b = rows("S3-473")
diff = {(k, type(x[k]).__name__, type(y[k]).__name__) for x, y in zip(a, b) for k in x if type(x[k]) is not type(y[k])}
chk("S3-473: rows, rows equal in sequence (values compare equal), type differences",
    (len(a), len(b), all(x == y for x, y in zip(a, b)), sorted(diff)), (22790, 22790, True, [("DelayDays", "float", "int")]))
chk("S3-473 verdicts (CT, CB, GQ, TG driver, PIPE, CS)", [V["S3-473"][s] for s in SIX], ["0", "0", "0", "1", "0", "1"])
a, b = rows("S3-479")
num = lambda v: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v
bag = lambda rs: sorted(tuple((k, num(v)) for k, v in r.items()) for r in rs)
chk("S3-479: rows differ in sequence, same bag once integers and floats are unified; verdicts",
    (a != b, bag(a) == bag(b), [V["S3-479"][s] for s in SIX]), (True, True, ["0", "0", "0", "0", "0", "1"]))
iff = sorted(c for c, r in V.items() if "int_float_type_difference" in r["features"] and len({r[s] for s in SIX}) > 1)
chk("non-unanimous integer-versus-float pairs", iff, ["S3-458", "S3-473", "S3-479", "S3-483"])
a, b = rows("S3-512")
chk("S3-512: NULL territory first in the SQL output, last in the Cypher output",
    (a[0]["territory_name"], b[-1]["territory_name"], a[1:] == b[:-1]), (None, None, True))
print("RESULT:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
