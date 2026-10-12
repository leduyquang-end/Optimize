import json
import os
import shutil
import unittest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

API_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_api_laneb")

VALID_BRIEF = {
    "feature_id": "Feature_X_v2_subflow6_prod",
    "optimization_targets": [
        {
            "metric_name": "latency_p50_ms",
            "unit": "ms",
            "direction": "decrease",
            "target_value": 25000,
            "measurement_source": "Loki: quantile_over_time(0.5, ...)",
        }
    ],
    "guardrails": [{"metric_name": "quality_score", "max_allowed_change_pct": 0.0}],
    "thresholds": {"keep_improvement_pct": 25.0, "revert_improvement_pct": 10.0},
    "max_risk_tier": "prompt",
    "scope_in": ["step3"],
    "scope_out": ["model_change"],
    "business_context": "Financial profile evaluation",
    "business_rule_card": "registry/cards/Feature_X_v2.md",
    "business_rule_card_confirmed": True,
}

VALIDITY = {
    "v1_same_fingerprint": True,
    "v2_same_business_complexity": True,
    "v3_equivalent_conditions": True,
    "v4_sufficient_sample_size": True,
    "v5_single_variable_diff": True,
    "v6_distribution_provided": True,
}


class TestApiEndpoints(unittest.TestCase):
    def test_root_redirects_to_ui(self):
        res = client.get("/", follow_redirects=True)
        self.assertEqual(res.status_code, 200)
        self.assertIn("Chọn lane", res.text)

    def test_health(self):
        res = client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "running")
        self.assertEqual(res.json()["ui"], "/ui")

    def test_lane_a_brief_validate_pass(self):
        res = client.post("/api/v1/lane-a/brief/validate", json=VALID_BRIEF)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "Gate 1 Passed")

    def test_lane_a_brief_validate_rejects_unconfirmed_card(self):
        payload = dict(VALID_BRIEF, business_rule_card_confirmed=False)
        res = client.post("/api/v1/lane-a/brief/validate", json=payload)
        self.assertEqual(res.status_code, 400)
        errors = res.json()["detail"]["errors"]
        self.assertTrue(any(e.startswith("A1-V6") for e in errors))

    def test_section_2_retest_evaluate_keep(self):
        payload = {
            "solution_id": "SOL-0123",
            "snapshot_before": "S-0012",
            "snapshot_after": "S-0019",
            "baseline_p50": 40000.0,
            "retest_p50": 25000.0,
            "validity": VALIDITY,
        }
        res = client.post("/api/v1/section-2/retest/evaluate", json=payload)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["decision"], "KEEP")
        self.assertEqual(body["improvement_pct"], 37.5)

    def test_section_2_retest_evaluate_invalid_on_fingerprint_mismatch(self):
        payload = {
            "solution_id": "SOL-0123",
            "snapshot_before": "S-0012",
            "snapshot_after": "S-0019",
            "baseline_p50": 40000.0,
            "retest_p50": 25000.0,
            "validity": dict(VALIDITY, v1_same_fingerprint=False),
        }
        res = client.post("/api/v1/section-2/retest/evaluate", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["decision"], "INVALID")

    def test_lane_b_self_criticism_rejects_guardrail_tradeoff(self):
        proposal = {
            "solution_id": "SOL-0124",
            "feature_id": "Feature_X_v2_subflow6_prod",
            "verified_root_cause": {"statement": "log line 402", "evidence_log_lines": ["log_402"]},
            "proposed_change": "STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            "risk_tier": "config",
            "pros": ["latency down"],
            "cons": ["quality risk"],
            "expected_impact_range": "-15% to -20%",
            "rollback_plan": "Revert to 6",
            "guardrail_tradeoffs": ["quality_score drops below baseline"],
        }
        policy = {
            "policy_id": "POL-001",
            "version": 1,
            "effective_from": "2026-10-08T00:00:00+07:00",
            "approved_by": "program-owner",
            "max_risk_tier": "config",
            "default_guardrails": [
                {"metric": "quality_score", "rule": ">= baseline", "hard": True}
            ],
        }
        res = client.post("/api/v1/lane-b/proposal/self-criticism", json={"proposal": proposal, "policy": policy})
        self.assertEqual(res.status_code, 400)
        rejections = res.json()["detail"]["rejections"]
        self.assertTrue(any(r.startswith("B2-C1") for r in rejections))

    def test_policy_and_registry_files_load(self):
        from src.modules.policy_registry.domain.policy_service import PolicyService, RegistryService

        policy = PolicyService(base_dir="optimization_data").get_policy()
        self.assertEqual(policy.min_runs, 30)
        self.assertEqual(policy.max_risk_tier.value, "config")

        registry = RegistryService(base_dir="optimization_data").load()
        self.assertTrue(registry)
        self.assertEqual(registry[0].mode.value, "observe")
        self.assertFalse(registry[0].lane_b_enabled)


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _make_runs(count: int):
    runs = []
    for i in range(count):
        total = 40000.0 + i * 100
        runs.append(
            {
                "run_id": f"r{i}",
                "timestamp": f"2026-10-{(i % 7) + 1:02d}T00:00:00Z",
                "latency_ms": total,
                "status": "success",
                "fingerprint": "fp_A",
                "steps": {
                    "step1": round(total * 0.24, 2),
                    "step2": round(total * 0.16, 2),
                    "step3_subflow": round(total * 0.60, 2),
                },
            }
        )
    return runs


