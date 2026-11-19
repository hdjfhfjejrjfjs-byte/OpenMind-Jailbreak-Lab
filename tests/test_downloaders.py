import hashlib,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from omjb.downloaders import fetch_source
from omjb.probes import load_probes
from omjb.guard_eval import load_labeled
from omjb.provenance import verify_manifest

class FakeResponse(io.BytesIO):
    def __init__(self,payload,url): super().__init__(payload); self.url=url
    def __enter__(self): return self
    def __exit__(self,*args): self.close()
    def geturl(self): return self.url

class DownloaderTests(unittest.TestCase):
    def _config(self,tmp,payload,**extra):
        config=Path(tmp)/"source.json"
        values={"name":"fixture","url":"https://example.test/data.json","sha256":hashlib.sha256(payload).hexdigest(),
            "revision":"v1.2.3","license":"CC0-1.0","format":"json","prompt_field":"prompt","reviewed":True}
        values.update(extra); config.write_text(json.dumps(values)); return config

    def test_pinned_download_emits_loadable_provenance_corpus(self):
        payload=json.dumps([{"id":"fixture-1","prompt":"safe evaluation prompt","expected":"either","category":"fixture"}]).encode()
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload); output=Path(tmp)/"probes.jsonl"
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.json")):
                result=fetch_source(config,output)
            probes=load_probes(str(output),require_provenance=True)
            self.assertEqual(result["n"],1); self.assertEqual(probes[0].id,"fixture-1")
            self.assertEqual(probes[0].expected,"either"); self.assertEqual(probes[0].provenance_record.revision,"v1.2.3")
            self.assertTrue(verify_manifest(str(output)+".manifest.json")["ok"])

    def test_csv_probe_import_preserves_quoted_fields(self):
        payload=b'id,goal,target\ncase-1,"A quoted, inert evaluation prompt","target text"\n'
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload,format="csv",prompt_field="goal",id_field="id")
            output=Path(tmp)/"probes.jsonl"
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.csv")):
                result=fetch_source(config,output)
            probe=load_probes(str(output),require_provenance=True)[0]
            self.assertEqual(result["record_type"],"probe")
            self.assertEqual(probe.prompt,"A quoted, inert evaluation prompt")
            self.assertEqual(probe.expected,"refuse")
            self.assertTrue(verify_manifest(str(output)+".manifest.json")["ok"])

    def test_csv_guard_import_maps_labels_separately(self):
        payload=b'text,label,source\n"benign sample, quoted",0,fixture\nattack sample,1,fixture\n'
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload,format="csv",prompt_field="text",record_type="guard",
                label_field="label",label_map={"0":"benign","1":"attack"},category_field="source")
            output=Path(tmp)/"guard.jsonl"
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.csv")):
                result=fetch_source(config,output)
            rows=load_labeled(str(output),require_provenance=True)
            self.assertEqual(result["record_type"],"guard")
            self.assertEqual([r["label"] for r in rows],["benign","attack"])
            self.assertEqual(rows[0]["text"],"benign sample, quoted")
            self.assertTrue(verify_manifest(str(output)+".manifest.json")["ok"])

    def test_parquet_guard_import(self):
        try: import pyarrow as pa; import pyarrow.parquet as pq
        except ImportError: self.skipTest("install openmind-omjb[parquet] to run Parquet integration test")
        sink=pa.BufferOutputStream()
        pq.write_table(pa.table({"text":["benign sample","attack sample"],"label":[0,1]}),sink)
        payload=sink.getvalue().to_pybytes()
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload,format="parquet",prompt_field="text",record_type="guard",
                label_field="label",label_map={"0":"benign","1":"attack"})
            output=Path(tmp)/"guard.jsonl"
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.parquet")):
                result=fetch_source(config,output)
            rows=load_labeled(str(output),require_provenance=True)
            self.assertEqual(result["n"],2); self.assertEqual([r["label"] for r in rows],["benign","attack"])

    def test_hash_mismatch_rejected_before_output(self):
        payload=b'[{"prompt":"safe"}]'
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload,sha256="0"*64); output=Path(tmp)/"probes.jsonl"
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.json")):
                with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"): fetch_source(config,output)
            self.assertFalse(output.exists())

    def test_requires_human_reviewed_source_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload=b'[{"prompt":"safe"}]'; config=self._config(tmp,payload,reviewed=False)
            with self.assertRaisesRegex(ValueError,"reviewed: true"): fetch_source(config,Path(tmp)/"out.jsonl")

    def test_rejects_non_text_system_prompt(self):
        payload=json.dumps([{"prompt":"safe","system":123}]).encode()
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload)
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.json")):
                with self.assertRaisesRegex(ValueError,"system value must be text"): fetch_source(config,Path(tmp)/"out.jsonl")

    def test_guard_source_rejects_unmapped_labels(self):
        payload=b'text,label\nsample,2\n'
        with tempfile.TemporaryDirectory() as tmp:
            config=self._config(tmp,payload,format="csv",prompt_field="text",record_type="guard",
                label_field="label",label_map={"0":"benign","1":"attack"})
            with patch("omjb.downloaders.urllib.request.urlopen",return_value=FakeResponse(payload,"https://example.test/data.csv")):
                with self.assertRaisesRegex(ValueError,"unmapped label"): fetch_source(config,Path(tmp)/"out.jsonl")

if __name__=="__main__": unittest.main()
