"""Configuration validation for explicitly pinned, licensed corpus sources."""
from __future__ import annotations
import json
from pathlib import Path

REQUIRED=("name","url","sha256","revision","license","format","prompt_field")
FORMATS=("json","jsonl","ndjson","yaml","yml","csv","parquet")
def load_source_config(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data,dict): raise ValueError("source config must be a JSON object")
    missing=[key for key in REQUIRED if not isinstance(data.get(key),str) or not data[key].strip()]
    if missing: raise ValueError("source config missing non-empty fields: "+", ".join(missing))
    if data.get("reviewed") is not True: raise ValueError("set reviewed: true only after manually confirming this is a safe, authorized test corpus")
    if not data["url"].startswith("https://"): raise ValueError("source URL must use HTTPS")
    if len(data["sha256"])!=64 or any(c not in "0123456789abcdefABCDEF" for c in data["sha256"]):
        raise ValueError("sha256 must be 64 hexadecimal characters")
    if data["format"] not in FORMATS: raise ValueError("format must be json, jsonl, ndjson, yaml, yml, csv, or parquet")
    record_type=data.get("record_type","probe")
    if record_type not in ("probe","guard"): raise ValueError("record_type must be probe or guard")
    if record_type=="guard":
        if not isinstance(data.get("label_field"),str) or not data["label_field"].strip():
            raise ValueError("guard sources require a non-empty label_field")
        label_map=data.get("label_map")
        if not isinstance(label_map,dict) or not label_map:
            raise ValueError("guard sources require a label_map object")
        if any(not isinstance(k,str) or v not in ("benign","attack") for k,v in label_map.items()):
            raise ValueError("label_map keys must be strings and values must be benign|attack")
    for key in ("prompt_field","id_field","category_field","expected_field","system_field","label_field"):
        if key in data and (not isinstance(data[key],str) or not data[key].strip()):
            raise ValueError(f"{key} must be a non-empty string")
    return data
