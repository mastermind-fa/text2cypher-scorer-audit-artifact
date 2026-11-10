"""Local-only natural-prediction adapter; never upload gold or run on Kaggle."""
from __future__ import annotations
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

from project_ex import evaluate, neo4j_executor, VERSION

ROOT = Path(__file__).resolve().parents[4]
TRACK = Path(__file__).resolve().parents[1]
RUNNER = TRACK / "kaggle/run_inference.py"
ADAPTER_ROOT = ROOT / "public_release/artifact_repository"
SCORER_RUNNER = ADAPTER_ROOT / "studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py"
ADAPTER = ADAPTER_ROOT / "studies/adapter_readiness/audit_readiness/code/audit_adapters.py"
PIN = ADAPTER_ROOT / "studies/adapter_readiness/audit_readiness/frozen/20261029T181645Z_audit_readiness/adapter_manifest.json"
INPUT_HASHES = {"runner": "8dbdb19653c84246898572b3dc79f02b0a9c8a00967a466526a5be36cb781bbf",
 "prompt": "13c431f01493eeeb52f9869257b182d0ac557c624dd5304e8fe435ba91b22f6e",
 "gate40": "836c3ba458c07dc32cad8dba3b19f9cfd3370713a0d0eea5807c71b8d867d219"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def jsonl(path):
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError("empty JSONL")
    return [json.loads(line) for line in lines]


def validate(packet_path, prediction_paths):
    if sha(RUNNER) != INPUT_HASHES["runner"] or sha(TRACK / "kaggle/prompt_template.txt") != INPUT_HASHES["prompt"]:
        raise ValueError("frozen runner/prompt drift")
    if sha(packet_path) != INPUT_HASHES["gate40"]:
        raise ValueError("packet hash drift")
    spec = importlib.util.spec_from_file_location("frozen_runner", RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    packet = jsonl(packet_path)
    ids = [x["question_id"] for x in packet]
    if len(ids) != 40 or len(set(ids)) != 40:
        raise ValueError("packet IDs")
    all_outputs = {}
    for model_key, path in prediction_paths.items():
        if model_key not in mod.MODELS:
            raise ValueError("model")
        records = jsonl(path)
        if [r.get("question_id") for r in records] != ids:
            raise ValueError("missing/duplicate/order prediction ID")
        for r in records:
            if set(r) != {"question_id", "status", "raw_response", "extracted_query", "error", "seconds", "metadata"}:
                raise ValueError("record schema")
            m = r["metadata"]
            if (m.get("model"), m.get("revision")) != mod.MODELS[model_key]:
                raise ValueError("model revision")
            if m.get("prompt_sha256") != INPUT_HASHES["prompt"] or m.get("packet_sha256") != INPUT_HASHES["gate40"] or m.get("smoke") is not False:
                raise ValueError("frozen provenance")
            if any(m.get(k) != v for k, v in {"seed":55,"do_sample":False,"temperature":0,"max_prompt_tokens":4096,"max_new_tokens":256,"quantization":"NF4 4-bit double-quant float16"}.items()):
                raise ValueError("decoding drift")
            if not isinstance(r["seconds"],(int,float)) or not math.isfinite(r["seconds"]) or r["seconds"]<0:
                raise ValueError("duration")
            status = r["status"]
            if status not in {"ok","non_extractable","prompt_too_long","generation_error"}:
                raise ValueError("prediction status")
            if status == "ok":
                if not r["extracted_query"] or r["extracted_query"] != mod.extract(r["raw_response"]) or r["error"] is not None:
                    raise ValueError("query extraction")
            elif r["extracted_query"] is not None:
                raise ValueError("failure has query")
            elif status=="non_extractable" and (r["error"] is not None or mod.extract(r["raw_response"]) is not None):
                raise ValueError("non-extractable status inconsistent")
            elif status=="prompt_too_long" and (r["raw_response"]!="" or r["error"] is not None):
                raise ValueError("prompt-too-long status inconsistent")
            elif status=="generation_error" and not r["error"]:
                raise ValueError("generation error absent")
        all_outputs[model_key] = records
    return packet, all_outputs


def reference_map(source_dir, packet):
    """Source must be pinned local MtQ manual test tree, never Kaggle input."""
    source = Path(source_dir)
    revision=subprocess.run(["git","-C",str(source),"rev-parse","HEAD"],capture_output=True,text=True)
    if revision.returncode or revision.stdout.strip()!="ec4054a1b7df7e6310efa95c56bb6e7cebc4d161":
        raise ValueError("MtQ source revision drift")
    found = {}
    for file in sorted((source / "Train_Test_Splits/Manual").glob("*/test/*.json")):
        graph = file.relative_to(source / "Train_Test_Splits/Manual").parts[0]
        for row in json.loads(file.read_text()):
            key = row["unique_id"]
            found.setdefault(key, []).append((graph, row["Cypher"], str(file), sha(file)))
    result = {}
    for row in packet:
        entries = found.get(row["question_id"], [])
        if len(entries) != 1 or entries[0][0] != row["graph"]:
            raise ValueError("reference missing/ambiguous/graph mismatch: " + row["question_id"])
        result[row["question_id"]] = entries[0]
    return result


def score_rows(packet, predictions, references, executor):
    """Returns complete trace and project-metric CSV rows; injected executor supports offline tests."""
    traces, verdicts = [], []
    for model, records in predictions.items():
        if len(records)!=len(packet) or [r["question_id"] for r in records]!=[r["question_id"] for r in packet]:
            raise ValueError("prediction IDs missing/duplicated/out of order")
        for item, pred in zip(packet, records):
            qid = item["question_id"]
            graph, gold, source_path, source_sha = references[qid]
            if pred["status"] == "ok":
                trace = evaluate(gold, pred["extracted_query"], graph, executor)
            else:
                trace = {"metric": VERSION,"graph":graph,"reference_query":gold,
                         "predicted_query":pred["extracted_query"],"reference":None,"prediction":None,
                         "status":"extract_error","verdict":0,"errors":{"prediction":pred["status"]}}
            trace.update({"question_id":qid,"model":model,"source_path":source_path,
                          "source_sha256":source_sha,"prediction_sha256":hashlib.sha256(json.dumps(pred,sort_keys=True).encode()).hexdigest()})
            traces.append(trace)
            status = "supported_scored" if trace["status"] == "scored" else trace["status"]
            verdicts.append({"benchmark":"mind_the_query","question_id":qid,"model":model,
                             "scorer":"s55_project_ex_official","verdict":"" if trace["verdict"] is None else str(trace["verdict"]),
                             "status":status,"origin":"natural_model_prediction"})
    return traces, verdicts


def run_released_scorer(scorer, traces, work, artifact_root=ADAPTER_ROOT):
    """Invoke unchanged hash-verified released adapter; only completed native result pairs."""
    if scorer not in {"cypherturn","cypherbench","gqlbench","tugraph","pipecypher","cyspider","neo4jlabs","pc_v1_1"}:
        raise ValueError("unapproved scorer")
    artifact_root=Path(artifact_root)
    adapter=artifact_root/"studies/adapter_readiness/audit_readiness/code/audit_adapters.py"
    pin_file=artifact_root/"studies/adapter_readiness/audit_readiness/frozen/20261029T181645Z_audit_readiness/adapter_manifest.json"
    scorer_runner=artifact_root/"studies/corpus_audit/audit_analysis/code/run_experiment_v1_1.py"
    pin=json.loads(pin_file.read_text())["code_sha256"]["audit_adapters.py"]
    if sha(adapter)!=pin or sha(adapter)!=sha(ADAPTER):
        raise ValueError("released scorer adapter hash drift")
    dirs={"cypherturn":"cypherturn","cypherbench":"cypherbench","gqlbench":"gqlbench","tugraph":"tugraph_driver",
          "pipecypher":"pipecypher","cyspider":"cyspider","neo4jlabs":"neo4jlabs_text2cypher"}
    if scorer in dirs:
        pins=json.loads((artifact_root/"external/EXTERNAL_PINS.json").read_text())["repos"]
        source=next(x for x in pins if x["local_dir"]==dirs[scorer])
        target=artifact_root/"external"/dirs[scorer]
        if sha(target/source["scorer_file"])!=source["scorer_sha256"]:
            raise ValueError("third-party scorer source hash drift")
        rev=subprocess.run(["git","-C",str(target),"rev-parse","HEAD"],capture_output=True,text=True)
        if rev.returncode or rev.stdout.strip()!=source["commit"]:
            raise ValueError("third-party scorer commit drift")
    def json_domain(v):
        if v is None or isinstance(v,(str,bool,int)):
            return True
        if isinstance(v,float):
            import math
            return math.isfinite(v)
        if isinstance(v,(list,tuple)):
            return all(json_domain(x) for x in v)
        if isinstance(v,dict):
            return all(isinstance(k,str) and json_domain(x) for k,x in v.items())
        return False
    pairs=[];unsupported=[]
    for t in traces:
        if t["status"] == "scored":
            key=t["model"]+"|"+t["question_id"]
            if not json_domain(t["reference"]["rows"]) or not json_domain(t["prediction"]["rows"]):
                unsupported.append({"case_id":key,"verdict":"UNSUPPORTED"})
            else:
                pairs.append({"case_id":key,
                              "reference":{"query":t["reference_query"],**t["reference"]},
                              "prediction":{"query":t["predicted_query"],**t["prediction"]}})
    work=Path(work)
    work.mkdir(parents=True, exist_ok=False)
    inp,out=work/"pairs.jsonl",work/"verdicts.jsonl"
    inp.write_text("".join(json.dumps(p,ensure_ascii=False,allow_nan=False)+"\n" for p in pairs))
    if not pairs:
        out.write_text("")
        return unsupported
    proc=subprocess.run([sys.executable,str(scorer_runner),scorer,"s3",str(inp),str(out)],capture_output=True,text=True,timeout=120*len(pairs)+60)
    (work/"runner_stdout.log").write_text(proc.stdout)
    (work/"runner_stderr.log").write_text(proc.stderr)
    if proc.returncode:
        raise RuntimeError("released scorer runner failed; logs preserved")
    return jsonl(out)+unsupported


def analysis_rows(traces, project_rows, scorer_outputs):
    """Create scorer_impact.py's exact CSV schema without dropping failures."""
    rows=list(project_rows)
    for scorer, outputs in scorer_outputs.items():
        by_case={r["case_id"]:r for r in outputs}
        if len(by_case)!=len(outputs):
            raise ValueError("duplicate released scorer case")
        for t in traces:
            key=t["model"]+"|"+t["question_id"]
            if t["status"] != "scored":
                status = t["status"]
                verdict = ""
            elif key not in by_case:
                status,verdict="scorer_error",""
            else:
                native=by_case[key]["verdict"]
                status,verdict=("supported_scored",str(native)) if native in (0,1) else (("unsupported" if native=="UNSUPPORTED" else "scorer_error"),"")
            rows.append({"benchmark":"mind_the_query","question_id":t["question_id"],
                         "model":t["model"],"scorer":scorer,"verdict":verdict,
                         "status":status,"origin":"natural_model_prediction"})
    return rows


def write_outputs(traces, rows, output_dir):
    out=Path(output_dir)
    out.mkdir(parents=True,exist_ok=False)
    def serial(v):
        from datetime import date,datetime,time
        from decimal import Decimal
        if isinstance(v,(date,datetime,time,Decimal)):
            return {"type":type(v).__name__,"value":str(v)}
        # Unsupported Neo4j objects are explicitly marked; never coerce them
        # into a misleading scalar/string or feed them to released scorers.
        return {"unsupported_native_type":type(v).__module__+"."+type(v).__name__}
    (out/"execution_traces.jsonl").write_text("".join(json.dumps(t,default=serial,ensure_ascii=False)+"\n" for t in traces))
    with (out/"scorer_verdicts.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=["benchmark","question_id","model","scorer","verdict","status","origin"])
        writer.writeheader(); writer.writerows(rows)
    (out/"SHA256SUMS").write_text("".join(f"{sha(out/name)}  {name}\n" for name in ("execution_traces.jsonl","scorer_verdicts.csv")))


def main():
    import argparse
    import os
    import tempfile
    ap=argparse.ArgumentParser(description="LOCAL ONLY. Requires owner-approved project metric and a read-only Neo4j account.")
    ap.add_argument("--packet",type=Path,required=True)
    ap.add_argument("--qwen",type=Path,required=True)
    ap.add_argument("--mistral",type=Path,required=True)
    ap.add_argument("--mtq-source",type=Path,required=True)
    ap.add_argument("--database-map",type=Path,required=True,help="JSON graph ID to isolated read-only database name")
    ap.add_argument("--uri",required=True)
    ap.add_argument("--output-dir",type=Path,required=True)
    ap.add_argument("--scorer",action="append",default=[])
    ap.add_argument("--artifact-root",type=Path,default=ADAPTER_ROOT,help="Released artifact copy with pinned external scorer checkouts")
    a=ap.parse_args()
    if a.output_dir.exists():raise SystemExit("output exists; preserve prior evidence")
    packet,predictions=validate(a.packet,{"qwen":a.qwen,"mistral":a.mistral})
    references=reference_map(a.mtq_source,packet)
    if not (a.mtq_source/".git").exists() and not (a.mtq_source/"ReadMe.md").exists():
        raise SystemExit("unrecognized MtQ source")
    databases=json.loads(a.database_map.read_text())
    if set(databases)!=set(r["graph"] for r in packet):raise SystemExit("database map does not match packet graphs")
    user=os.environ.get("S55_NEO4J_READONLY_USER")
    password=os.environ.get("S55_NEO4J_READONLY_PASSWORD")
    if not user or not password:raise SystemExit("read-only Neo4j credentials must be supplied outside repository")
    from neo4j import GraphDatabase
    driver=GraphDatabase.driver(a.uri,auth=(user,password))
    try:
        traces,project=score_rows(packet,predictions,references,neo4j_executor(driver,databases))
    finally:
        driver.close()
    scorer_outputs={}
    for name in a.scorer:
        scorer_outputs[name]=run_released_scorer(name,traces,a.output_dir.with_name(a.output_dir.name+"_scorer_"+name),a.artifact_root)
    rows=analysis_rows(traces,project,scorer_outputs)
    write_outputs(traces,rows,a.output_dir)
    manifest={"metric":VERSION,"packet_sha256":sha(a.packet),"qwen_sha256":sha(a.qwen),
              "mistral_sha256":sha(a.mistral),"source_commit":"ec4054a1b7df7e6310efa95c56bb6e7cebc4d161",
              "database_map":databases,"scorers":a.scorer,"rows":len(rows),
              "runner_sha256":sha(RUNNER),"adapter_sha256":sha(ADAPTER)}
    (a.output_dir/"execution_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({"status":"completed","rows":len(rows),"output":str(a.output_dir)}))


if __name__=="__main__":main()
