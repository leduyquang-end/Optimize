import json
import os
import shutil
import unittest
from datetime import datetime, timedelta, timezone

from src.core.storage.file_store import FileStore
from src.modules.lane_b.domain.metrics_service import LaneBMetricsService
from src.modules.lane_b.domain.review_service import ReviewService

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_review")


def write_package(
    solution_id="SOL-0100",
    status="pending",
    due_at=None,
    decision=None,
    reviewer=None,
    reason=None,
    proposal="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
):
    package = {
        "solution_id": solution_id,
        "status": status,
        "problem": "step3 dominates runtime",
        "proposal": proposal,
        "tradeoff": {"pros": ["latency down"], "cons": ["truncation risk"]},
        "evidence": {
            "root_cause": "runs all steps although most converge earlier",
            "log_lines": ["log_402"],
            "snapshot_id": "S-0001",
            "fingerprint": "fp_A",
            "queries": ["q1"],
        },
        "confidence": "medium",
        "risk_tier": "config",
        "rollback": "Revert to 6",
        "remeasure": "7 days, min 30 runs",
        "period": "2026-W41",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "due_at": due_at or (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "decision": decision,
        "reviewer": reviewer,
        "decided_at": None,
        "reason": reason,
        "required_changes": [],
    }
    path = os.path.join(BASE_DIR, "queue", "review", f"REV-{solution_id}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(package, f, indent=2, ensure_ascii=False)
    return package


class ReviewBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(BASE_DIR, exist_ok=True)
        self.store = FileStore(base_dir=BASE_DIR)
        self.reviews = ReviewService(file_store=self.store)

    def tearDown(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR, ignore_errors=True)


class TestReviewWorkflow(ReviewBase):
    def test_list_pending_and_get(self):
        write_package()
        write_package(solution_id="SOL-0101")
        pending = self.reviews.list_packages(status="pending")
        self.assertEqual(len(pending), 2)
        self.assertEqual(self.reviews.get("SOL-0100")["status"], "pending")

    def test_approve_records_reviewer_without_lesson(self):
        write_package()
        package = self.reviews.decide("SOL-0100", "approved", reviewer="mai")
        self.assertEqual(package["status"], "approved")
        self.assertEqual(package["reviewer"], "mai")
        self.assertIsNotNone(package["decided_at"])
        self.assertEqual(self.store.read_lessons(), [])

    def test_approved_with_changes_requires_list(self):
        write_package()
        with self.assertRaises(ValueError):
            self.reviews.decide("SOL-0100", "approved_with_changes", reviewer="mai")

    def test_approved_with_changes_records_changes(self):
        write_package()
        package = self.reviews.decide(
            "SOL-0100", "approved_with_changes", reviewer="mai",
            required_changes=["keep max_steps=4 instead of 3"],
        )
        self.assertEqual(package["status"], "approved_with_changes")
        self.assertEqual(package["required_changes"], ["keep max_steps=4 instead of 3"])

    def test_reject_requires_reason(self):
        write_package()
        with self.assertRaises(ValueError):
            self.reviews.decide("SOL-0100", "rejected", reviewer="mai")

    def test_reject_appends_reason_to_lessons(self):
        write_package()
        package = self.reviews.decide(
            "SOL-0100", "rejected", reviewer="mai",
            reason="business rule card forbids lowering max steps below 5",
        )
        self.assertEqual(package["status"], "rejected")

        lessons = self.store.read_lessons()
        self.assertEqual(len(lessons), 1)
        self.assertEqual(lessons[0]["solution_id"], "SOL-0100")
        self.assertEqual(lessons[0]["decision"], "REVERT")
        self.assertIn("mai", lessons[0]["reason"])
        self.assertIn("lowering max steps below 5", lessons[0]["reason"])
        self.assertIn("not measured", lessons[0]["measured"]["result"])

    def test_cannot_decide_twice(self):
        write_package()
        self.reviews.decide("SOL-0100", "approved", reviewer="mai")
        with self.assertRaises(ValueError):
            self.reviews.decide("SOL-0100", "rejected", reviewer="lan", reason="changed my mind")

    def test_invalid_decision_and_missing_reviewer(self):
        write_package()
        with self.assertRaises(ValueError):
            self.reviews.decide("SOL-0100", "maybe", reviewer="mai")
        with self.assertRaises(ValueError):
            self.reviews.decide("SOL-0100", "approved", reviewer="  ")

    def test_overdue_packages_are_reported_not_approved(self):
        write_package(solution_id="SOL-LATE", due_at="2020-01-01T00:00:00+00:00")
        write_package(solution_id="SOL-OK", due_at=(datetime.now(timezone.utc) + timedelta(days=5)).isoformat())

        overdue = self.reviews.overdue()
        self.assertEqual([p["solution_id"] for p in overdue], ["SOL-LATE"])
        # still pending - a human decides, never auto-approval
        self.assertEqual(self.reviews.get("SOL-LATE")["status"], "pending")


class TestLaneBMetrics(ReviewBase):
    def test_metrics_on_empty_store(self):
        metrics = LaneBMetricsService(file_store=self.store).compute()
        self.assertIsNone(metrics["approval_rate"])
        self.assertIsNone(metrics["keep_rate"])
        self.assertIsNone(metrics["false_alarm_rate"])
        self.assertEqual(metrics["guardrail_violations"], 0)

    def test_metrics_from_recorded_data(self):
        # two decided packages: one approved, one rejected for a guardrail reason
        write_package(solution_id="SOL-0100", status="approved", decision="approved", reviewer="mai")
        write_package(
            solution_id="SOL-0101", status="rejected", decision="rejected", reviewer="mai",
            reason="B2-C1: trades off quality_score guardrail",
        )
        write_package(solution_id="SOL-0102")  # still pending

        # measured lessons: 1 KEEP, 1 REVERT (+1 rejection lesson without measurement)
        self.store.append_lesson({
            "lesson_id": "L-0001", "date": "2026-10-01T00:00:00+07:00", "solution_id": "SOL-A",
            "fingerprint": "fp_A", "change": "STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            "measured": {"snapshot_before": "S-1", "snapshot_after": "S-2", "result": "30%"},
            "decision": "KEEP", "reason": "kept", "revisit_if": None,
        })
        self.store.append_lesson({
            "lesson_id": "L-0002", "date": "2026-10-02T00:00:00+07:00", "solution_id": "SOL-B",
            "fingerprint": "fp_A", "change": "PROMPT_TEMPLATE shortened",
            "measured": {"snapshot_before": "S-3", "snapshot_after": "S-4", "result": "2%"},
            "decision": "REVERT", "reason": "no evidence", "revisit_if": "new model",
        })
        self.store.append_lesson({
            "lesson_id": "L-0003", "date": "2026-10-03T00:00:00+07:00", "solution_id": "SOL-C",
            "fingerprint": "fp_A", "change": "rejected at review",
            "measured": {"snapshot_before": "S-5", "snapshot_after": None, "result": "not measured"},
            "decision": "REVERT", "reason": "rejected", "revisit_if": None,
        })

        # observation: 1 kept + 1 persistence false alarm + 1 lesson rejection
        observation = {
            "feature": "Feature_X_v2",
            "period": "2026-W41",
            "kept": [{"step_name": "step3_subflow", "fingerprint": "fp_A"}],
            "rejected": [
                {"stage": "persistence", "item": "step2", "reason": "only 1 period"},
                {"stage": "lessons", "item": "step4", "reason": "reverted"},
            ],
        }
        obs_path = os.path.join(BASE_DIR, "observations", "scan-Feature_X_v2-2026-W41.json")
        os.makedirs(os.path.dirname(obs_path), exist_ok=True)
        with open(obs_path, "w", encoding="utf-8") as f:
            json.dump(observation, f)

        metrics = LaneBMetricsService(file_store=self.store).compute()

        self.assertEqual(metrics["approval_rate"], 0.5)      # 1 approved / 2 decided
        self.assertEqual(metrics["approval"]["pending"], 1)
        self.assertEqual(metrics["keep_rate"], 0.5)          # 1 KEEP / 2 measured
        self.assertEqual(metrics["revert_rate"], 0.5)
        self.assertEqual(metrics["measured"]["total"], 2)    # rejection lesson not measured
        self.assertAlmostEqual(metrics["false_alarm_rate"], 1 / 3, places=3)  # 1 persistence / 3 candidates
        self.assertEqual(metrics["guardrail_violations"], 1)


if __name__ == "__main__":
    unittest.main()
