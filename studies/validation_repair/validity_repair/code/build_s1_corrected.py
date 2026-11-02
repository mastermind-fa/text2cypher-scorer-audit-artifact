#!/usr/bin/env python3
"""Build the query-consistent controlled suite (the validation repair validity repair; rules frozen in preregistration/PLAN.md A2).

  python3.12 studies/validation_repair/validity_repair/code/build_s1_corrected.py

Reads the FROZEN studies/controlled_suite/audit/s1/s1_cases.jsonl (never modified). Writes:
  s1_corrected/s1_corrected_cases.jsonl   121 records; only ref_query / pred_query of affected fixtures differ
  s1_corrected/correction_manifest.csv    one row per corrected fixture
Fails (exit 1) on any validation violation (PLAN A2.6)."""
import csv, json, os, re, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
SRC = os.path.join(ROOT, "studies/controlled_suite/audit/s1/s1_cases.jsonl")
OUT = os.path.join(ROOT, "studies/validation_repair/validity_repair/s1_corrected")
RET = re.compile(r"^(?P<head>.*?\bRETURN\s+(?:DISTINCT\s+)?)(?P<items>.*?)(?P<tail>\s+(?:ORDER BY|SKIP|LIMIT)\b.*)?$", re.I | re.S)
RENAME = {"x": "y", "p": "q", "q": "r"}


def split_items(items):  # commas outside (), {}
    return [x.strip() for x in re.split(r",(?![^(){}]*[)}])", items)] if items.strip() else []


def parse_item(it):
    m = re.match(r"^(?P<expr>.*?)\s+AS\s+(?P<alias>\S+)$", it, re.I | re.S)
    return (m.group("expr").strip(), m.group("alias")) if m else (it, it)


def aliases(q):
    m = RET.match(q)
    return {parse_item(i)[1] for i in split_items(m.group("items"))} if m else set()


def bound_vars(q):  # node variables bound in MATCH patterns, in order
    head = RET.match(q).group("head")
    return re.findall(r"\(\s*([A-Za-z_]\w*)\s*(?::|\)|\{)", head)


def rename_var(q, old, new):
    return re.sub(rf"\b{re.escape(old)}\b(?=\s*[.:)\]{{,]|\s*$|\s+AS\b|\))", new, q)


def correct_side(q, cols):
    """Rules A2.1, A2.2, A2.4: rebuild the RETURN item list so its aliases are exactly `cols`."""
    m = RET.match(q)
    head, tail = m.group("head"), m.group("tail") or ""
    orig = [parse_item(i) for i in split_items(m.group("items"))]
    var0 = bound_vars(q)[0]
    out = []
    for i, c in enumerate(cols):
        if "." in c or "(" in c:                                   # (a) expression key, unaliased
            out.append(c)
        elif any(a == c for _, a in orig):                         # (b) reuse item with that alias
            e, a = next((e, a) for e, a in orig if a == c)
            out.append(f"{e} AS {c}" if e != c else c)
        elif c.endswith("_alias") and any(a == c[:-6] for _, a in orig):  # (c) renamed alias
            out.append(f"{next(e for e, a in orig if a == c[:-6])} AS {c}")
        elif i < len(orig):                                        # (d) positional expression
            e = orig[i][0]
            out.append(f"{e}.{c} AS {c}" if re.fullmatch(r"[A-Za-z_]\w*", e) else f"{e} AS {c}")
        else:                                                      # (e) property of the first bound variable
            out.append(f"{var0}.{c} AS {c}")
    new = head + ", ".join(out) + tail
    # rule 4: expression keys must name a bound variable of this side
    keyvars = {re.match(r"^(?:\w+\()?([A-Za-z_]\w*)\.", c).group(1) for c in cols
               if re.match(r"^(?:\w+\()?([A-Za-z_]\w*)\.", c)}
    keyvars |= {re.match(r"^\w+\(([A-Za-z_]\w*)\)$", c).group(1) for c in cols if re.match(r"^\w+\(([A-Za-z_]\w*)\)$", c)}
    for kv in keyvars:
        bv = bound_vars(new)
        if kv not in bv:
            # rename the side's first bound variable (the one the original text used for this entity) in MATCH/tail
            head2 = rename_var(RET.match(new).group("head"), bv[0], kv)
            tail2 = rename_var(RET.match(new).group("tail") or "", bv[0], kv)
            items2 = ", ".join(i if "." in i.split(" AS ")[0] and i.split(".")[0] == kv or "(" + kv in i
                               else rename_var(i, bv[0], kv) for i in split_items(RET.match(new).group("items")))
            new = head2 + items2 + tail2
    return new


