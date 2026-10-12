import json
import os
import shutil
import unittest

from src.core.storage.file_store import FileStore
from src.modules.lane_b.domain.lane_b_service import LaneBService
from src.modules.lane_b.domain.scan_job import ScanJob

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_scan_job")


def write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def make_policy(budget: int = 100, min_periods: int = 2) -> dict:
    return {
        "policy_id": "POL-001",
        "version": 1,
        "effective_from": "2020-01-01T00:00:00+00:00",
        "approved_by": "program-owner",
        "scan": {"schedule": "weekly", "budget_queries_per_run": budget, "top_k": 1},
        "default_objectives": [{"metric": "latency_p50_ms", "direction": "down"}],
        "default_guardrails": [{"metric": "quality_score", "rule": ">= baseline", "hard": True}],
        "max_risk_tier": "config",
        "persistence": {"min_periods": min_periods, "share_threshold": 0.25},
        "min_runs": 30,
        "alert_triggers": [],
    }


def make_registry(features=None) -> dict:
    if features is None:
        features = ["Feature_X_v2"]
    return {
        "features": [
            {
                "feature": feature,
                "variants": [{"fingerprint": "fp_A", "rule_set": "v2", "subflow_steps": 6, "env": "prod"}],
                "steps": ["step1", "step2", "step3_subflow"],
                "business_rule_card": f"registry/cards/{feature}.md",
                "domain_owner": "alice",
                "lane_b_enabled": True,
                "mode": "propose",
            }
            for feature in features
        ]
    }


def make_runs(count: int, fingerprint="fp_A"):
    runs = []
    for i in range(count):
        total = 40000.0 + i * 100
        runs.append(
            {
                "run_id": f"r{i}",
                "timestamp": f"2026-10-{(i % 7) + 1:02d}T00:00:00Z",
                "latency_ms": total,
                "status": "success",
                "fingerprint": fingerprint,
                "config": {"STEP3_SUBFLOW_MAX_STEPS": "6"},
                "steps": {
                    "step1": round(total * 0.24, 2),
                    "step2": round(total * 0.16, 2),
                    "step3_subflow": round(total * 0.60, 2),
                },
            }
        )
    return runs


class ScanJobBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(BASE_DIR, exist_ok=True)
        self.store = FileStore(base_dir=BASE_DIR)
        self.service = LaneBService(file_store=self.store)
        self.write_policy()
        self.write_registry()

    def tearDown(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR, ignore_errors=True)

    def write_policy(self, budget=100):
        write_json(os.path.join(BASE_DIR, "policy", "policy.json"), make_policy(budget=budget))

    def write_registry(self, features=None, enabled=True):
        payload = make_registry(features)
        for entry in payload["features"]:
            entry["lane_b_enabled"] = enabled
        write_json(os.path.join(BASE_DIR, "registry", "features.json"), payload)
        for entry in payload["features"]:
            card = os.path.join(BASE_DIR, "registry", "cards", f"{entry['feature']}.md")
            os.makedirs(os.path.dirname(card), exist_ok=True)
            with open(card, "w", encoding="utf-8") as f:
                f.write("# Business Rule Card (test)\n")

    def job(self, loader=None) -> ScanJob:
        return ScanJob(self.service, runs_loader=loader or (lambda feature, period: make_runs(40)))

    def history(self) -> dict:
        path = os.path.join(BASE_DIR, "observations", "scan_history.json")
        self.assertTrue(os.path.exists(path), "scan_history.json must be written")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


class TestScanJobPersistence(ScanJobBase):
    def test_candidate_becomes_persistent_over_periods(self):
        job = self.job()

        first = job.run("2026-W41")
        self.assertEqual(first.errors, [])
        record = first.features[0]
        self.assertEqual(record.status, "scanned")
        self.assertEqual(record.kept, 0)  # seen in 1 period < min_periods 2

        history = self.history()
        self.assertEqual(history["features"]["Feature_X_v2"]["candidates"], {"step3_subflow": 1})
        self.assertEqual(history["features"]["Feature_X_v2"]["samples"]["2026-W41"], 40)

        second = job.run("2026-W42")
        self.assertEqual(second.features[0].status, "scanned")
        self.assertEqual(second.features[0].kept, 1)  # now seen in 2 periods
        self.assertEqual(
            self.history()["features"]["Feature_X_v2"]["candidates"]["step3_subflow"], 2
        )

    def test_same_instance_reuses_history_file(self):
        job = self.job()
        job.run("2026-W41")
        # a fresh job (new process / next scheduler tick) must keep counting
        job2 = self.job()
        record = job2.run("2026-W42").features[0]
        self.assertEqual(record.kept, 1)


class TestScanJobKillSwitchAndBudget(ScanJobBase):
    def test_disabled_feature_is_skipped_without_loading_logs(self):
        self.write_registry(enabled=False)
        calls = []

        def loader(feature, period):
            calls.append((feature, period))
            return make_runs(40)

        record = self.job(loader).run("2026-W41").features[0]
        self.assertEqual(record.status, "skipped_disabled")
        self.assertEqual(calls, [])

    def test_budget_stops_the_run(self):
        self.write_policy(budget=1)
        self.write_registry(features=["Feature_X_v2", "Feature_Y"])

        result = self.job().run("2026-W41")
        self.assertEqual(result.budget_limit, 1)
        self.assertEqual(result.budget_used, 1)
        self.assertTrue(result.stopped_by_budget)
        statuses = [f.status for f in result.features]
        self.assertEqual(statuses, ["scanned", "skipped_budget"])

    def test_missing_policy_does_not_crash_the_scheduler(self):
        os.remove(os.path.join(BASE_DIR, "policy", "policy.json"))
        result = self.job().run("2026-W41")
        self.assertTrue(result.errors)
        self.assertEqual(result.features, [])

    def test_feature_without_logs_is_recorded(self):
        result = self.job(lambda feature, period: []).run("2026-W41")
        self.assertEqual(result.features[0].status, "no_logs")
        self.assertEqual(result.budget_used, 1)


class TestScanJobSampleDrop(ScanJobBase):
    def test_sample_drop_recommends_downgrade_to_observe(self):
        job = ScanJob(self.service, runs_loader=lambda feature, period: make_runs(40))
        job.run("2026-W41")

        job2 = ScanJob(self.service, runs_loader=lambda feature, period: make_runs(12))
        record = job2.run("2026-W42").features[0]

        self.assertEqual(record.status, "scanned")
        self.assertIsNotNone(record.downgrade_recommended)
        self.assertEqual(record.kept, 0)  # 12 runs < min_runs: weak baseline, nothing proposed


if __name__ == "__main__":
    unittest.main()
