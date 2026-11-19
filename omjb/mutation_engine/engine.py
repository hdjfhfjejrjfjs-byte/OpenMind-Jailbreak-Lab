from __future__ import annotations
import hashlib,json,time
from dataclasses import dataclass
from .budget import Budget
from .core import Candidate,Kind,REGISTRY,Registry,Verdict
from .dedup import dedup_key
from .rng import derive_rng
from .scheduler import CostAwareUCB
from . import transforms as _builtin_transforms

class Tracer:
 def __init__(self,path): self.f=open(path,"w",encoding="utf-8") if path else None
 def write(self,record):
  if self.f: self.f.write(json.dumps(record,sort_keys=True,ensure_ascii=False)+"\n"); self.f.flush()
 def close(self):
  if self.f: self.f.close(); self.f=None

@dataclass
class EngineReport:
 submitted:int; allowed:int; blocked:int; errors:int; skipped:int; by_arm:dict; allow_rate:float

class Engine:
 def __init__(self,spec,target,submit,*,approved_benign=False,registry:Registry=REGISTRY,trace_path=None,scheduler=None):
  if approved_benign is not True: raise ValueError("Engine requires explicit approved_benign=True after human review")
  if not isinstance(target,str) or not target.strip(): raise ValueError("target must be non-empty text")
  self.spec,self.target,self.submit,self.registry=spec,target,submit,registry
  self.budget=Budget.from_dict(spec.budget); self.tracer=Tracer(trace_path); self.scheduler=scheduler or CostAwareUCB()
  self._register_arms()
 def _register_arms(self):
  for stage in self.spec.stages:
   for arm in stage.arms:
    ts=self.registry.get(arm.name)
    if ts.semantic_delta!=0: raise ValueError(f"semantic-changing transform is not allowed: {arm.name}")
    self.scheduler.add(arm.key(stage.name),ts.cost)
 def _build(self,idx):
  text=self.target; kind=Kind.TEXT; rng=derive_rng(self.spec.seed,idx); used=[]
  for stage in self.spec.stages:
   choices=[a for a in stage.arms if self.registry.get(a.name).input_kind==kind]
   if not choices:
    if stage.optional: continue
    return Candidate(idx,text,used,dedup_key(text),True,"no_compatible_arm:"+stage.name)
   keys=[a.key(stage.name) for a in choices]; selected=self.scheduler.pick(keys)
   arm=next(a for a in choices if a.key(stage.name)==selected); transform=self.registry.get(arm.name)
   try: text=transform.fn(text,rng,**arm.params)
   except Exception as exc: return Candidate(idx,text,used,dedup_key(text),True,"transform_error:"+arm.name+":"+type(exc).__name__)
   kind=transform.output_kind; used.append((stage.name,arm))
  if text==self.target: return Candidate(idx,text,used,dedup_key(text),True,"identity_chain")
  return Candidate(idx,text,used,dedup_key(text))
 def run(self):
  counts={"submitted":0,"allowed":0,"blocked":0,"errors":0,"skipped":0}; seen=set(); started=time.monotonic(); idx=0
  try:
   while not self.budget.exhausted(time.monotonic()-started):
    self.budget.build_attempts+=1; candidate=self._build(idx); idx+=1
    if candidate.skipped:
     counts["skipped"]+=1; self.tracer.write({"event":"skip","idx":candidate.idx,"reason":candidate.reason,"spec_hash":self.spec.hash()}); continue
    if candidate.dedup in seen:
     counts["skipped"]+=1; self.tracer.write({"event":"skip","idx":candidate.idx,"reason":"dedup","key":candidate.dedup,"spec_hash":self.spec.hash()}); continue
    seen.add(candidate.dedup)
    try:
     verdict=self.submit(candidate.payload)
     if not isinstance(verdict,Verdict): raise TypeError("submit must return Verdict")
    except Exception as exc: verdict=Verdict(False,error=f"{type(exc).__name__}: {exc}")
    self.budget.spent_candidates+=1; self.budget.spent_usd+=max(0.0,verdict.cost_usd)
    reward=1.0 if verdict.allowed and not verdict.error else 0.0
    for key in candidate.arm_keys(): self.scheduler.update(key,reward)
    counts["submitted"]+=1
    if verdict.error: counts["errors"]+=1
    elif verdict.allowed: counts["allowed"]+=1
    else: counts["blocked"]+=1
    self.tracer.write({"event":"candidate","idx":candidate.idx,"key":candidate.dedup,
     "arms":[{"stage":s,"name":a.name,"params":a.params,"version":self.registry.get(a.name).version} for s,a in candidate.arms],
     "allowed":verdict.allowed,"latency_ms":round(verdict.latency_ms,2),"cost_usd":round(verdict.cost_usd,8),
     "error":verdict.error,"spec_hash":self.spec.hash(),"seed":self.spec.seed,
     "payload_sha256":hashlib.sha256(candidate.payload.encode()).hexdigest()})
   scored=counts["allowed"]+counts["blocked"]
   return EngineReport(counts["submitted"],counts["allowed"],counts["blocked"],counts["errors"],counts["skipped"],
                       self.scheduler.summary(),counts["allowed"]/scored if scored else 0.0)
  finally: self.tracer.close()

def rebuild(spec,target,record,registry:Registry=REGISTRY):
 rng=derive_rng(spec.seed,record["idx"]); text=target
 for arm in record["arms"]:
  transform=registry.get(arm["name"])
  if transform.version!=arm.get("version",transform.version): raise ValueError("transform version mismatch")
  text=transform.fn(text,rng,**arm["params"])
 return text