def main():
    recs = [json.loads(l) for l in open(SRC, encoding="utf-8")]
    out, manifest, errors = [], [], []
    for r in recs:
        c = json.loads(json.dumps(r))  # deep copy
        rq, pq = r["ref_query"], r["pred_query"]
        problems = []
        if aliases(rq) != set(r["ref_columns"]):
            rq = correct_side(rq, r["ref_columns"]); problems.append("reference RETURN aliases != reference result columns")
        if aliases(pq) != set(r["pred_columns"]):
            pq = correct_side(pq, r["pred_columns"]); problems.append("candidate RETURN aliases != candidate result columns")
        if rq == pq:                                                # rule 5
            v = bound_vars(pq)[0]
            pq = rename_var(pq, v, RENAME.get(v, v + "2"))
            problems.append("reference and candidate query texts identical (replay by query text cannot represent the pair)")
        if problems:
            c["ref_query"], c["pred_query"] = rq, pq
            c["correction"] = {"session": 30, "problems": problems, "original_ref_query": r["ref_query"], "original_pred_query": r["pred_query"]}
            manifest.append({"case_id": r["case_id"], "dimension": r["dimension"], "expected": r["expected"],
                             "problem": "; ".join(problems), "original_ref_query": r["ref_query"], "corrected_ref_query": rq,
                             "original_pred_query": r["pred_query"], "corrected_pred_query": pq,
                             "result_values_changed": "NO", "oracle_changed": "NO",
                             "rationale": "query text rewritten so that RETURN aliases name the attached result columns (PLAN A2 rules); "
                                          "MATCH and ORDER BY/SKIP/LIMIT preserved; results and label untouched"})
        # ---- validation A2.6
        for side, q, cols in (("ref", c["ref_query"], c["ref_columns"]), ("pred", c["pred_query"], c["pred_columns"])):
            if aliases(q) != set(cols): errors.append(f"{r['case_id']} {side}: aliases {sorted(aliases(q))} != {sorted(cols)}")
        for k, orig in (("ref_query", r["ref_query"]), ("pred_query", r["pred_query"])):
            if bool(re.search(r"\bORDER BY\b", orig, re.I)) != bool(re.search(r"\bORDER BY\b", c[k], re.I)):
                errors.append(f"{r['case_id']} {k}: ORDER BY presence changed")
        if c["ref_query"] == c["pred_query"]: errors.append(f"{r['case_id']}: texts identical")
        for k in r:
            if k not in ("ref_query", "pred_query") and json.dumps(r[k], sort_keys=True) != json.dumps(c[k], sort_keys=True):
                errors.append(f"{r['case_id']}: field {k} changed")
        if not problems and json.dumps(r, sort_keys=True) != json.dumps(c, sort_keys=True):
            errors.append(f"{r['case_id']}: unaffected record changed")
        out.append(c)
    if errors:
        print("VALIDATION FAILED:\n" + "\n".join(errors)); sys.exit(1)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "s1_corrected_cases.jsonl"), "w", encoding="utf-8") as f:
        for c in out: f.write(json.dumps(c, ensure_ascii=False) + "\n")
    with open(os.path.join(OUT, "correction_manifest.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(manifest[0])); w.writeheader(); w.writerows(manifest)
    print(json.dumps({"fixtures": len(out), "corrected": len(manifest),
                      "alias_inconsistent": sum("aliases" in m["problem"] for m in manifest),
                      "identical_text_only": sum(m["problem"].startswith("reference and candidate") for m in manifest)}))


if __name__ == "__main__":
    main()