def _make_proposal(solution_id: str, risk_tier: str = "config"):
    return {
        "solution_id": solution_id,
        "feature_id": "Feature_X_v2_subflow6_prod",
        "snapshot_id": "S-0001",
        "verified_root_cause": {"statement": "step3 runs all steps", "evidence_log_lines": ["log_402"]},
        "proposed_change": "STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
        "change": {
            "description": "STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            "variables": ["STEP3_SUBFLOW_MAX_STEPS"],
            "risk_tier": risk_tier,
            "blast_radius": "step3",
        },
        "risk_tier": risk_tier,
        "blast_radius": "step3",
        "pros": ["Latency -10% to -20%"],
        "cons": ["Truncation risk"],
        "pros_cons": [{"criterion": "latency_p50_ms", "pros": "-10% to -20%", "cons": "none"}],
        "expected_impact_range": "-10% to -20%",
        "effort_estimate": "Small",
        "retest_plan": "Compare to S-0001, 7 days, min 30 runs",
        "rollback_plan": "Revert to 6",
        "confidence_score": 0.9,
    }


BASELINE = {
    "snapshot_id": "S-0001",
    "feature_id": "Feature_X_v2_subflow6_prod",
    "fingerprint": "fp_A",
    "time_window_start": "2026-10-01T00:00:00Z",
    "time_window_end": "2026-10-08T00:00:00Z",
    "sample_count": 45,
    "total_p50_latency_ms": 40000.0,
    "total_p90_latency_ms": 48000.0,
    "total_p99_latency_ms": 55000.0,
    "step_breakdowns": [
        {
            "step_name": "step3_subflow",
            "pct_of_total_time": 48.0,
            "p50_latency_ms": 19200.0,
            "p90_latency_ms": 23000.0,
            "p99_latency_ms": 40000.0,
            "is_critical_path": True,
        }
    ],
    "active_configs": {"STEP3_SUBFLOW_MAX_STEPS": "6"},
}


