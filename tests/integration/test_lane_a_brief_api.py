import json
import os
import shutil
import unittest

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_brief_api")
STORE = os.path.join(TMP, "store")


def brief_payload(**overrides):
    payload = {
        "feature_id": "Feature_X_v2_subflow6_prod",
        "optimization_targets": [
            {
                "metric_name": "latency_p50_ms",
                "unit": "ms",
                "direction": "decrease",
                "target_value": 40000.0,
                "priority": 1,
                "measurement_source": "loki:{app=\"x\"} | json | latency_ms",
            }
        ],
        "guardrails": [
            {"metric_name": "quality_score", "max_allowed_change_pct": 2.0, "hard": True}
        ],
        "thresholds": {"keep_improvement_pct": 25.0, "revert_improvement_pct": 10.0},
        "max_risk_tier": "prompt",
        "scope_in": ["subflow6"],
        "scope_out": ["model selection"],
        "business_context": "Giảm độ trễ cho luồng xử lý hồ sơ.",
        "business_rule_card": "optimization_data/registry/cards/Feature_X_v2.md",
        "business_rule_card_confirmed": True,
        "data_gaps": [],
    }
    payload.update(overrides)
    return payload


class BriefApiBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(STORE, exist_ok=True)

    def tearDown(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP, ignore_errors=True)

    def post_brief(self, payload):
        return client.post(
            "/api/v1/lane-a/brief", params={"base_dir": STORE}, json=payload
        )


class TestBriefApi(BriefApiBase):
    def test_valid_brief_is_validated_and_saved(self):
        res = self.post_brief(brief_payload())
        self.assertEqual(res.status_code, 201, res.text)
        body = res.json()
        self.assertTrue(body["brief_id"].startswith("BR-2026-"))
        self.assertEqual(body["brief"]["status"], "validated")
        self.assertEqual(body["brief"]["feature_id"], "Feature_X_v2_subflow6_prod")

        saved = client.get(
            f"/api/v1/lane-a/briefs/{body['brief_id']}", params={"base_dir": STORE}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "validated")

    def test_missing_hard_guardrail_reports_a1_v3(self):
        res = self.post_brief(
            brief_payload(guardrails=[{"metric_name": "q", "max_allowed_change_pct": 1, "hard": False}])
        )
        self.assertEqual(res.status_code, 422)
        errors = res.json()["detail"]["errors"]
        self.assertTrue(any(e.startswith("A1-V3") for e in errors))

    def test_unconfirmed_rule_card_reports_a1_v6(self):
        res = self.post_brief(brief_payload(business_rule_card_confirmed=False))
        self.assertEqual(res.status_code, 422)
        self.assertTrue(any(e.startswith("A1-V6") for e in res.json()["detail"]["errors"]))

    def test_objective_without_measurement_source_reports_a1_v2(self):
        res = self.post_brief(
            brief_payload(
                optimization_targets=[
                    {
                        "metric_name": "latency_p50_ms",
                        "unit": "ms",
                        "direction": "decrease",
                        "target_value": 40000.0,
                        "measurement_source": "",
                    }
                ]
            )
        )
        self.assertEqual(res.status_code, 422)
        self.assertTrue(any(e.startswith("A1-V2") for e in res.json()["detail"]["errors"]))

    def test_bad_thresholds_report_a1_v4(self):
        res = self.post_brief(
            brief_payload(thresholds={"keep_improvement_pct": 5.0, "revert_improvement_pct": 10.0})
        )
        self.assertEqual(res.status_code, 422)
        self.assertTrue(any(e.startswith("A1-V4") for e in res.json()["detail"]["errors"]))

    def test_invalid_brief_is_not_saved(self):
        self.post_brief(brief_payload(business_rule_card_confirmed=False))
        listed = client.get("/api/v1/lane-a/briefs", params={"base_dir": STORE})
        self.assertEqual(listed.json()["briefs"], [])

    def test_list_and_missing_brief(self):
        created = self.post_brief(brief_payload()).json()
        listed = client.get("/api/v1/lane-a/briefs", params={"base_dir": STORE})
        self.assertEqual([b["brief_id"] for b in listed.json()["briefs"]], [created["brief_id"]])

        missing = client.get("/api/v1/lane-a/briefs/BR-9999", params={"base_dir": STORE})
        self.assertEqual(missing.status_code, 404)

    def test_legacy_validate_endpoint_still_works(self):
        res = client.post("/api/v1/lane-a/brief/validate", json=brief_payload())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "Gate 1 Passed")


if __name__ == "__main__":
    unittest.main()
