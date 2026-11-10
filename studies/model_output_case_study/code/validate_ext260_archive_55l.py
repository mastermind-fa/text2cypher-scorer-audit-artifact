"""S55L independent validation of the returned ext260 archive (separate code path from the notebook validator). Reads only."""
import hashlib, json, re, sys, zipfile
from collections import Counter
from pathlib import Path
T = Path(sys.argv[1]); Z = Path(sys.argv[2]); out = Path(sys.argv[3])
sha = lambda b: hashlib.sha256(b).hexdigest()
chk = {}; ok = lambda n, c, d=None: chk.__setitem__(n, {"pass": bool(c), "detail": d})
man55k = json.loads((T / "gate40_final_package_55k/FROZEN_INFERENCE_MANIFEST_55K.json").read_text())
z = zipfile.ZipFile(Z); names = z.namelist(); R = {n: z.read(n) for n in names}
ok("crc", z.testzip() is None)
sums = dict(l.split("  ", 1)[::-1] for l in R["SHA256SUMS"].decode().splitlines())
ok("sha256sums_cover_all_other_members", set(sums) == set(names) - {"SHA256SUMS"}, sorted(set(names) ^ set(sums) ^ {"SHA256SUMS"}))
ok("member_hashes", all(sha(R[n]) == h for n, h in sums.items()))
em = json.loads(R["execution_manifest.json"]); ok("manifest_phase_complete", em.get("phase") == "ext260" and em.get("complete") is True and em.get("errors") == [], {k: em.get(k) for k in ("phase", "complete", "errors", "timestamp_utc")})
env = json.loads(R["environment.json"]); ok("runtime_equals_lock", all(env.get(k) == v for k, v in man55k["runtime_lock"].items()) and env.get("nf4_cuda_test") == "PASS", env)
ih = json.loads(R["input_hashes.json"])
fh = ih["file_sha256"]; frozen = man55k["file_sha256"]
ok("input_files_equal_frozen_manifest", all(fh[k] == frozen[k] for k in fh if k in frozen) and len(fh) == 6, {k: fh[k] == frozen.get(k) for k in fh})
packet = [json.loads(l) for l in (T / "data/packet_mtq_remaining260.jsonl").read_text().splitlines()]; ids = [r["question_id"] for r in packet]
ok("ext_ids_in_manifest_equal_packet", ih.get("ext_ids") == ids)
g40 = {json.loads(l)["question_id"] for l in (T / "data/packet_mtq_gate40.jsonl").read_text().splitlines()}
nb = json.loads((T / "kaggle/session55_ext260_frozen_v1.ipynb").read_text())
src = R["notebook_executed_source.py"].decode()
cells = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]
ok("executed_source_equals_frozen_cells", all(c.strip() in src for c in cells[1:]) and cells[0].strip()[:200] in src, [i for i, c in enumerate(cells) if c.strip() not in src])
runner_src = (T / "kaggle/run_inference.py").read_text(); ns = {}; exec(compile(runner_src.split("def main")[0], "runner", "exec"), ns)
MODELS = {"qwen": ("Qwen/Qwen2.5-Coder-7B-Instruct", "c03e6d358207e414f1eca0bb1891e29f1db0e242"), "mistral": ("mistralai/Mistral-7B-Instruct-v0.3", "c170c708c41dac9275d15a8fff4eca08d52bab71")}
stats = {}
for m in ("qwen", "mistral"):
    rows = [json.loads(l) for l in R["s55_%s_mtq_ext260.jsonl" % m].decode().splitlines()]
    q = [r["question_id"] for r in rows]
    ok("%s_260_ids_exact_order" % m, q == ids and len(set(q)) == 260)
    ok("%s_no_gate40_overlap" % m, not (set(q) & g40))
    md = [r["metadata"] for r in rows]
    ok("%s_identity" % m, all((x["model"], x["revision"]) == MODELS[m] for x in md), {"|".join(k): v for k, v in Counter((x["model"], x["revision"]) for x in md).items()})
    ok("%s_prompt_packet_hash" % m, all(x["prompt_sha256"] == frozen["kaggle/prompt_template.txt"] and x["packet_sha256"] == frozen["data/packet_mtq_remaining260.jsonl"] for x in md))
    ok("%s_decoding" % m, all(x["seed"] == 55 and x["do_sample"] is False and x["temperature"] == 0 and x["max_new_tokens"] == 256 and x["max_prompt_tokens"] == 4096 and x["quantization"] == "NF4 4-bit double-quant float16" and x["smoke"] is False for x in md))
    ok("%s_runtime_per_row" % m, all(x["python"] == env["python"] and x["torch"] == env["torch"] and x["transformers"] == env["transformers"] and x["gpu"] == "Tesla T4" for x in md))
    st = Counter(r["status"] for r in rows)
    ok("%s_extraction_consistent" % m, all((r["status"] == "ok" and r["extracted_query"] == ns["extract"](r["raw_response"]) and r["extracted_query"]) or (r["status"] != "ok" and r["extracted_query"] is None) for r in rows))
    ok("%s_schema" % m, all(set(r) == {"question_id", "status", "raw_response", "extracted_query", "error", "seconds", "metadata"} for r in rows))
    trunc = sum(1 for r in rows if r["status"] == "ok" and not re.search(r"\bRETURN\b", r["extracted_query"] or "", re.I))
    stats[m] = {"status_counts": dict(st), "empty_raw": sum(1 for r in rows if not r["raw_response"].strip()), "ok_without_RETURN": trunc,
                "seconds_total": round(sum(r["seconds"] for r in rows), 1), "sha256": sums["s55_%s_mtq_ext260.jsonl" % m],
                "notebook_validation": (em.get("results", {}).get(m, {}) or {}).get("validation")}
    ok("%s_notebook_validator_agrees" % m, stats[m]["notebook_validation"] and stats[m]["notebook_validation"]["count"] == 260 and stats[m]["notebook_validation"]["status_counts"] == dict(st))
res = {"archive": str(Z), "archive_sha256": sha(Z.read_bytes()), "all_pass": all(c["pass"] for c in chk.values()), "checks": chk, "models": stats,
       "gpu": env.get("gpu_names"), "executed_utc": em.get("timestamp_utc")}
out.mkdir(parents=True, exist_ok=False); (out / "ext260_archive_validation.json").write_text(json.dumps(res, indent=1, default=str))
print(res["all_pass"], [k for k, c in chk.items() if not c["pass"]]); print(json.dumps(stats, indent=1)[:1500]); print(res["gpu"], res["executed_utc"])
