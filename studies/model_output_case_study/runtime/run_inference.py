"""One-pass generation on a gold-free packet. Run on free GPU only after owner gate."""
import argparse, hashlib, json, platform, re, time
from pathlib import Path

MODELS={
 'qwen':('Qwen/Qwen2.5-Coder-7B-Instruct','c03e6d358207e414f1eca0bb1891e29f1db0e242'),
 'mistral':('mistralai/Mistral-7B-Instruct-v0.3','c170c708c41dac9275d15a8fff4eca08d52bab71'),
}
def extract(s):
    t=s.strip()
    t=re.sub(r'^```(?:cypher)?\s*|\s*```$', '', t, flags=re.I).strip()
    return t if re.match(r'^(MATCH|OPTIONAL MATCH|WITH|UNWIND|CALL|RETURN)\b',t,re.I) else None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--model',choices=MODELS,required=True)
    ap.add_argument('--packet',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--smoke',action='store_true',help='technical fixture only; does not read the held-out packet')
    a=ap.parse_args()
    if a.output.exists(): raise SystemExit('Output exists; never overwrite or retry content')
    import torch, transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    torch.manual_seed(55)
    prompt_template=Path(__file__).with_name('prompt_template.txt').read_text()
    if a.smoke:
        packet=[{'question_id':'SYNTHETIC-SMOKE-1','question':'List the names of all nodes.','schema':{'node_props':{'Thing':[{'property':'name','datatype':'STRING'}]},'rel_props':{},'relationships':[]}}]
    else:
        packet=[json.loads(x) for x in a.packet.open()]
        assert all(set(r)=={'question_id','benchmark','graph','question','schema'} for r in packet)
    repo,revision=MODELS[a.model]
    tokenizer=AutoTokenizer.from_pretrained(repo,revision=revision,trust_remote_code=False)
    quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.float16,bnb_4bit_use_double_quant=True)
    model=AutoModelForCausalLM.from_pretrained(repo,revision=revision,device_map='auto',quantization_config=quant,trust_remote_code=False)
    metadata={'model':repo,'revision':revision,'prompt_sha256':hashlib.sha256(prompt_template.encode()).hexdigest(),
      'packet_sha256':None if a.smoke else hashlib.sha256(a.packet.read_bytes()).hexdigest(),
      'torch':torch.__version__,'transformers':transformers.__version__,'python':platform.python_version(),
      'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
      'temperature':0,'do_sample':False,'max_prompt_tokens':4096,'max_new_tokens':256,'seed':55,
      'quantization':'NF4 4-bit double-quant float16','smoke':a.smoke}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:
      for r in packet:
        prompt=prompt_template.format(schema=json.dumps(r['schema'],sort_keys=True),question=r['question'])
        chat=tokenizer.apply_chat_template([{'role':'user','content':prompt}],tokenize=False,add_generation_prompt=True)
        inp=tokenizer(chat,return_tensors='pt').to(model.device)
        if inp['input_ids'].shape[1]>4096:
            f.write(json.dumps({'question_id':r['question_id'],'status':'prompt_too_long','raw_response':'',
              'extracted_query':None,'error':None,'seconds':0,'metadata':metadata},ensure_ascii=False)+'\n'); f.flush(); continue
        start=time.monotonic(); status='ok'; raw=''; error=None
        try:
            with torch.inference_mode(): generated=model.generate(**inp,max_new_tokens=256,do_sample=False,pad_token_id=tokenizer.eos_token_id)
            raw=tokenizer.decode(generated[0][inp['input_ids'].shape[1]:],skip_special_tokens=True)
        except Exception as exc:
            status='generation_error'; error=f'{type(exc).__name__}: {exc}'
        query=extract(raw) if status=='ok' else None
        if status=='ok' and query is None: status='non_extractable'
        f.write(json.dumps({'question_id':r['question_id'],'status':status,'raw_response':raw,'extracted_query':query,
                            'error':error,'seconds':time.monotonic()-start,'metadata':metadata},ensure_ascii=False)+'\n')
        f.flush()
    print(json.dumps({'rows':len(packet),'output':str(a.output),'metadata':metadata},indent=2))
if __name__=='__main__':main()
