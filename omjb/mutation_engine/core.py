from __future__ import annotations
import hashlib,json
from dataclasses import dataclass,field
from enum import Enum
from typing import Callable,Iterable
class Kind(str,Enum):
 TEXT="text"; BASE64="base64"; HEX="hex"; ROT13="rot13"
@dataclass(frozen=True)
class TransformSpec:
 name:str; fn:Callable; input_kind:Kind=Kind.TEXT; output_kind:Kind=Kind.TEXT
 cost:float=1.0; semantic_delta:float=0.0; tags:tuple[str,...]=(); version:int=1; description:str=""
class Registry:
 def __init__(self): self._specs={}
 def register(self,spec):
  if spec.name in self._specs: raise ValueError(f"duplicate transform: {spec.name}")
  if spec.cost<0 or not 0<=spec.semantic_delta<=1 or spec.version<1: raise ValueError("invalid transform metadata")
  self._specs[spec.name]=spec; return spec
 def get(self,name):
  if name not in self._specs: raise KeyError(f"unknown transform {name!r}; registered: {sorted(self._specs)}")
  return self._specs[name]
 def names(self): return sorted(self._specs)
 def __iter__(self): return iter(self._specs.values())
REGISTRY=Registry()
def transform(name,*,input_kind=Kind.TEXT,output_kind=Kind.TEXT,cost=1.0,semantic_delta=0.0,tags:Iterable[str]=(),version=1,description=""):
 def deco(fn):
  REGISTRY.register(TransformSpec(name,fn,input_kind,output_kind,cost,semantic_delta,tuple(tags),version,description)); return fn
 return deco
@dataclass
class StageArm:
 name:str; params:dict=field(default_factory=dict)
 def key(self,stage):
  raw=json.dumps(self.params,sort_keys=True,separators=(",",":"),ensure_ascii=False)
  return f"{stage}:{self.name}:{hashlib.sha256(raw.encode()).hexdigest()[:8]}"
@dataclass
class Verdict:
 allowed:bool; latency_ms:float=0.0; cost_usd:float=0.0; raw:dict|None=None; error:str|None=None
@dataclass
class Candidate:
 idx:int; payload:str; arms:list; dedup:str; skipped:bool=False; reason:str=""
 def arm_keys(self): return [a.key(s) for s,a in self.arms]

def load_extensions(group: str = "openmind_omjb.mutation_transforms") -> list[str]:
    """Load installed third-party transform modules from Python entry points."""
    from importlib.metadata import entry_points
    points = entry_points()
    selected = points.select(group=group) if hasattr(points, "select") else points.get(group, [])
    loaded = []
    for point in sorted(selected, key=lambda item: item.name):
        point.load()
        loaded.append(point.name)
    return loaded
