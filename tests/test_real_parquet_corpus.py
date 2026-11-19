"""Opt-in integration tests against the immutable deepset Parquet files.

These tests download only pinned public test data at runtime. The corpus files
and prompt text are never added to the repository.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from omjb.downloaders import fetch_source
from omjb.guard_eval import load_labeled
from omjb.provenance import verify_manifest


REVISION = "4f61ecb038e9c3fb77e21034b22511b523772cdd"
BASE = f"https://huggingface.co/datasets/deepset/prompt-injections/resolve/{REVISION}/data"


@unittest.skipUnless(
    __import__("os").environ.get("OMJB_RUN_EXTERNAL_CORPUS_TESTS") == "1",
    "set OMJB_RUN_EXTERNAL_CORPUS_TESTS=1 to download pinned external test corpora",
)
class RealParquetCorpusTests(unittest.TestCase):
    def _run_split(self, split, filename, sha256, expected_n, expected_labels):
        config = {
            "name": f"deepset-prompt-injections-{split}",
            "url": f"{BASE}/{filename}",
            "sha256": sha256,
            "revision": REVISION,
            "license": "See pinned upstream dataset card; test does not assert license",
            "format": "parquet",
            "prompt_field": "text",
            "record_type": "guard",
            "label_field": "label",
            "label_map": {"0": "benign", "1": "attack"},
            "reviewed": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "source.json"
            output_path = Path(tmp) / f"{split}.jsonl"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = fetch_source(config_path, output_path, timeout=60, max_bytes=10_000_000)
            rows = load_labeled(str(output_path), require_provenance=True)
            self.assertEqual(result["n"], expected_n)
            self.assertEqual(len(rows), expected_n)
            self.assertEqual(Counter(row["label"] for row in rows), expected_labels)
            self.assertTrue(verify_manifest(str(output_path) + ".manifest.json")["ok"])
            self.assertTrue(all(row["text"].strip() for row in rows))
            self.assertTrue(all(row["provenance"]["revision"] == REVISION for row in rows))

    def test_real_train_parquet_import(self):
        self._run_split(
            "train",
            "train-00000-of-00001-9564e8b05b4757ab.parquet",
            "2e10bc7ab30f542c97e4e83e2a5683000b5057d25ec10908784c631d44124c04",
            546,
            {"benign": 343, "attack": 203},
        )

    def test_real_test_parquet_import(self):
        self._run_split(
            "test",
            "test-00000-of-00001-701d16158af87368.parquet",
            "39ac797cabc157eeed58435a08593b2952bb6cb16fc394a2d383f447cc7b246e",
            116,
            {"benign": 56, "attack": 60},
        )


if __name__ == "__main__":
    unittest.main()
