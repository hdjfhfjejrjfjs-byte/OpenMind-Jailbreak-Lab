import asyncio
import unittest

from omjb.async_harness import parse_decision
from omjb.providers import CostTable, QuotaTracker, ProviderRegistry, Completion
from omjb.provider_eval import ProviderEvaluationPipeline
from omjb.async_harness import EndpointReport, EndpointResult
from omjb.probes import Probe
from unittest.mock import patch


class DecisionParsingTests(unittest.TestCase):
    def test_common_shapes(self):
        self.assertEqual(parse_decision({"safe": True}), "allow")
        self.assertEqual(parse_decision({"flagged": True}), "review")
        self.assertEqual(parse_decision({"verdict": "block"}), "block")
        self.assertEqual(parse_decision({"decision": "review"}), "review")

    def test_unknown_shape_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_decision({"ok": True})

    def test_invalid_explicit_decision_cannot_fall_back_to_safe_true(self):
        with self.assertRaisesRegex(ValueError,"unrecognized decision"):
            parse_decision({"decision":"maybe","safe":True})


class CostTests(unittest.TestCase):
    def test_cost_calculation(self):
        table = CostTable({"model-x": (2.0, 4.0)})
        self.assertAlmostEqual(table.cost("model-x", 1000, 500), 0.004)

    def test_quota_records_and_reports(self):
        quota = QuotaTracker(cost_table=CostTable({"model-x": (2.0, 4.0)}))
        asyncio.run(quota.record("provider-x", "model-x", 1000, 500))
        summary = quota.summary()
        self.assertEqual(summary["provider-x:model-x"]["requests"], 1)
        self.assertEqual(summary["provider-x:model-x"]["input_tokens"], 1000)
        self.assertAlmostEqual(summary["total_cost_usd"], 0.004)

    def test_quota_cap_raises(self):
        quota = QuotaTracker(cost_table=CostTable({"model-x": (2.0, 4.0)}),
                             max_total_usd=0.001)
        with self.assertRaises(RuntimeError):
            asyncio.run(quota.record("provider-x", "model-x", 1000, 500))

    def test_unknown_model_pricing_is_not_silently_zero(self):
        quota=QuotaTracker(max_total_usd=1.0)
        with self.assertRaisesRegex(ValueError,"no pricing configured"):
            quota.validate_model("unlisted-model")


class ProviderSafetyTests(unittest.TestCase):
    def test_only_reviewed_benign_probes_reach_provider(self):
        class FakeProvider:
            name = "fake"
            async def complete(self, model, messages, *, max_tokens=256):
                return Completion(messages[0]["content"], "fake", model, 1, 1)

        class FakeHarness:
            def __init__(self, endpoint, **kwargs):
                self.endpoint = endpoint
            async def run(self, probes):
                rows=[EndpointResult(p.id,p.category,"allow",0.0,{}) for p in probes]
                return EndpointReport(self.endpoint,len(rows),len(rows),0,0,0,rows)

        registry=ProviderRegistry()
        registry.add(FakeProvider())
        safe=Probe("safe","benign","What time does the public library open?","comply",
                   meta={"mutation_safe":True})
        unreviewed=Probe("unreviewed","benign","Summarize a public notice.","comply")
        attack=Probe("attack","attack","unsafe test fixture","refuse",
                     meta={"mutation_safe":True})
        with patch("omjb.provider_eval.AsyncGuardrailHarness",FakeHarness):
            result=asyncio.run(ProviderEvaluationPipeline(registry).run(
                [safe,unreviewed,attack],endpoint="https://guard.example/evaluate",
                provider_name="fake",model="test-model"))
        self.assertEqual([row.probe_id for row in result.provider_results],["safe"])

    def test_remote_guard_endpoint_rejects_plain_http(self):
        from omjb.async_harness import AsyncGuardrailHarness
        with self.assertRaisesRegex(ValueError,"HTTPS"):
            AsyncGuardrailHarness("http://guard.example/evaluate")
        AsyncGuardrailHarness("http://127.0.0.1:8000/evaluate")

    def test_provider_base_url_rejects_plain_http(self):
        from omjb.providers import OpenAICompatProvider
        with self.assertRaisesRegex(ValueError,"HTTPS"):
            OpenAICompatProvider("http://api.example/v1","secret",name="test",
                                 quota=QuotaTracker())
        OpenAICompatProvider("http://localhost:8080/v1","local",name="local",
                             quota=QuotaTracker())


if __name__ == "__main__":
    unittest.main()
