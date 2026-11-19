import hashlib,json
import warnings
from dataclasses import dataclass,field
from .core import Kind,REGISTRY,StageArm

@dataclass
class Stage:
    name:str
    optional:bool
    arms:list[StageArm]

@dataclass
class PipelineSpec:
    version:int
    seed:int
    stages:list[Stage]
    budget:dict
    diagnostics:list[str]=field(default_factory=list)
    def canonical(self):
        d={"version":self.version,"seed":self.seed,"budget":self.budget,"stages":[{"name":s.name,"optional":s.optional,"arms":[{"name":a.name,"params":a.params} for a in s.arms]} for s in self.stages]}
        return json.dumps(d,sort_keys=True,separators=(",",":"),ensure_ascii=False)
    def hash(self):
        return hashlib.sha256(self.canonical().encode()).hexdigest()[:24]

def validate_spec(spec:PipelineSpec,registry=REGISTRY,*,strict=False):
    """Forward dataflow over Kind values; optional stages retain their bypass path."""
    reachable={Kind.TEXT}
    diagnostics=[]
    for stage_index,stage in enumerate(spec.stages):
        compatible=[]
        for arm in stage.arms:
            transform=registry.get(arm.name)
            if transform.input_kind in reachable:
                compatible.append(arm)
            else:
                message=(f"unreachable arm {stage.name}.{arm.name}: requires "
                         f"{transform.input_kind.value}; reachable kinds are "
                         f"{sorted(kind.value for kind in reachable)}")
                diagnostics.append(message)
        if not compatible and not stage.optional:
            raise ValueError(f"stage {stage.name!r} has no reachable arms at index {stage_index}; "
                             + "; ".join(diagnostics[-len(stage.arms):]))
        next_kinds={registry.get(arm.name).output_kind for arm in compatible}
        if stage.optional:
            next_kinds.update(reachable)
        if compatible:
            reachable=next_kinds
    spec.diagnostics=diagnostics
    if strict and diagnostics:
        raise ValueError("pipeline contains unreachable arms: "+"; ".join(diagnostics))
    for message in diagnostics:
        warnings.warn(message,UserWarning,stacklevel=2)
    return diagnostics

def load_spec(d,*,registry=REGISTRY,strict_reachability=False):
    if not isinstance(d,dict) or not isinstance(d.get("stages"),list):
        raise ValueError("spec requires a stages array")
    stages=[]
    for s in d["stages"]:
        if not isinstance(s,dict) or not isinstance(s.get("arms"),list) or not s["arms"]:
            raise ValueError("each stage requires non-empty arms")
        arms=[StageArm(a,{}) if isinstance(a,str) else StageArm(a["name"],dict(a.get("params",{}))) for a in s["arms"]]
        stages.append(Stage(str(s["name"]),bool(s.get("optional",False)),arms))
    spec=PipelineSpec(int(d.get("version",1)),int(d.get("seed",0)),stages,dict(d.get("budget",{})))
    validate_spec(spec,registry,strict=strict_reachability)
    return spec
