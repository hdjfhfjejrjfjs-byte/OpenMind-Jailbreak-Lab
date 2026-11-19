"""Download a pinned, explicitly licensed corpus and emit OMJB JSONL."""
from __future__ import annotations
import hashlib
import tempfile
import time
import urllib.request
from pathlib import Path
from .corpus_io import iter_records
from .provenance import ProvenanceRecord,write_corpus
from .downloader_sources import load_source_config

def fetch_source(config_path,output_path,timeout=30,max_bytes=50_000_000):
    if timeout <= 0: raise ValueError("timeout must be positive")
    if max_bytes <= 0: raise ValueError("max_bytes must be positive")
    cfg=load_source_config(config_path)
    request=urllib.request.Request(cfg["url"],headers={"User-Agent":"OpenMind-OMJB-corpus-fetch/1.0"})
    with urllib.request.urlopen(request,timeout=timeout) as response:
        if not response.geturl().startswith("https://"): raise ValueError("download redirected away from HTTPS")
        raw=response.read(max_bytes+1)
    if len(raw)>max_bytes: raise ValueError(f"download exceeds {max_bytes} byte limit")
    actual=hashlib.sha256(raw).hexdigest()
    if actual.lower()!=cfg["sha256"].lower(): raise ValueError(f"SHA-256 mismatch: expected {cfg['sha256']}, got {actual}")
    with tempfile.TemporaryDirectory() as tmp:
        source_path=Path(tmp)/("source."+cfg["format"])
        source_path.write_bytes(raw)
        rows=[]; record_type=cfg.get("record_type","probe")
        for index,row in enumerate(iter_records(source_path)):
            if not isinstance(row,dict): raise ValueError(f"source row {index} is not an object")
            prompt=row.get(cfg["prompt_field"])
            if not isinstance(prompt,str) or not prompt.strip():
                raise ValueError(f"source row {index} has no non-empty {cfg['prompt_field']!r}")
            raw_id=row.get(cfg.get("id_field","id"))
            raw_category=row.get(cfg.get("category_field","category"))
            sample_id=str(raw_id) if raw_id is not None else f'{cfg["name"]}-{index+1:06d}'
            if not sample_id.strip(): raise ValueError(f"source row {index} has an empty id")
            category=str(raw_category) if raw_category is not None else "external"
            prov=ProvenanceRecord(source=cfg["name"],revision=cfg["revision"],upstream_uri=cfg["url"],
                fetched_at=time.time(),license=cfg["license"],author=cfg.get("author",""),
                date=cfg.get("date",""),notes=cfg.get("notes",""))
            meta={"source_row":index,"source_sha256":actual,"source_fields":sorted(row.keys())}
            if record_type=="guard":
                label_key=str(row.get(cfg["label_field"]))
                if label_key not in cfg["label_map"]:
                    raise ValueError(f"source row {index} has unmapped label {label_key!r} in {cfg['label_field']!r}")
                rows.append({"id":sample_id,"text":prompt,"label":cfg["label_map"][label_key],
                    "category":category,"meta":meta,"provenance":prov.to_dict()})
                continue
            expected=str(row.get(cfg.get("expected_field","expected"),cfg.get("default_expected","refuse")))
            if expected not in ("refuse","comply","either"):
                raise ValueError(f"source row {index} expected label must be refuse|comply|either; got {expected!r}")
            system=row.get(cfg.get("system_field","system"))
            if system is not None and not isinstance(system,str):
                raise ValueError(f"source row {index} system value must be text or null")
            rows.append({"id":sample_id,"category":category,"prompt":prompt,"expected":expected,
                "system":system,"meta":meta,"provenance":prov.to_dict()})
        if not rows: raise ValueError("source contained no records")
    manifest=write_corpus(rows,output_path,manifest_extra={"record_type":record_type,
        "upstream_sha256":actual,"upstream_url":cfg["url"],"upstream_revision":cfg["revision"],
        "license":cfg["license"]})
    return {"n":len(rows),"record_type":record_type,"output":str(output_path),"manifest":manifest}
