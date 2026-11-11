#!/usr/bin/env python3
"""Network-free check of the post hoc numbers quoted in paper Section VII ("Limits") against
verdicts/case_study_units.csv (post hoc run) and ../verdicts/case_study_units.csv (frozen run).
usage: python3 check_paper_numbers.py"""
import csv, json, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]; CS = HERE.parent
sys.path.insert(0, str(CS / "code"))
import project_ex
POST = list(csv.DictReader((HERE / "verdicts/case_study_units.csv").open()))
FROZ = {(u["model"], u["question_id"]): u for u in csv.DictReader((CS / "verdicts/case_study_units.csv").open())}
EXP = json.loads((HERE / "expected/expected_case_study.json").read_text())
B = "s55_project_ex_official"
def v(u, s):
    st, x = u["status__" + s], u["verdict__" + s]
    if st == "supported_scored": return int(x == "1")
    if st in ("execution_error", "extract_error"): return 0
    return None
def gate_ok(q):
    try: project_ex.read_only_query(q); return True
    except Exception: return False
ok = True
def chk(name, got, want):
    global ok; good = got == want; ok &= good
    print(("OK  " if good else "FAIL"), name, got, "" if good else "(paper: %s)" % (want,))
# predictions the frozen gate rejects only for one trailing semicolon
preds = {}
for f in sorted((CS / "predictions").glob("s55_*_mtq_*.jsonl")):
    m = "qwen" if "_qwen_" in f.name else "mistral"
    for line in f.open():
        d = json.loads(line); preds[(m, d["question_id"])] = d.get("extracted_query") or ""
for m, want in (("qwen", 79), ("mistral", 17)):
    n = sum(1 for (mm, q), text in preds.items() if mm == m and FROZ[(mm, q)]["candidate_error"].startswith("QueryRejected")
            and not gate_ok(text) and gate_ok(re.sub(r";\s*$", "", text.strip())))
    chk("%s predictions admitted once one trailing ';' is ignored" % m, n, want)
for m, acc, n in (("qwen", 72, 285), ("mistral", 28, 284)):
    us = [u for u in POST if u["model"] == m]
    chk("%s baseline accepted (post hoc)" % m, sum(v(u, B) == 1 for u in us), acc)
    chk("%s evaluable (post hoc)" % m, sum(v(u, B) is not None for u in us), n)
chk("gold queries newly evaluable (qwen)", sum(1 for u in POST if u["model"] == "qwen" and u["baseline_status"] != "invalid_reference"
    and FROZ[("qwen", u["question_id"])]["baseline_status"] == "invalid_reference"), 7)
S = EXP["shifts"]
chk("CypherTurn shift, Qwen", round(S["combined300|qwen|cypherturn|all"]["points"], 1), -11.9)
chk("PIPE-Cypher shift, Qwen", round(S["combined300|qwen|pipecypher|all"]["points"], 1), -9.8)
chk("Text2GQL driver shift, Qwen", round(S["combined300|qwen|tugraph|all"]["points"], 1), -3.5)
chk("Text2GQL driver shift, Qwen, unflagged", round(S["combined300|qwen|tugraph|unflagged"]["points"], 1), -1.9)
R = EXP["ranking"]["combined300|primary"]
chk("ranking check assessable (>= 30 paired comparable questions outside ER)", R["paired_comparable_non_er"] >= 30, True)
chk("Qwen ahead of Mistral (post hoc, baseline)", R["qwen_minus_mistral"] > 0, True)
by = {(u["model"], u["question_id"]): u for u in POST}
for name, sel in (("entity-resolution graph", lambda g: g == "er"), ("other graphs", lambda g: g != "er")):
    d = [v(by[("qwen", q)], B) - v(by[("mistral", q)], B) for (m, q), u in by.items() if m == "qwen" and sel(u["graph"])
         and u["baseline_status"] == "scored" and by[("mistral", q)]["baseline_status"] == "scored"]
    chk("Qwen minus Mistral > 0 on paired comparable questions, %s (n=%d, diff=%d)" % (name, len(d), sum(d)), sum(d) > 0, True)
print("mistral shifts (post hoc):", {s: S["combined300|mistral|%s|all" % s]["points"] for s in ("cypherturn", "pipecypher", "tugraph")})
print("ranking (post hoc):", R)
print("RESULT:", "PASS" if ok else "FAIL"); sys.exit(0 if ok else 1)