class TestLaneBApi(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(API_BASE_DIR, exist_ok=True)
        _write_json(
            os.path.join(API_BASE_DIR, "policy", "policy.json"),
            {
                "policy_id": "POL-001",
                "version": 1,
                "effective_from": "2020-01-01T00:00:00+00:00",
                "approved_by": "program-owner",
                "scan": {"schedule": "weekly", "budget_queries_per_run": 100, "top_k": 1},
                "default_objectives": [{"metric": "latency_p50_ms", "direction": "down"}],
                "default_guardrails": [{"metric": "quality_score", "rule": ">= baseline", "hard": True}],
                "max_risk_tier": "config",
                "persistence": {"min_periods": 2, "share_threshold": 0.25},
                "min_runs": 30,
                "alert_triggers": [],
            },
        )
        _write_json(
            os.path.join(API_BASE_DIR, "registry", "features.json"),
            {
                "features": [
                    {
                        "feature": "Feature_X_v2",
                        "variants": [{"fingerprint": "fp_A", "rule_set": "v2", "subflow_steps": 6, "env": "prod"}],
                        "steps": ["step1", "step2", "step3_subflow"],
                        "business_rule_card": "registry/cards/Feature_X_v2.md",
                        "domain_owner": "alice",
                        "lane_b_enabled": True,
                        "mode": "propose",
                    }
                ]
            },
        )
        card = os.path.join(API_BASE_DIR, "registry", "cards", "Feature_X_v2.md")
        os.makedirs(os.path.dirname(card), exist_ok=True)
        with open(card, "w", encoding="utf-8") as f:
            f.write("# Business Rule Card (test)\n")

    def tearDown(self):
        if os.path.isdir(API_BASE_DIR):
            shutil.rmtree(API_BASE_DIR, ignore_errors=True)

    def test_scan_endpoint_keeps_candidate(self):
        payload = {
            "feature_id": "Feature_X_v2",
            "period": "2026-W41",
            "runs": _make_runs(40),
            "runs_per_week": 100,
            "candidate_periods": {"step3_subflow": 3},
            "active_configs": {"STEP3_SUBFLOW_MAX_STEPS": "6"},
            "base_dir": API_BASE_DIR,
        }
        res = client.post("/api/v1/lane-b/scan", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertFalse(body["blocked"])
        self.assertEqual(len(body["kept"]), 1)
        self.assertEqual(body["kept"][0]["step_name"], "step3_subflow")
        self.assertTrue(os.path.exists(body["observation_file"]))

    def test_scan_endpoint_conflict_without_policy(self):
        os.remove(os.path.join(API_BASE_DIR, "policy", "policy.json"))
        payload = {
            "feature_id": "Feature_X_v2",
            "period": "2026-W41",
            "runs": _make_runs(5),
            "base_dir": API_BASE_DIR,
        }
        res = client.post("/api/v1/lane-b/scan", json=payload)
        self.assertEqual(res.status_code, 409)
        self.assertIn("reasons", res.json()["detail"])

    def test_propose_endpoint_queues_package(self):
        payload = {
            "feature_id": "Feature_X_v2",
            "period": "2026-W41",
            "baseline": BASELINE,
            "proposals": [_make_proposal("SOL-0100")],
            "base_dir": API_BASE_DIR,
        }
        res = client.post("/api/v1/lane-b/propose", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["queued_count"], 1)
        self.assertEqual(body["outcomes"][0]["outcome"], "queued")
        self.assertTrue(os.path.exists(os.path.join(API_BASE_DIR, body["outcomes"][0]["queue_file"])))

    def test_propose_endpoint_conflict_in_observe_mode(self):
        registry_path = os.path.join(API_BASE_DIR, "registry", "features.json")
        with open(registry_path, "r", encoding="utf-8") as f:
            registry = json.load(f)
        registry["features"][0]["mode"] = "observe"
        _write_json(registry_path, registry)

        payload = {
            "feature_id": "Feature_X_v2",
            "period": "2026-W41",
            "baseline": BASELINE,
            "proposals": [_make_proposal("SOL-0100")],
            "base_dir": API_BASE_DIR,
        }
        res = client.post("/api/v1/lane-b/propose", json=payload)
        self.assertEqual(res.status_code, 409)
        self.assertTrue(any("observe" in r for r in res.json()["detail"]["reasons"]))


class TestReviewAndMetricsApi(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(API_BASE_DIR, exist_ok=True)
        _write_json(
            os.path.join(API_BASE_DIR, "policy", "policy.json"),
            {
                "policy_id": "POL-001",
                "version": 1,
                "effective_from": "2020-01-01T00:00:00+00:00",
                "approved_by": "program-owner",
                "scan": {"schedule": "weekly", "budget_queries_per_run": 100, "top_k": 1},
                "default_objectives": [{"metric": "latency_p50_ms", "direction": "down"}],
                "default_guardrails": [{"metric": "quality_score", "rule": ">= baseline", "hard": True}],
                "max_risk_tier": "config",
                "persistence": {"min_periods": 2, "share_threshold": 0.25},
                "min_runs": 30,
                "alert_triggers": [],
            },
        )
        _write_json(
            os.path.join(API_BASE_DIR, "registry", "features.json"),
            {
                "features": [
                    {
                        "feature": "Feature_X_v2",
                        "variants": [{"fingerprint": "fp_A", "rule_set": "v2", "subflow_steps": 6, "env": "prod"}],
                        "steps": ["step1", "step2", "step3_subflow"],
                        "business_rule_card": "registry/cards/Feature_X_v2.md",
                        "domain_owner": "alice",
                        "lane_b_enabled": True,
                        "mode": "propose",
                    }
                ]
            },
        )
        card = os.path.join(API_BASE_DIR, "registry", "cards", "Feature_X_v2.md")
        os.makedirs(os.path.dirname(card), exist_ok=True)
        with open(card, "w", encoding="utf-8") as f:
            f.write("# Business Rule Card (test)\n")

    def tearDown(self):
        if os.path.isdir(API_BASE_DIR):
            shutil.rmtree(API_BASE_DIR, ignore_errors=True)

    def queue_package(self):
        payload = {
            "feature_id": "Feature_X_v2",
            "period": "2026-W41",
            "baseline": BASELINE,
            "proposals": [_make_proposal("SOL-0100")],
            "base_dir": API_BASE_DIR,
        }
        res = client.post("/api/v1/lane-b/propose", json=payload)
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["outcomes"][0]["solution_id"]

    def test_review_flow_from_queue_to_decision(self):
        solution_id = self.queue_package()

        res = client.get("/api/v1/lane-b/review/list", params={"base_dir": API_BASE_DIR})
        self.assertEqual(res.status_code, 200, res.text)
        packages = res.json()["packages"]
        self.assertEqual([p["solution_id"] for p in packages], [solution_id])
        self.assertEqual(packages[0]["status"], "pending")
        self.assertIsNotNone(packages[0]["due_at"])

        # rejection without a reason is refused - B2-R1 needs a written reason
        res = client.post(
            "/api/v1/lane-b/review/decide",
            json={
                "solution_id": solution_id,
                "decision": "rejected",
                "reviewer": "mai",
                "base_dir": API_BASE_DIR,
            },
        )
        self.assertEqual(res.status_code, 400)

        res = client.post(
            "/api/v1/lane-b/review/decide",
            json={
                "solution_id": solution_id,
                "decision": "rejected",
                "reviewer": "mai",
                "reason": "business rule card forbids lowering max steps",
                "base_dir": API_BASE_DIR,
            },
        )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["status"], "rejected")

        res = client.get("/api/v1/lane-b/review/list",
                         params={"status": "pending", "base_dir": API_BASE_DIR})
        self.assertEqual(res.json()["packages"], [])

        # the reason must be traceable in lessons so it is not proposed again
        lessons_path = os.path.join(API_BASE_DIR, "lessons", "lessons.jsonl")
        with open(lessons_path, "r", encoding="utf-8") as f:
            lessons = [json.loads(line) for line in f if line.strip()]
        self.assertEqual(len(lessons), 1)
        self.assertIn("mai", lessons[0]["reason"])

    def test_review_overdue_and_metrics_endpoints(self):
        self.queue_package()

        res = client.get("/api/v1/lane-b/review/overdue", params={"base_dir": API_BASE_DIR})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertEqual(res.json()["count"], 0)  # fresh package, due in 2 business days

        res = client.get("/api/v1/lane-b/metrics", params={"base_dir": API_BASE_DIR})
        self.assertEqual(res.status_code, 200, res.text)
        metrics = res.json()
        self.assertIsNone(metrics["approval_rate"])  # nothing decided yet
        self.assertEqual(metrics["approval"]["decided"], 0)
        self.assertEqual(metrics["approval"]["pending"], 1)
        self.assertEqual(metrics["guardrail_violations"], 0)

    def test_metrics_endpoint_reports_rates_with_denominators(self):
        from src.core.storage.file_store import FileStore

        store = FileStore(base_dir=API_BASE_DIR)
        store.append_lesson(
            {
                "lesson_id": "L-0001",
                "date": "2026-10-01T00:00:00+07:00",
                "solution_id": "SOL-A",
                "fingerprint": "fp_A",
                "change": "STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
                "measured": {"snapshot_before": "S-1", "snapshot_after": "S-2", "result": "30%"},
                "decision": "KEEP",
                "reason": "kept",
                "revisit_if": None,
            }
        )
        metrics = client.get("/api/v1/lane-b/metrics", params={"base_dir": API_BASE_DIR}).json()
        self.assertEqual(metrics["keep_rate"], 1.0)
        self.assertEqual(metrics["revert_rate"], 0.0)
        self.assertEqual(metrics["measured"]["total"], 1)


if __name__ == "__main__":
    unittest.main()
