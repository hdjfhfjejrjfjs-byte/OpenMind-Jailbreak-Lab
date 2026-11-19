import hashlib,json
from dataclasses import dataclass
from .core import StageArm
@dataclass
class Stage:
 name:str; optional:bool; arms:list[StageArm]
@dataclass
class PipelineSpec:
 version:int; seed:int; stages:list[Stage]; budget:dict
 def canonical(self):
  d={"version":self.version,"seed":self.seed,"budget":self.budget,"stages":[{"name":s.name,"optional":s.optional,"arms":[{"name":a.name,"params":a.params} for a in s.arms]} for s in self.stages]}
  return json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=False)
 def hash(self): return hashlib.sha256(self.canonical().encode()).hexdigest()[:24]
def load_spec(d):
 if not isinstance(d,dict) or not isinstance(d.get("stages"),list): raise ValueError("spec requires a stages array")
 stages=[]
 for s in d["stages"]:
  if not isinstance(s,dict) or not isinstance(s.get("arms"),list) or not s["arms"]: raise ValueError("each stage requires non-empty arms")
  arms=[StageArm(a,{}) if isinstance(a,str) else StageArm(a["name"],dict(a.get("params",{}))) for a in s["arms"]]
  stages.append(Stage(str(s["name"]),bool(s.get("optional",False)),arms))
 return PipelineSpec(int(d.get("version",1)),int(d.get("seed",0)),stages,dict(d.get("budget",{})))