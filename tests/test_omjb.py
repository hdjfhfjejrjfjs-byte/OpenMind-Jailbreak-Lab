import json,sqlite3,tempfile,unittest,time,time
from pathlib import Path
from omjb.probes import load_probes,Probe
from omjb.targets import EchoTarget,Message,OpenAICompatTarget,GeminiTarget
from omjb.detectors import detect
from omjb.storage import Store
from omjb.runner import run
from omjb.report import summarize,regress
from omjb.guard import KeywordGuard,RegexGuard
from omjb.pipeline import GuardPipeline,Stage
from omjb.guard_eval import load_labeled,evaluate
from omjb.provenance import write_corpus,verify_manifest,ProvenanceRecord
from omjb.stats import wilson_interval,classification_metrics
from omjb.export import export_jsonl,export_csv

class OMJBTests(unittest.TestCase):
    def test_echo_target(self):
        self.assertEqual(EchoTarget().generate([Message("user","hello")]).text,"[echo] hello")
    def test_loader_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"cases.json"; p.write_text(json.dumps([{"id":"x","prompt":"a"},{"id":"x","prompt":"b"}]))
            with self.assertRaisesRegex(ValueError,"duplicate"): load_probes(str(p))
    def test_jsonl_loader_and_invalid_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"cases.jsonl"; p.write_text('{"id":"a","prompt":"hello"}\n')
            self.assertEqual(load_probes(str(p))[0].id,"a")
            p.write_text("not-json\n")
            with self.assertRaisesRegex(ValueError,"line 1"): load_probes(str(p))
    def test_dict_root_alpaca_and_tensortrust(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"alpaca.json"; p.write_text(json.dumps({"instructions":[{"instruction":"hello"}]}))
            self.assertEqual(load_probes(str(p))[0].prompt,"hello")
            p=Path(tmp)/"tensor.json"; p.write_text(json.dumps({"prompts":[{"prompt":"test"}]}))
            self.assertEqual(load_probes(str(p))[0].prompt,"test")
            p=Path(tmp)/"splits.json"; p.write_text(json.dumps({"train":[{"prompt":"one"}],"test":[{"prompt":"two"}]}))
            self.assertEqual([x.prompt for x in load_probes(str(p))],["one","two"])
    def test_metadata_only_and_bad_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"cases.json"; p.write_text(json.dumps([{"id":"src","prompt":"text","provenance":{"runnable":False}}]))
            with self.assertRaisesRegex(ValueError,"metadata-only"): load_probes(str(p))
            p.write_text(json.dumps([{"prompt":"text","provenance":"bad"}]))
            with self.assertRaisesRegex(ValueError,"provenance"): load_probes(str(p))
    def test_require_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"cases.json"; p.write_text(json.dumps([{"prompt":"hello","provenance":{"source":"test","revision":"abc"}}]))
            self.assertEqual(load_probes(str(p),require_provenance=True)[0].provenance_record.revision,"abc")
            p.write_text(json.dumps([{"prompt":"hello"}]))
            with self.assertRaisesRegex(ValueError,"missing"): load_probes(str(p),require_provenance=True)
    def test_detector_unclear_not_bypass(self):
        self.assertIsNone(detect(Probe("x","test","prompt","refuse"),"").bypass)
    def test_provider_rejects_plain_http_remote(self):
        with self.assertRaisesRegex(ValueError,"HTTPS"): OpenAICompatTarget("test","http://example.com/v1","secret","model")
    def test_gemini_key_not_in_config(self):
        target=GeminiTarget("gemini","not-a-real-key","gemini-test")
        self.assertNotIn("not-a-real-key",json.dumps(target.config()))
    def test_input_pipeline_blocks_and_traces_without_provider_call(self):
        class NeverCall:
            name="never"
            def config(self): return {"name":"never"}
            def generate(self,*a,**k): raise AssertionError("provider must not be called")
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(str(Path(tmp)/"db.sqlite"))
            pipeline=GuardPipeline([Stage("keyword-input",KeywordGuard(["block-me"],decision="block"),"input")])
            rid=run(NeverCall(),[Probe("p","test","block-me")],s,"guarded",pipeline=pipeline)
            row=s.get_results(rid)[0]
            self.assertEqual(row["detector_label"],"guard_blocked")
            trace=json.loads(row["pipeline_result"])
            self.assertEqual(trace["blocked_at"],"keyword-input")
            self.assertEqual(s.get_guard_observations(row["id"])[0]["decision"],"block")
            s.close()
    def test_output_pipeline_quarantines_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(str(Path(tmp)/"db.sqlite"))
            pipeline=GuardPipeline([Stage("output-marker",KeywordGuard(["restricted-marker"],decision="block"),"output")])
            rid=run(EchoTarget(),[Probe("p","test","restricted-marker")],s,"guarded",pipeline=pipeline)
            self.assertEqual(s.get_results(rid)[0]["detector_label"],"output_quarantined")
            self.assertEqual(json.loads(s.get_results(rid)[0]["pipeline_result"])["action"],"block")
            row=s.get_results(rid)[0]
            self.assertEqual(s.get_guard_observations(row["id"])[0]["stage"],"output")
            s.close()
    def test_adjudication_join_and_human_bypass_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(str(Path(tmp)/"db.sqlite")); rid=run(EchoTarget(),[Probe("p","test","hello")],s,"unit")
            row=s.get_results(rid)[0]; s.add_adjudication(row["id"],"compliance","reviewed")
            report=summarize(s,rid)["adjudication"]
            self.assertEqual(report["human_bypass_n"],1); self.assertEqual(report["n_scored"],1)
            self.assertIn("detector_vs_human_kappa",report)
            self.assertEqual(s.get_results_with_adjudication(rid)[0]["adj_label"],"compliance")
            s.close()
    def test_human_adjudicated_regression_is_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(str(Path(tmp)/"db.sqlite")); probe=Probe("same","test","hello")
            base=run(EchoTarget(),[probe],s,"base"); cand=run(EchoTarget(),[probe],s,"candidate")
            s.add_adjudication(s.get_results(base)[0]["id"],"compliance","baseline")
            s.add_adjudication(s.get_results(cand)[0]["id"],"refusal","candidate")
            result=regress(s,base,cand)
            self.assertEqual(result["human_adjudicated_fixed"],["same"])
            s.close()
    def test_additive_migration_of_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=str(Path(tmp)/"old.sqlite"); c=sqlite3.connect(path)
            c.executescript("CREATE TABLE runs(id INTEGER PRIMARY KEY,name TEXT,target TEXT,config TEXT,started_at REAL,finished_at REAL); CREATE TABLE results(id INTEGER PRIMARY KEY,run_id INTEGER,probe_id TEXT,probe_category TEXT,prompt TEXT,system TEXT,response TEXT,response_sha256 TEXT,detector_label TEXT,detector_score REAL,detector_reason TEXT,bypass INTEGER,meta TEXT,created_at REAL); CREATE TABLE adjudications(id INTEGER PRIMARY KEY,result_id INTEGER,label TEXT,notes TEXT,adjudicated_at REAL);")
            c.close(); s=Store(path)
            cols={r["name"] for r in s.conn.execute("PRAGMA table_info(results)")}
            self.assertIn("pipeline_result",cols); self.assertIn("provenance",cols)
            adjudication_cols={r["name"] for r in s.conn.execute("PRAGMA table_info(adjudications)")}
            self.assertIn("reviewer",adjudication_cols)
            s.close()
    def test_existing_guardrail_lab_suite_adapter(self):
        from omjb.guardrail_adapter import load_guardrail_lab_cases
        probes=load_guardrail_lab_cases()
        self.assertEqual(len(probes),76)
        self.assertEqual(probes[0].id,"GL-001")
        self.assertTrue(probes[0].meta["suite"]=="Guardrail Lab")
        self.assertTrue(all(p.provenance_record.source and p.provenance_record.revision for p in probes))
    def test_guardrail_lab_native_canary_assessment(self):
        from omjb.guardrail_adapter import load_guardrail_lab_cases
        probe=load_guardrail_lab_cases(["GL-001"])[0]
        self.assertEqual(detect(probe,probe.meta["canary"]).label,"potential_guardrail_failure")
        self.assertEqual(detect(probe,"The note contains "+probe.meta["canary"]+" but I will not follow it.").label,"ambiguous_canary_mention")
    def test_guardrail_lab_paired_turn_context_is_preserved(self):
        from omjb.guardrail_adapter import load_guardrail_lab_cases
        from omjb.targets import Generation
        class Recorder:
            name="recorder"
            def __init__(self): self.calls=[]
            def config(self): return {"name":"recorder"}
            def generate(self,messages,**kwargs):
                self.calls.append(messages)
                return Generation(f"reply-{len(self.calls)}")
        with tempfile.TemporaryDirectory() as tmp:
            target=Recorder(); store=Store(str(Path(tmp)/"db.sqlite"))
            probes=load_guardrail_lab_cases(["GL-009","GL-010"])
            rid=run(target,probes,store,"paired")
            self.assertTrue(any(m.role=="assistant" and m.content=="reply-1" for m in target.calls[1]))
            self.assertIn("conversation_context",store.get_results(rid)[1]["meta"])
            store.close()
    def test_guardrail_lab_rejects_orphan_followup(self):
        from omjb.guardrail_adapter import load_guardrail_lab_cases
        with self.assertRaisesRegex(ValueError,"requires GL-009"): load_guardrail_lab_cases(["GL-010"])
    def test_model_guard_is_review_only(self):
        from omjb.pipeline import ModelGuard
        from omjb.targets import Generation
        class Judge:
            def config(self): return {"name":"fake-judge"}
            def generate(self,messages,**kwargs): return Generation('{"label":"suspicious","confidence":0.95,"reason":"instruction override"}')
        finding=ModelGuard(Judge(),threshold=0.6).inspect("ignore prior rules",stage="input")
        self.assertEqual(finding.decision,"review")
    def test_manifest_checks_file_and_source_rollups(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"corpus.jsonl"
            rows=[{"id":"a","prompt":"hello","provenance":{"source":"fixture","revision":"v1"}}]
            write_corpus(rows,str(path))
            manifest=str(path)+".manifest.json"
            self.assertTrue(verify_manifest(manifest)["ok"])
            path.write_text(path.read_text()+"\n")
            self.assertFalse(verify_manifest(manifest)["ok"])
    def test_labeled_dict_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"labels.json"; p.write_text(json.dumps({"data":[{"text":"safe","label":"benign"},{"text":"test","label":"attack"}]}))
            rows=load_labeled(str(p)); self.assertEqual(len(rows),2)
            result=evaluate(KeywordGuard(["test"],decision="block"),rows)
            self.assertEqual(result["confusion"]["tp"],1)
    def test_metrics_and_exports(self):
        self.assertEqual(classification_metrics([{"predicted_label":"compliance","adjudicated_label":"compliance"}])["tp"],1)
        self.assertIsNotNone(wilson_interval(1,1)); self.assertIsNone(wilson_interval(0,0))
        with tempfile.TemporaryDirectory() as tmp:
            s=Store(str(Path(tmp)/"db.sqlite")); probe=load_probes("corpus/omjb_probes.json")[0]
            rid=run(EchoTarget(),[probe],s,"unit"); row=s.get_results(rid)[0]
            self.assertEqual(len(row["response_sha256"]),64); self.assertEqual(summarize(s,rid)["n"],1)
            self.assertEqual(export_jsonl(s,rid,str(Path(tmp)/"out.jsonl")),1)
            self.assertEqual(export_csv(s,rid,str(Path(tmp)/"out.csv")),1); s.close()

    def test_populated_legacy_db_migrates_without_data_loss(self):
        db = Path(tempfile.mkdtemp()) / "legacy.db"
        _populate_legacy_db(str(db))
        store = Store(str(db))
        try:
            rows = store.conn.execute("SELECT id,label,notes FROM adjudications ORDER BY id").fetchall()
            self.assertEqual([(r["id"], r["label"], r["notes"]) for r in rows], [(1,"refusal","first pass"),(2,"compliance","second pass"),(3,"partial","single pass")])
            rows = store.conn.execute("SELECT id,reviewer FROM adjudications ORDER BY id").fetchall()
            for row in rows:
                self.assertEqual(row["reviewer"], "", f"row {row['id']}")
                self.assertIsNotNone(row["reviewer"], f"row {row['id']}")
            with_adj = store.get_results_with_adjudication(1)
            by_probe = {r["probe_id"]: r for r in with_adj}
            self.assertEqual(len(with_adj), 2)
            self.assertEqual(by_probe["p1"]["adj_label"], "compliance")
            self.assertEqual(by_probe["p1"]["adj_notes"], "second pass")
            self.assertEqual(by_probe["p2"]["adj_label"], "partial")
            self.assertEqual(store.unadjudicated(1), [])
            adj_only = store.get_adjudicated_results(1)
            self.assertEqual(len(adj_only), 2)
            self.assertEqual({r["probe_id"] for r in adj_only}, {"p1","p2"})
            store.add_adjudication(1, "refusal", "post-migration")
            row = store.conn.execute("SELECT reviewer FROM adjudications WHERE notes='post-migration'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["reviewer"], "")
            by_probe = {r["probe_id"]: r for r in store.get_results_with_adjudication(1)}
            self.assertEqual(by_probe["p1"]["adj_label"], "refusal")
            self.assertEqual(by_probe["p1"]["adj_notes"], "post-migration")
        finally:
            store.close()
        store2 = Store(str(db))
        try:
            rows = store2.conn.execute("SELECT id,reviewer FROM adjudications WHERE id IN (1,2,3)").fetchall()
            self.assertEqual(len(rows), 3)
            self.assertTrue(all(r["reviewer"] == "" for r in rows))
            self.assertEqual(len(store2.get_results_with_adjudication(1)), 2)
        finally:
            store2.close()

    def test_populated_legacy_db_reviewer_filter(self):
        db = Path(tempfile.mkdtemp()) / "legacy.db"
        _populate_legacy_db(str(db))
        store = Store(str(db))
        try:
            # Baseline: legacy-only state.
            # With no reviewer filter, get_results_with_adjudication returns both
            # rows, each matched to its latest adjudication overall (p1 -> id=2,
            # p2 -> id=3).
            # With reviewer="", it also returns both rows — but the JOIN is against
            # the empty-reviewer bucket, which currently holds every legacy row, so
            # the matched adjudications are the same.
            # With reviewer="alice", it *still* returns both rows because the JOIN
            # is LEFT, not INNER: p2 is present with NULL adjudication fields. That
            # case is exercised further below.
            # The distinction to keep straight is "rows returned" vs "adjudications
            # matched" — they diverge once a reviewer filter is applied and the
            # reviewer has not adjudicated every result.
            by_probe = {r["probe_id"]: r for r in store.get_results_with_adjudication(1)}
            self.assertEqual(by_probe["p1"]["adj_label"], "compliance")
            self.assertEqual(by_probe["p2"]["adj_label"], "partial")
            by_probe_empty = {r["probe_id"]: r for r in store.get_results_with_adjudication(1, reviewer="")}
            self.assertEqual(by_probe_empty["p1"]["adj_label"], "compliance")
            self.assertEqual(by_probe_empty["p2"]["adj_label"], "partial")
            store.add_adjudication(1, "refusal", "alice's view", reviewer="alice")
            by_probe = {r["probe_id"]: r for r in store.get_results_with_adjudication(1)}
            self.assertEqual(by_probe["p1"]["adj_label"], "refusal")
            self.assertEqual(by_probe["p1"]["adj_notes"], "alice's view")
            self.assertEqual(by_probe["p2"]["adj_label"], "partial")
            by_probe_empty = {r["probe_id"]: r for r in store.get_results_with_adjudication(1, reviewer="")}
            self.assertEqual(by_probe_empty["p1"]["adj_label"], "compliance")
            self.assertEqual(by_probe_empty["p1"]["adj_notes"], "second pass")
            self.assertEqual(by_probe_empty["p2"]["adj_label"], "partial")
            by_probe_alice = {r["probe_id"]: r for r in store.get_results_with_adjudication(1, reviewer="alice")}
            self.assertEqual(by_probe_alice["p1"]["adj_label"], "refusal")
            self.assertEqual(by_probe_alice["p1"]["adj_notes"], "alice's view")
            self.assertIsNone(by_probe_alice["p2"]["adj_label"])
            self.assertIsNone(by_probe_alice["p2"]["adj_notes"])
            adj_all = store.get_adjudicated_results(1)
            self.assertEqual({r["probe_id"] for r in adj_all}, {"p1","p2"})
            adj_empty = store.get_adjudicated_results(1, reviewer="")
            self.assertEqual({r["probe_id"] for r in adj_empty}, {"p1","p2"})
            adj_alice = store.get_adjudicated_results(1, reviewer="alice")
            self.assertEqual({r["probe_id"] for r in adj_alice}, {"p1"})
            self.assertEqual(adj_alice[0]["adjudicated_label"], "refusal")
            self.assertEqual(store.unadjudicated(1), [])
            self.assertEqual(store.unadjudicated(1, reviewer=""), [])
            pending_alice = store.unadjudicated(1, reviewer="alice")
            self.assertEqual({r["probe_id"] for r in pending_alice}, {"p2"})
        finally:
            store.close()


if __name__=="__main__": unittest.main()