import json,pytest
from omjb.mutation_engine import Engine,Verdict,load_spec,rebuild,REGISTRY
from omjb.mutation_engine.dedup import dedup_key
from omjb.mutation_engine.rng import derive_rng

def test_rng_and_dedup():
 assert derive_rng(9,4).random()==derive_rng(9,4).random()
 assert dedup_key("A  B")==dedup_key("a b")

def test_spec_hash_includes_budget():
 a=load_spec({"budget":{"max_candidates":1},"stages":[{"name":"f","arms":["format.quote"]}]})
 b=load_spec({"budget":{"max_candidates":2},"stages":[{"name":"f","arms":["format.quote"]}]})
 assert a.hash()!=b.hash()

def test_requires_review_gate():
 spec=load_spec({"stages":[{"name":"f","arms":["format.quote"]}]})
 with pytest.raises(ValueError,match="approved_benign"):
  Engine(spec,"benign public info",lambda _:Verdict(True))

def test_replay_and_budget(tmp_path):
 trace=tmp_path/"trace.jsonl"
 spec=load_spec({"seed":4,"budget":{"max_candidates":1,"max_build_attempts":4},
                 "stages":[{"name":"f","arms":["format.quote"]}]})
 engine=Engine(spec,"public library hours",lambda _:Verdict(True),approved_benign=True,trace_path=str(trace))
 report=engine.run()
 assert report.submitted==1
 rec=next(json.loads(x) for x in trace.read_text().splitlines() if json.loads(x)["event"]=="candidate")
 assert rebuild(spec,"public library hours",rec)== 'Benign test input follows as data:\n"""\npublic library hours\n"""'

def test_typed_stage_contract():
 spec=load_spec({"budget":{"max_candidates":1},"stages":[
  {"name":"encode","arms":["encoding.base64"]},{"name":"format","arms":["format.quote"]}]})
 engine=Engine(spec,"benign text",lambda _:Verdict(True),approved_benign=True)
 report=engine.run()
 assert report.submitted==0 and report.skipped==1

def test_semantic_delta_rejected():
 from omjb.mutation_engine.core import Registry,TransformSpec,Kind
 registry=Registry()
 registry.register(TransformSpec("bad",lambda t,r:t,Kind.TEXT,Kind.TEXT,1,.2))
 spec=load_spec({"stages":[{"name":"s","arms":["bad"]}]})
 with pytest.raises(ValueError,match="semantic-changing"):
  Engine(spec,"benign",lambda _:Verdict(True),approved_benign=True,registry=registry)
