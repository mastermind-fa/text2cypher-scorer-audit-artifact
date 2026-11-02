#!/usr/bin/env python3
"""study S23 pre-specified replication criterion (s23-replication-v1). Pure functions; frozen BEFORE any execution.

Reference patterns are read from FROZEN files only:
  study S20 verdicts  studies/native_cypherturn_stress/native_equivalence_stress/frozen/20261030T143804Z_results/s20_verdicts.csv
  study S1 (S1) prior studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final/s1_results.csv  (new classes only)

Per scorer and class, a verdict list is summarised as a CATEGORY: ACCEPT (all 1), REJECT (all 0), ERROR (all
exceptions), MIXED (anything else).

Rubric for a class shared with study S20 (R1<-D1, R2<-D2, R3<-D3, R4<-D4, C0<-D6):
  NOT_TESTABLE           n_admitted < MIN_N (5)
  EXACT_REPLICATION      all 7 primary scorers have the same category as in study S20
  PARTIAL_REPLICATION    1 or 2 scorers differ, AND the class is still split (not all 7 scorers in one category) when
                         study S20 was split
  NO_REPLICATION         otherwise (>= 3 scorers differ, or a study S20 split disappears)
R8 (natural NULLs) vs study S20 D5 (appended-column fixture) is compared at MECHANISM level, as frozen from the
study S20 diagnosis: GQLBench rejects a case iff some result column holds a NULL together with numeric non-NULL values
(pandas materialisation -> NaN); the other six accept every case. A scorer "matches" iff each of its verdicts equals
that prediction; the same thresholds (0 / 1-2 / >= 3 mismatching scorers) give EXACT / PARTIAL / NO.
New classes (R5, R6, R7) have no study S20 pattern: status NEW_EVIDENCE. Secondary, they are compared with the frozen
S1 policy profile under the same thresholds: CONSISTENT_WITH_S1 / PARTIALLY_CONSISTENT_WITH_S1 / INCONSISTENT_WITH_S1.
The S1 prior for R6 uses the D06 fixtures whose prediction text has no ORDER BY (S1-030, S1-031, S1-033).

Study-level decision (pre-declared operationalisation of the A-E labels; E is reserved for integrity failure):
  T   = testable classes among the S20-shared evidence classes {R1, R2, R3, R4, R8} (C0 is calibration only)
  Rep = classes in T that are EXACT or PARTIAL; Ex = classes in T that are EXACT
  D_INSUFFICIENT_CLEAN_CASES   if |T| < 3
  A_STRONG                     if Rep == |T| and Ex >= 2 and at least one of R5/R6/R7 is testable
  C_BENCHMARK_SPECIFIC         if Rep < |T| / 2
  B_PARTIAL                    otherwise
"""
import csv, os

PRIMARY = ["cypherturn", "cypherbench", "gqlbench", "tugraph", "pipecypher", "cypherlens", "cyspider"]
MIN_N = 5
S20_MAP = {"R1_numeric_type": "D1_numeric_type", "R2_float_tolerance": "D2_float_tolerance",
           "R3_row_order": "D3_row_order", "R4_duplicates": "D4_duplicates",
           "C0_column_name_control": "D6_column_name_control"}
MECHANISM_CLASS = {"R8_null_natural": "D5_null_controlled"}
NEW_CLASSES = {"R5_column_order": ["S1-019", "S1-020", "S1-021", "S1-022", "S1-023", "S1-024"],
               "R6_reference_order": ["S1-030", "S1-031", "S1-033"],
               "R7_list_order": ["S1-098", "S1-099", "S1-100"]}
SHARED_EVIDENCE = ["R1_numeric_type", "R2_float_tolerance", "R3_row_order", "R4_duplicates", "R8_null_natural"]


def category(verdicts):
    vs = [str(v) for v in verdicts]
    if not vs: return "NONE"
    if all(v == "1" for v in vs): return "ACCEPT"
    if all(v == "0" for v in vs): return "REJECT"
    if all(v.startswith("ERROR") for v in vs): return "ERROR"
    return "MIXED"


def patterns_from_csv(path, class_col, ids=None):
    rows = list(csv.DictReader(open(path)))
    out = {}
    for r in rows:
        if ids is not None and r["case_id"] not in ids: continue
        out.setdefault(r[class_col], {s: [] for s in PRIMARY})
        for s in PRIMARY: out[r[class_col]][s].append(r[s])
    return {k: {s: category(v) for s, v in d.items()} for k, d in out.items()}


def split(cats): return len(set(cats.values())) > 1


def classify(ref_cats, new_cats, n, labels=("EXACT_REPLICATION", "PARTIAL_REPLICATION", "NO_REPLICATION")):
    if n < MIN_N: return "NOT_TESTABLE", []
    mism = [s for s in PRIMARY if new_cats[s] != ref_cats[s]]
    if not mism: return labels[0], mism
    if len(mism) <= 2 and (not split(ref_cats) or split(new_cats)): return labels[1], mism
    return labels[2], mism


def numeric_null(null_columns):
    return any(v["type"] == "numeric" for v in (null_columns or {}).values())


def classify_r8(cases, verdicts):
    """cases: [{case_id, null_columns}], verdicts: {case_id: {scorer: v}}."""
    if len(cases) < MIN_N: return "NOT_TESTABLE", [], {}
    pred = {c["case_id"]: {s: ("0" if (s == "gqlbench" and numeric_null(c["null_columns"])) else "1") for s in PRIMARY}
            for c in cases}
    mism = [s for s in PRIMARY if any(str(verdicts[c["case_id"]][s]) != pred[c["case_id"]][s] for c in cases)]
    status = "EXACT_REPLICATION" if not mism else ("PARTIAL_REPLICATION" if len(mism) <= 2 else "NO_REPLICATION")
    return status, mism, {"numeric_null_cases": sum(numeric_null(c["null_columns"]) for c in cases), "n": len(cases)}


def session_decision(status):
    T = [c for c in SHARED_EVIDENCE if status.get(c) not in (None, "NOT_TESTABLE")]
    rep = [c for c in T if status[c] in ("EXACT_REPLICATION", "PARTIAL_REPLICATION")]
    ex = [c for c in T if status[c] == "EXACT_REPLICATION"]
    new_ok = any(status.get(c) not in (None, "NOT_TESTABLE") for c in NEW_CLASSES)
    if len(T) < 3: d = "D_INSUFFICIENT_CLEAN_CASES"
    elif len(rep) == len(T) and len(ex) >= 2 and new_ok: d = "A_STRONG_CROSS_BENCHMARK_REPLICATION"
    elif len(rep) < len(T) / 2: d = "C_BENCHMARK_SPECIFIC_EFFECT"
    else: d = "B_PARTIAL_CROSS_BENCHMARK_REPLICATION"
    return d, {"testable_shared": T, "replicated": rep, "exact": ex, "new_class_testable": new_ok}
