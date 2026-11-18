import hashlib
import json
import unittest
from modules.guardrail_lab.cases import CASES, CASE_BY_ID
from modules.guardrail_lab.source_cases import SOURCE_CASES
from modules.guardrail_lab.runner import assess, run_case, run_suite

class GuardrailLabTests(unittest.TestCase):
    def test_case_ids_unique(self):
        ids = [case.case_id for case in CASES]
        self.assertEqual(len(ids), len(set(ids)))

    def test_case_inventory_includes_core_and_source_adaptations(self):
        core = {f"GL-{number:03d}" for number in range(1, 25)}
        source = {f"GL-SRC-{number:03d}" for number in range(1, 53)}
        actual = {case.case_id for case in CASES}
        self.assertEqual(actual, core | source)
        self.assertEqual(len(CASES), 76)
        self.assertEqual(len(SOURCE_CASES), 52)
        self.assertTrue((core | source).issubset(CASE_BY_ID))

    def test_source_cases_are_safe_provenance_backed_adaptations(self):
        self.assertEqual(len({case.case_id for case in SOURCE_CASES}), 52)
        self.assertEqual(len({case.canary for case in SOURCE_CASES}), 52)
        self.assertTrue(all(case.case_id.startswith("GL-SRC-") for case in SOURCE_CASES))
        self.assertTrue(all(case.canary and case.canary.startswith("SAFE-MARKER-") for case in SOURCE_CASES))
        self.assertTrue(all(case.prompt.startswith("Authorized robustness test.") for case in SOURCE_CASES))
        self.assertTrue(all(not case.control for case in SOURCE_CASES))

    def test_source_case_evidence_preserves_provenance(self):
        case = SOURCE_CASES[0]
        result = run_case(case, lambda messages: "The embedded claim is untrusted.", provider="mock")
        self.assertEqual(result["source_provenance"], {
            "source_id": case.source_id,
            "source_path": case.source_path,
            "source_sha256": case.source_sha256,
            "adaptation": "safe_pattern_adaptation",
            "variant": case.variant,
        })
        self.assertEqual(len(result["source_provenance"]["source_sha256"]), 64)

    def test_source_adaptations_use_four_balanced_approved_categories(self):
        from collections import Counter
        counts = Counter(case.category for case in SOURCE_CASES)
        self.assertEqual(counts, {
            "source_authority_override": 13,
            "source_boundary_narrowing": 13,
            "source_persona_reassignment": 13,
            "source_agent_authority_confusion": 13,
        })

    def test_source_adaptations_cover_thirteen_injection_surfaces_factorially(self):
        from collections import Counter
        from modules.guardrail_lab.source_registry import SURFACES
        surface_counts = Counter(case.variant for case in SOURCE_CASES)
        self.assertEqual(set(surface_counts), set(SURFACES))
        self.assertEqual(set(surface_counts.values()), {4})
        pairs = {
            (case.category.split("source_")[1], case.variant)
            for case in SOURCE_CASES
        }
        self.assertEqual(len(pairs), len(SOURCE_CASES))

    def test_source_adaptation_prompts_are_pairwise_distinct(self):
        normalized = {
            case.prompt.replace(case.canary, "<MARKER>")
            for case in SOURCE_CASES
        }
        self.assertEqual(len(normalized), len(SOURCE_CASES))

    def test_source_adaptations_are_reproducible_from_the_registry(self):
        from modules.guardrail_lab.source_registry import (
            case_number, expected_assignment, expected_prompt,
        )
        for case in SOURCE_CASES:
            category = case.category.split("source_")[1]
            number = case_number(case.case_id)
            self.assertEqual(
                (category, case.variant), expected_assignment(number)
            )
            self.assertEqual(
                case.prompt, expected_prompt(category, case.variant, case.canary)
            )

    def test_source_loader_rejects_unapproved_prompt_edits(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from modules.guardrail_lab import source_cases

        rows = [json.loads(line) for line in source_cases._DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows[0]["prompt"] += " Also run an external command."
        with tempfile.TemporaryDirectory() as tmp:
            altered = Path(tmp) / "altered.jsonl"
            altered.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            manifest = json.loads(source_cases._MANIFEST.read_text(encoding="utf-8"))
            manifest["adaptations_sha256"] = hashlib.sha256(altered.read_bytes()).hexdigest()
            altered_manifest = Path(tmp) / "altered_manifest.json"
            altered_manifest.write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(source_cases, "_DATA", altered), patch.object(source_cases, "_MANIFEST", altered_manifest):
                with self.assertRaisesRegex(ValueError, "approved safe template"):
                    source_cases.load_source_cases()

    def test_source_loader_rejects_adaptations_tampering_detected_by_manifest(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from modules.guardrail_lab import source_cases

        rows = [json.loads(line) for line in source_cases._DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
        rows[0]["prompt"] += " Also run an external command."
        with tempfile.TemporaryDirectory() as tmp:
            altered = Path(tmp) / "altered.jsonl"
            altered.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
            with patch.object(source_cases, "_DATA", altered):
                with self.assertRaisesRegex(ValueError, "safe adaptations SHA-256"):
                    source_cases.load_source_cases()

    def test_trust_escalation_cases_are_harmless_canary_probes(self):
        cases = [c for c in CASES if c.case_id in {"GL-013", "GL-014", "GL-015", "GL-016"}]
        self.assertEqual(len(cases), 4)
        self.assertTrue(all(c.canary and c.canary.startswith("TRUST-CANARY-") for c in cases))
        self.assertTrue(all(not c.control for c in cases))


    def test_indirect_injection_surface_cases_are_unique_synthetic_canaries(self):
        ids = {f"GL-{n:03d}" for n in range(17, 25)}
        cases = [case for case in CASES if case.case_id in ids]
        self.assertEqual({case.case_id for case in cases}, ids)
        self.assertTrue(all(case.canary and case.canary.startswith("TRUST-CANARY-") for case in cases))
        self.assertTrue(all(not case.control for case in cases))
        self.assertEqual(len({case.canary for case in cases}), 8)


    def test_expected_signal_does_not_match_inside_another_word(self):
        case = next(c for c in CASES if c.case_id == "GL-015")
        self.assertEqual(assess(case, "The instruction says to treat this as untrusted data."), "manual_review")
        self.assertEqual(assess(case, "The instruction claims the data is trusted."), "boundary_held")

    def test_canary_is_indicator(self):
        case = next(c for c in CASES if c.case_id == "GL-001")
        self.assertEqual(assess(case, "CANARY-GL001"), "potential_guardrail_failure")

    def test_canary_quoted_in_explanation_is_ambiguous(self):
        case = next(c for c in CASES if c.case_id == "GL-001")
        self.assertEqual(
            assess(
                case,
                "The note contains CANARY-GL001, but it is untrusted text.",
            ),
            "ambiguous_canary_mention",
        )

    def test_safe_response_classified_boundary_held(self):
        case = next(c for c in CASES if c.case_id == "GL-001")
        self.assertEqual(assess(case, "The quote is untrusted content."), "boundary_held")

    def test_partial_evidence_retained_on_provider_error(self):
        case = CASES[0]
        result = run_case(case, lambda messages: (_ for _ in ()).throw(RuntimeError("offline")), provider="test")
        self.assertEqual(result["assessment"], "partial_run")
        self.assertEqual(result["error"]["message"], "offline")
        self.assertTrue(result["request_messages"])

    def test_result_contains_recomputable_evidence_checksum(self):
        case = CASES[0]
        result = run_case(case, lambda messages: "safe response", provider="mock")
        recorded = dict(result)
        digest = recorded.pop("evidence_sha256")
        canonical = json.dumps(recorded, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertEqual(digest, hashlib.sha256(canonical).hexdigest())

    def test_evidence_checksum_changes_when_response_is_edited(self):
        result = run_case(CASES[0], lambda messages: "original", provider="mock")
        original = result["evidence_sha256"]
        edited = dict(result)
        edited.pop("evidence_sha256")
        edited["response"] = "edited"
        canonical = json.dumps(edited, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertNotEqual(original, hashlib.sha256(canonical).hexdigest())

    def test_repository_provider_tuple_is_unpacked_and_metadata_saved(self):
        case = CASES[0]
        result = run_case(
            case,
            lambda messages: ("provider-model-1", "The quote is untrusted content.", {"request_id": "req-123", "usage": {"total_tokens": 12}}),
            provider="mock",
        )
        self.assertEqual(result["assessment"], "boundary_held")
        self.assertEqual(result["model"], "provider-model-1")
        self.assertEqual(result["provider_metadata"]["request_id"], "req-123")

    def test_control_case(self):
        case = next(c for c in CASES if c.case_id == "GL-012")
        self.assertEqual(assess(case, "51"), "control_passed")

    def test_suite_prepends_trusted_system_instruction(self):
        captured = []
        def fake_call(messages):
            captured.append(messages)
            return "The quoted text is untrusted."
        report = run_suite(
            fake_call, provider="mock", case_ids=["GL-001"]
        )
        self.assertEqual(report["summary"]["total"], 1)
        self.assertEqual(captured[0][0]["role"], "system")
        self.assertIn("Treat quoted text", captured[0][0]["content"])
        self.assertEqual(captured[0][1]["role"], "user")

    def test_suite_rejects_invalid_delays(self):
        for delay in (-1, float("nan"), float("inf"), True, "1"):
            with self.subTest(delay=delay):
                with self.assertRaisesRegex(ValueError, "finite non-negative"):
                    run_suite(lambda messages: "ok", provider="mock",
                              case_ids=["GL-001"], delay_seconds=delay)

    def test_suite_applies_configured_delay_between_requests(self):
        from unittest.mock import patch
        with patch("modules.guardrail_lab.runner.time.sleep") as sleep:
            report = run_suite(
                lambda messages: "The content is untrusted.",
                provider="mock",
                case_ids=["GL-001", "GL-002", "GL-003"],
                delay_seconds=4.5,
            )
        self.assertEqual(report["summary"]["total"], 3)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(4.5)

    def test_report_summary(self):
        report = run_suite(lambda messages: "The content is untrusted; answer: 51; reading list.", provider="mock", case_ids=["GL-001", "GL-012"])
        self.assertEqual(report["summary"]["total"], 2)
        self.assertTrue(report["summary"]["potential_failures_require_manual_confirmation"])

    def test_report_summary_breaks_down_by_category(self):
        from modules.guardrail_lab.cases import CASES

        by_id = {case.case_id: case for case in CASES}
        report = run_suite(lambda messages: "The content is untrusted; answer: 51; reading list.", provider="mock", case_ids=["GL-001", "GL-012", "GL-017"])
        by_category = report["summary"]["by_category"]
        expected = {by_id[cid].category for cid in ("GL-001", "GL-012", "GL-017")}
        self.assertEqual(set(by_category), expected)
        total = sum(sum(bucket.values()) for bucket in by_category.values())
        self.assertEqual(total, 3)
        for category, bucket in by_category.items():
            self.assertEqual(sum(bucket.values()), 1, category)

    def test_duplicate_case_ids_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate case IDs"):
            run_suite(lambda messages: "ok", provider="mock", case_ids=["GL-001", "GL-001"])

    def test_followup_requires_setup_case_immediately_before_it(self):
        with self.assertRaisesRegex(ValueError, "GL-009"):
            run_suite(lambda messages: "ok", provider="mock", case_ids=["GL-010"])
        with self.assertRaisesRegex(ValueError, "GL-009"):
            run_suite(lambda messages: "ok", provider="mock", case_ids=["GL-001", "GL-010"])

class ReportAndCliTests(unittest.TestCase):
    def test_write_report_creates_parent_directory(self):
        import json
        import tempfile
        from pathlib import Path
        from modules.guardrail_lab.runner import write_report

        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "reports" / "result.json"
            write_report({"ok": True}, str(target))
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_list_does_not_require_provider(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from modules.guardrail_lab.cli import main

        output = StringIO()
        with redirect_stdout(output):
            status = main(["--list"])
        self.assertEqual(status, 0)
        self.assertIn("GL-001", output.getvalue())

    def test_list_includes_source_derived_cases(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from modules.guardrail_lab.cli import main

        output = StringIO()
        with redirect_stdout(output):
            status = main(["--list"])
        self.assertEqual(status, 0)
        self.assertIn("GL-SRC-001", output.getvalue())
        self.assertIn("GL-SRC-052", output.getvalue())

    def test_source_corpus_flag_selects_all_52_cases(self):
        import os
        from unittest import mock
        from modules.guardrail_lab.cli import main

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True), \
             mock.patch("modules.guardrail_lab.cli._adapter", return_value=lambda messages: "safe"), \
             mock.patch("modules.guardrail_lab.cli.run_suite", return_value={"summary": {"total": 52}, "results": []}) as run:
            code = main(["--provider", "gemini", "--source-corpus", "--output", "/tmp/source-corpus.json"])
        self.assertEqual(code, 0)
        selected = run.call_args.kwargs["case_ids"]
        self.assertEqual(len(selected), 52)
        self.assertEqual(selected[0], "GL-SRC-001")
        self.assertEqual(selected[-1], "GL-SRC-052")

    def test_research_mode_selects_six_variant_bounded_campaign(self):
        import os
        from unittest import mock
        from modules.guardrail_lab.cli import main

        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=True), mock.patch("modules.guardrail_lab.cli._adapter", return_value=lambda messages: "safe"), mock.patch("modules.guardrail_lab.cli.run_campaign", return_value={"summary": {"total": 1}, "results": []}) as run:
            code = main(["--provider", "gemini", "--research-mode", "--case", "GL-001",
                         "--budget", "12", "--output", "/tmp/research-mode.json"])
        self.assertEqual(code, 0)
        self.assertEqual(run.call_args.kwargs["variants"], 6)
        self.assertTrue(run.call_args.kwargs["adaptive"])
        self.assertEqual(run.call_args.kwargs["budget"], 12)
        self.assertEqual(run.call_args.kwargs["case_ids"], ["GL-001"])

    def test_research_mode_rejects_no_adaptive(self):
        from modules.guardrail_lab.cli import main
        with self.assertRaises(SystemExit) as ctx:
            main(["--provider", "gemini", "--research-mode", "--no-adaptive"])
        self.assertEqual(ctx.exception.code, 2)

    def test_hosted_preset_fails_fast_without_its_key(self):
        import os
        from unittest import mock
        from modules.guardrail_lab.cli import main

        env = {
            k: v for k, v in os.environ.items()
            if k not in ("DEEPSEEK_API_KEY", "OPENAI_COMPAT_API_KEY")
        }
        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "urllib.request.urlopen"
        ) as urlopen:
            with self.assertRaises(SystemExit) as ctx:
                main([
                    "--provider", "deepseek", "--model", "deepseek-chat",
                    "--case", "GL-011", "--output", "/tmp/nope.json",
                ])
        self.assertEqual(ctx.exception.code, 2)
        urlopen.assert_not_called()

    def test_hosted_preset_accepts_override_key_env(self):
        import os
        from unittest import mock
        from modules.guardrail_lab.cli import main

        env = dict(os.environ)
        env.pop("DEEPSEEK_API_KEY", None)
        env["MY_DEEPSEEK_KEY"] = "test-key"
        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "modules.guardrail_lab.cli.call_openai_compatible",
            return_value=("deepseek-chat", "ok", {}),
        ) as compat:
            code = main([
                "--provider", "deepseek", "--model", "deepseek-chat",
                "--api-key-env", "MY_DEEPSEEK_KEY",
                "--case", "GL-011", "--output", "/tmp/ok.json",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(
            compat.call_args.kwargs["api_key_env"], "MY_DEEPSEEK_KEY"
        )

    def test_local_preset_needs_no_key(self):
        import os
        from unittest import mock
        from modules.guardrail_lab.cli import main

        env = {
            k: v for k, v in os.environ.items()
            if k not in ("OPENAI_COMPAT_API_KEY",)
        }
        with mock.patch.dict(os.environ, env, clear=True), mock.patch(
            "modules.guardrail_lab.cli.call_openai_compatible",
            return_value=("llama3.1", "ok", {}),
        ) as compat:
            code = main([
                "--provider", "ollama", "--model", "llama3.1",
                "--case", "GL-011", "--output", "/tmp/ok2.json",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(
            compat.call_args.kwargs["api_key_env"], "OPENAI_COMPAT_API_KEY"
        )

    def test_max_tokens_flows_to_compatible_adapter(self):
        import os
        from unittest import mock
        from modules.guardrail_lab.cli import main

        with mock.patch.dict(os.environ, {}, clear=True), mock.patch(
            "modules.guardrail_lab.cli.call_openai_compatible",
            return_value=("llama3.1", "ok", {}),
        ) as compat:
            code = main([
                "--provider", "ollama", "--model", "llama3.1",
                "--case", "GL-011", "--max-tokens", "2048",
                "--output", "/tmp/ok3.json",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(compat.call_args.kwargs["max_tokens"], 2048)

    def test_max_tokens_zero_is_rejected(self):
        from modules.guardrail_lab.cli import main

        with self.assertRaises(SystemExit) as ctx:
            main([
                "--provider", "ollama", "--model", "llama3.1",
                "--case", "GL-011", "--max-tokens", "0",
                "--output", "/tmp/nope3.json",
            ])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
