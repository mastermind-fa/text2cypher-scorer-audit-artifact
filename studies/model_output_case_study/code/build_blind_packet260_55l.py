"""Blinded annotation packet for the frozen P6 selection (ext260). Model identity, scorer names and verdicts are excluded from annotator files."""
import csv, hashlib, json, re, sys
from pathlib import Path
T = Path(sys.argv[1]); sel = json.loads(Path(sys.argv[2]).read_text()); out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=False)
J = lambda p: [json.loads(l) for l in Path(p).read_text().splitlines()]
tr = {(t["model"], t["question_id"]): t for t in J(T / "gate40_scoring_runs/s55l_score260_01/execution_traces.jsonl")}
pk = {r["question_id"]: r for r in J(T / "data/packet_mtq_remaining260.jsonl")}
h = lambda s: hashlib.sha256(s.encode()).hexdigest()
cases = sorted(sel["cases"], key=lambda c: h("S55L-CASE|" + c["case_key"][0] + "|" + c["case_key"][1]))
blind, ev, mp = [], [], []
for i, c in enumerate(cases, 1):
    m, q = c["units"][0]; t = tr[(m, q)]; bid = "E260-%02d" % i
    swap = int(h("S55L-AB|seed55|" + q + "|" + c["case_key"][1])[0], 16) % 2 == 1
    a, b = (t["predicted_query"], t["reference_query"]) if swap else (t["reference_query"], t["predicted_query"])
    blind.append({"blind_id": bid, "question": pk[q]["question"], "graph_schema": pk[q]["schema"], "query_A": a, "query_B": b,
                  "instructions": "See ANNOTATION_PROTOCOL.md (first pass: query text and schema only)."})
    side = lambda s: {"columns": s["columns"], "n_rows": len(s["rows"]), "first_rows": s["rows"][:5]}
    ev.append({"blind_id": bid, "A_result": side(t["prediction"] if swap else t["reference"]), "B_result": side(t["reference"] if swap else t["prediction"])})
    mp.append({"blind_id": bid, "question_id": q, "units": c["units"], "kind": c["kind"], "A_is": "candidate" if swap else "reference"})
w = lambda n, rows: (out / n).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
w("blind_cases.jsonl", blind); w("second_pass_result_evidence.jsonl", ev); w("mapping_keep_separate.jsonl", mp)
cols = ["blind_id", "annotator_id", "question_status", "A_label", "A_justification", "B_label", "B_justification", "equivalence", "equivalence_justification",
        "pass2_A_label", "pass2_B_label", "pass2_equivalence", "pass2_justification"]
with open(out / "response_template.csv", "w", newline="") as f:
    wr = csv.writer(f); wr.writerow(cols); [wr.writerow([b["blind_id"]] + [""] * (len(cols) - 1)) for b in blind]
txt = (out / "blind_cases.jsonl").read_text() + (out / "second_pass_result_evidence.jsonl").read_text()
leak = [x for x in ("qwen", "mistral", "scorer", "cypherturn", "pipecypher", "verdict", "accepted", "gold", "reference", "candidate", "s55_", "pc_v1") if re.search(x, txt, re.I)]
qids = {x["question_id"] for x in mp}
old61 = (T / "adjudication/mapping_keep_separate.jsonl").read_text(); old11 = {json.loads(l)["question_id"] for l in (T / "gate40_final_package_55h/adjudication_packet/mapping_keep_separate.jsonl").read_text().splitlines()}
man = {"cases": len(blind), "disagreement_cases": sum(x["kind"] == "disagreement" for x in mp), "agreement_controls": sum(x["kind"] == "agreement_control" for x in mp),
       "units_covered": sum(len(x["units"]) for x in mp), "selection_file_sha256": hashlib.sha256(Path(sys.argv[2]).read_bytes()).hexdigest(),
       "ab_seed": "S55L-AB|seed55", "unique_ids": len({b["blind_id"] for b in blind}) == len(blind), "unique_case_keys": len({(x["question_id"], json.dumps(x["units"])) for x in mp}) == len(mp),
       "leak_terms_found": leak, "overlap_with_61_case_packet": sum(q in old61 for q in qids), "overlap_with_11_case_packet": len(qids & old11),
       "labels_collected": 0, "status": "TBD — independent human adjudication required", "blind_packet_sha256": hashlib.sha256((out / "blind_cases.jsonl").read_bytes()).hexdigest(),
       "mapping_must_not_be_given_to_annotators": True}
(out / "manifest.json").write_text(json.dumps(man, indent=1)); print(json.dumps(man))
