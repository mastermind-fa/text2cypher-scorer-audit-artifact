"""Independent S15 recomputation from frozen raw verdicts (does NOT import audit_analysis)."""
import json, math, itertools, collections, csv, sys
from statistics import NormalDist
F='studies/corpus_audit/audit_final/frozen/20261029T190431Z_audit_final'
P7=["cypherturn","cypherbench","gqlbench","tugraph","pipecypher","cypherlens","cyspider"]; SEC=["neo4jlabs","pc_v1_1"]
def load(st):
    v=collections.defaultdict(dict)
    for s in P7+SEC:
        for l in open(f'{F}/raw/{st}/{s}.jsonl'):
            r=json.loads(l); v[r['case_id']][s]=r['verdict']
    return v
b=lambda x: x in (0,1) and not isinstance(x,str)
def wil_lo(k,n,z):
    p=k/n; d=1+z*z/n; c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d; return max(0,c-h)
z=NormalDist().inv_cdf(1-0.05/21)
out={}
S1=[json.loads(l) for l in open('studies/controlled_suite/audit/s1/s1_cases.jsonl')]
out['s1']={'cases':len(S1),'oracle':sum(c['expected']!='INTENT_DEPENDENT' for c in S1),'intent':sum(c['expected']=='INTENT_DEPENDENT' for c in S1),
 'dim_groups':len({c['dimension'].split('_')[0] for c in S1}),'sub_dims':len({c['dimension'] for c in S1})}
v1=load('s1'); agree={}
for s in P7+SEC:
    c=n=0
    for x in S1:
        if x['expected']=='INTENT_DEPENDENT': continue
        n+=1; v=v1[x['case_id']][s]; c+= b(v) and int(v)==(1 if x['expected']=='EQUIV' else 0)
    agree[s]=(c,n,round(c/n,4))
out['s1_agree']=agree
same=[x['case_id'] for x in S1 if x['ref_query']==x['pred_query']]
out['s1_identical_query_cases']={c:(next(x['dimension'] for x in S1 if x['case_id']==c), sorted(s for s in P7+SEC if str(v1[c][s]).startswith('ERROR:AdapterInputConflict'))) for c in same}
v3=load('s3'); out['s3_n']=len(v3)
un=sum(len({int(v[s]) for s in P7})==1 for v in v3.values()); out['s3_unanimous']=un; out['s3_nonunanimous']=len(v3)-un
pw=[]
for a,c in itertools.combinations(P7,2):
    k=sum(int(v[a])!=int(v[c]) for v in v3.values()); n=len(v3); pw.append((a,c,k,n,round(k/n,4),round(wil_lo(k,n,z),4)))
out['pairs_meeting']=sum(p[5]>=0.02 for p in pw); out['max']=max(pw,key=lambda p:p[4])
six=[p for p in pw if 'cypherlens' not in p]; out['six_meeting']=sum(p[5]>=0.02 for p in six); out['six_max']=max(six,key=lambda p:p[4])
S6=[s for s in P7 if s!='cypherlens']
d6=sum(len({int(v[s]) for s in S6})>1 for v in v3.values()); out['six_scorer_nonunanimous']=(d6,len(v3),round(d6/len(v3),4))
out['s3_pass']={s:sum(1 for v in v3.values() if b(v[s]) and int(v[s])==1) for s in P7+SEC}
out['s3_errors']={s:[v[s] for v in v3.values() if not b(v[s])] for s in P7+SEC if any(not b(v[s]) for v in v3.values())}
cl_only=[c for c,v in v3.items() if int(v['cypherlens'])==0 and all(int(v[s])==1 for s in S6)]; out['s3_cypherlens_only_fail']=len(cl_only)
v2=load('s2'); P2={json.loads(l)['case_id']:json.loads(l) for l in open(F+'/pairs/s2_pairs.jsonl')}
out['s2_n']=len(v2); out['s2_empty_pred']=sum(1 for p in P2.values() if not p['prediction']['rows'])
comp={c:v for c,v in v2.items() if all(b(v[s]) for s in P7)}
out['s2_complete']=len(comp); out['s2_unan_fail']=sum(all(int(v[s])==0 for s in P7) for v in comp.values()); out['s2_unan_pass']=sum(all(int(v[s])==1 for s in P7) for v in comp.values())
out['s2_nonunan']=sum(len({int(v[s]) for s in P7})>1 for v in comp.values())
out['s2_incomplete_units']=[(c,{s:v[s] for s in P7 if not b(v[s])}) for c,v in v2.items() if c not in comp]
solo=[c for c,v in v2.items() if v['cypherlens']==1 and all(b(v[s]) and int(v[s])==0 for s in S6)]
solo_any=[c for c,v in v2.items() if v['cypherlens']==1 and not any(b(v[s]) and int(v[s])==1 for s in S6)]
lab={r['unit_id']:r['final_semantic_label'] for r in csv.DictReader(open('studies/reference_comparator/pass2_work/frozen/20261028T163230Z_pass2/c3_unblinded_semantic_table.csv'))}
out['s2_cl_pass']=sum(1 for v in v2.values() if v['cypherlens']==1)
out['s2_cl_solo_strict']=len(solo); out['s2_cl_solo_noother_pass']=len(solo_any)
out['s2_cl_solo_empty']=sum(1 for c in solo_any if not P2[c]['prediction']['rows'])
out['s2_cl_solo_labels']=dict(collections.Counter(lab.get(c[3:],'NOT_IN_C3_SAMPLE') for c in solo_any))
out['s2_pass']={s:sum(1 for v in v2.values() if b(v[s]) and int(v[s])==1) for s in P7+SEC}
to=[c for c,v in v3.items() if v['neo4jlabs']=='ERROR:CaseTimeout']; P3={json.loads(l)['case_id']:json.loads(l) for l in open(F+'/pairs/s3_pairs.jsonl')}
out['timeout_units']=[(c,len(P3[c]['reference']['rows']),len(P3[c]['prediction']['rows'])) for c in to]
am=json.load(open(F+'/ANALYSIS_FREEZE_AMENDMENT_1.json')); lg=json.load(open(F+'/raw/run_log.json'))
out['amendment_before_resume']=(am['created_utc'], lg['started_utc'], am['created_utc']<lg['started_utc'])
st=json.load(open(F+'/audit_statistics.json'))
fz={(r['scorer_a'],r['scorer_b']):(r['disagreements'],round(r['rate'],4),round(r['lower_bonf_one_sided'],4)) for r in st['s3']['pairwise']}
out['pairwise_match_frozen']=all(fz[(p[0],p[1])]==(p[2],p[4],p[5]) for p in pw)
out['pairwise']=[(p[0],p[1],p[2],p[4],p[5]) for p in sorted(pw,key=lambda p:-p[4])]
print(json.dumps(out,indent=1,default=str))
