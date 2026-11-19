import json
import unittest
from omjb.mutation_engine import Engine, Verdict, load_spec, rebuild
from omjb.mutation_engine.dedup import dedup_key
from omjb.mutation_engine.rng import derive_rng

class MutationEngineTests(unittest.TestCase):
    def test_rng_and_dedup(self):
        self.assertEqual(derive_rng(9,4).random(), derive_rng(9,4).random())
        self.assertEqual(dedup_key("A  B"), dedup_key("a b"))

    def test_spec_hash_includes_budget(self):
        a=load_spec({"budget":{"max_candidates":1},"stages":[{"name":"f","arms":["format.quote"]}]})
        b=load_spec({"budget":{"max_candidates":2},"stages":[{"name":"f","arms":["format.quote"]}]})
        self.assertNotEqual(a.hash(),b.hash())

    def test_requires_review_gate(self):
        spec=load_spec({"stages":[{"name":"f","arms":["format.quote"]}]})
        with self.assertRaisesRegex(ValueError,"approved_benign"):
            Engine(spec,"benign public info",lambda _:Verdict(True))

    def test_replay_and_budget(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            trace=Path(directory)/"trace.jsonl"
            spec=load_spec({"seed":4,"budget":{"max_candidates":1,"max_build_attempts":4},
                "stages":[{"name":"f","arms":["format.quote"]}]})
            report=Engine(spec,"public library hours",lambda _:Verdict(True),
                approved_benign=True,estimate_cost=lambda _:0.0,trace_path=str(trace)).run()
            self.assertEqual(report.submitted,1)
            rec=next(json.loads(x) for x in trace.read_text().splitlines()
                     if json.loads(x)["event"]=="candidate")
            self.assertEqual(rebuild(spec,"public library hours",rec),
                'Benign test input follows as data:\n"""\npublic library hours\n"""')

    def test_typed_stage_contract(self):
        spec=load_spec({"budget":{"max_candidates":1},"stages":[
            {"name":"encode","arms":["encoding.base64"]},
            {"name":"format","arms":["format.quote"]}]})
        report=Engine(spec,"benign text",lambda _:Verdict(True),approved_benign=True,estimate_cost=lambda _:0.0).run()
        self.assertEqual(report.submitted,0)
        self.assertEqual(report.skipped,1)

if __name__ == "__main__":
    unittest.main()
