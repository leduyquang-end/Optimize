import json
import os
import shutil
import unittest

from src.core.schemas.baseline import BaselineReport, StepBreakdown
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause, ChangeDescription, ProsCons
from src.core.schemas.brief import RiskTier
from src.core.storage.file_store import FileStore
from src.modules.lane_b.domain.lane_b_service import LaneBService

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_lane_b")


def write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def make_policy(top_k: int = 1, expires_at=None) -> dict:
    return {
        "policy_id": "POL-001",
        "version": 1,
        "effective_from": "2020-01-01T00:00:00+00:00",
        "expires_at": expires_at,
        "approved_by": "program-owner",
        "scan": {"schedule": "weekly", "budget_queries_per_run": 100, "top_k": top_k},
        "default_objectives": [{"metric": "latency_p50_ms", "direction": "down"}],
        "default_guardrails": [{"metric": "quality_score", "rule": ">= baseline", "hard": True}],
        "max_risk_tier": "config",
        "persistence": {"min_periods": 2, "share_threshold": 0.25},
        "min_runs": 30,
        "alert_triggers": [],
    }


def make_registry(mode: str = "propose", with_card: bool = True, owner: str = "alice") -> dict:
    return {
        "features": [
            {
                "feature": "Feature_X_v2",
                "variants": [{"fingerprint": "fp_A", "rule_set": "v2", "subflow_steps": 6, "env": "prod"}],
                "steps": ["step1", "step2", "step3_subflow"],
                "business_rule_card": "registry/cards/Feature_X_v2.md" if with_card else "",
                "domain_owner": owner,
                "lane_b_enabled": True,
                "mode": mode,
            }
        ]
    }


def make_runs(count: int, fingerprint="fp_A", with_fingerprint=True):
    runs = []
    for i in range(count):
        total = 40000.0 + i * 100
        runs.append(
            {
                "run_id": f"r{i}",
                "timestamp": f"2026-10-{(i % 7) + 1:02d}T00:00:00Z",
                "latency_ms": total,
                "status": "success",
                "fingerprint": fingerprint if with_fingerprint else None,
                "steps": {
                    "step1": round(total * 0.24, 2),
                    "step2": round(total * 0.16, 2),
                    "step3_subflow": round(total * 0.60, 2),
                },
            }
        )
    return runs


def make_solution(solution_id: str, risk_tier=RiskTier.CONFIG, variables=None, impact="-10% to -20%") -> SolutionProposal:
    return SolutionProposal(
        solution_id=solution_id,
        feature_id="Feature_X_v2_subflow6_prod",
        snapshot_id="S-0001",
        verified_root_cause=VerifiedRootCause(
            statement="Step 3 subflow runs all steps although most runs converge earlier",
            evidence_log_lines=["log_402"],
        ),
        proposed_change="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
        change=ChangeDescription(
            description="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            variables=variables or ["STEP3_SUBFLOW_MAX_STEPS"],
            risk_tier=risk_tier,
            blast_radius="step3",
        ),
        risk_tier=risk_tier,
        blast_radius="step3",
        pros=["Latency -10% to -20%"],
        cons=["Runs needing more steps may be truncated"],
        pros_cons=[ProsCons(criterion="latency_p50_ms", pros="-10% to -20%", cons="none")],
        expected_impact_range=impact,
        effort_estimate="Small",
        retest_plan="Compare to S-0001, 7 days, min 30 runs, same fingerprint",
        rollback_plan="Revert STEP3_SUBFLOW_MAX_STEPS to 6",
        confidence_score=0.9,
    )


def make_baseline(sample_count=45, weak=False) -> BaselineReport:
    return BaselineReport(
        snapshot_id="S-0001",
        feature_id="Feature_X_v2_subflow6_prod",
        fingerprint="fp_A",
        time_window_start="2026-10-01T00:00:00Z",
        time_window_end="2026-10-08T00:00:00Z",
        sample_count=sample_count,
        is_weak_baseline=weak,
        weak_baseline_reason="below min_runs" if weak else None,
        total_p50_latency_ms=40000.0,
        total_p90_latency_ms=48000.0,
        total_p99_latency_ms=55000.0,
        step_breakdowns=[
            StepBreakdown(
                step_name="step3_subflow",
                pct_of_total_time=48.0,
                p50_latency_ms=19200.0,
                p90_latency_ms=23000.0,
                p99_latency_ms=40000.0,
                is_critical_path=True,
            )
        ],
        active_configs={"STEP3_SUBFLOW_MAX_STEPS": "6"},
    )


class LaneBBase(unittest.TestCase):
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

    def write_policy(self, top_k=1, expires_at=None):
        write_json(os.path.join(BASE_DIR, "policy", "policy.json"), make_policy(top_k=top_k, expires_at=expires_at))

    def write_registry(self, mode="propose", with_card=True, owner="alice"):
        write_json(os.path.join(BASE_DIR, "registry", "features.json"), make_registry(mode, with_card, owner))
        if with_card:
            card = os.path.join(BASE_DIR, "registry", "cards", "Feature_X_v2.md")
            os.makedirs(os.path.dirname(card), exist_ok=True)
            with open(card, "w", encoding="utf-8") as f:
                f.write("# Business Rule Card (test)\n")


class TestLaneBPreconditions(LaneBBase):
    def test_blocked_when_policy_missing(self):
        os.remove(os.path.join(BASE_DIR, "policy", "policy.json"))
        reasons = self.service.check_preconditions("Feature_X_v2")
        self.assertTrue(any("Policy not found" in r for r in reasons))

    def test_blocked_when_policy_expired(self):
        self.write_policy(expires_at="2020-01-01T00:00:00+00:00")
        reasons = self.service.check_preconditions("Feature_X_v2")
        self.assertTrue(any("expired" in r for r in reasons))

    def test_blocked_when_card_missing(self):
        self.write_registry(with_card=False)
        reasons = self.service.check_preconditions("Feature_X_v2")
        self.assertTrue(any("no Business Rule Card" in r for r in reasons))

    def test_blocked_when_domain_owner_pending(self):
        self.write_registry(owner="PENDING_DOMAIN_OWNER")
        reasons = self.service.check_preconditions("Feature_X_v2")
        self.assertTrue(any("domain owner" in r for r in reasons))

    def test_blocked_when_feature_not_registered(self):
        reasons = self.service.check_preconditions("Unknown_Feature")
        self.assertTrue(any("not in the feature registry" in r for r in reasons))

    def test_ready_when_everything_present(self):
        self.assertEqual(self.service.check_preconditions("Feature_X_v2"), [])

    def test_scan_returns_blocked_result_without_policy(self):
        os.remove(os.path.join(BASE_DIR, "policy", "policy.json"))
        result = self.service.scan("Feature_X_v2", make_runs(40), period="2026-W41")
        self.assertTrue(result.blocked)
        self.assertEqual(result.kept, [])
        self.assertIsNone(result.observation_file)


class TestLaneBScan(LaneBBase):
    def scan(self, runs, candidate_periods=None, active_configs=None):
        return self.service.scan(
            "Feature_X_v2",
            runs,
            period="2026-W41",
            runs_per_week=100,
            candidate_periods=candidate_periods or {"step3_subflow": 3},
            active_configs=active_configs or {"STEP3_SUBFLOW_MAX_STEPS": "6"},
        )

    def test_keeps_structural_candidate_and_writes_observation(self):
        runs = make_runs(40) + [{"run_id": "rx", "latency_ms": 1000.0, "status": "success"}]  # no fingerprint
        result = self.scan(runs)

        self.assertFalse(result.blocked)
        self.assertEqual(result.not_comparable_runs, 1)
        self.assertEqual(result.fingerprints, ["fp_A"])
        self.assertEqual(len(result.kept), 1)

        kept = result.kept[0]
        self.assertEqual(kept.step_name, "step3_subflow")
        self.assertEqual(kept.fingerprint, "fp_A")
        self.assertTrue(kept.snapshot_id.startswith("S-"))
        self.assertIn("share", kept.signals)

        self.assertIsNotNone(result.observation_file)
        self.assertTrue(os.path.exists(result.observation_file))
        with open(result.observation_file, "r", encoding="utf-8") as f:
            observation = json.load(f)
        self.assertEqual(len(observation["kept"]), 1)

        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "snapshots", f"{kept.snapshot_id}.json")))

    def test_rejects_transient_candidate(self):
        result = self.scan(make_runs(40), candidate_periods={"step3_subflow": 1})
        self.assertEqual(result.kept, [])
        stages = [r.stage for r in result.rejected]
        self.assertIn("persistence", stages)

    def test_rejects_candidate_already_reverted_in_lessons(self):
        self.store.append_lesson(
            {
                "lesson_id": "L-0001",
                "date": "2026-10-01T00:00:00+07:00",
                "solution_id": "SOL-0001",
                "fingerprint": "fp_A",
                "change": "STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
                "measured": {"snapshot_before": None, "snapshot_after": None, "result": "no gain"},
                "decision": "REVERT",
                "reason": "no evidence of improvement",
                "revisit_if": "rule-set change",
            }
        )
        result = self.scan(make_runs(40))
        self.assertEqual(result.kept, [])
        self.assertTrue(any(r.stage == "lessons" for r in result.rejected))

    def test_weak_baseline_never_reaches_b2(self):
        result = self.scan(make_runs(10))
        self.assertEqual(result.kept, [])
        self.assertTrue(any(r.stage == "gate_b1" for r in result.rejected))

    def test_runs_without_latency_are_data_gaps_not_estimated(self):
        runs = make_runs(40)
        runs.append(
            {
                "run_id": "no-latency",
                "timestamp": "2026-10-01T00:00:00Z",
                "status": "success",
                "fingerprint": "fp_A",
            }
        )
        result = self.scan(runs)
        self.assertTrue(any("data gap" in r.reason for r in result.rejected))


class TestLaneBPropose(LaneBBase):
    def propose(self, proposals, baseline=None, period="2026-W41"):
        return self.service.propose(
            feature_id="Feature_X_v2",
            baseline=baseline or make_baseline(),
            proposals=proposals,
            period=period,
        )

    def test_blocked_in_observe_mode(self):
        self.write_registry(mode="observe")
        result = self.propose([make_solution("SOL-0001")])
        self.assertTrue(result.blocked)
        self.assertEqual(result.queued_count, 0)
        self.assertTrue(any("observe" in r for r in result.blocked_reasons))

    def test_queued_verified_and_hypothesis_kept_out(self):
        hypothesis = make_solution("SOL-0002")
        hypothesis.is_unverified_hypothesis = True
        hypothesis.verified_root_cause = VerifiedRootCause(statement="guessed cause")

        result = self.propose([make_solution("SOL-0001"), hypothesis])

        outcomes = {o.solution_id: o for o in result.outcomes}
        self.assertEqual(outcomes["SOL-0001"].outcome, "queued")
        self.assertEqual(outcomes["SOL-0001"].confidence, "medium")
        self.assertEqual(outcomes["SOL-0002"].outcome, "hypothesis")
        self.assertEqual(result.queued_count, 1)

        queue_path = os.path.join(BASE_DIR, outcomes["SOL-0001"].queue_file)
        self.assertTrue(os.path.exists(queue_path))
        with open(queue_path, "r", encoding="utf-8") as f:
            package = json.load(f)
        self.assertIn("problem", package)
        self.assertIn("decision_needed", package)
        self.assertEqual(package["confidence"], "medium")

    def test_low_confidence_when_baseline_weak(self):
        baseline = make_baseline(sample_count=10, weak=True)
        result = self.propose([make_solution("SOL-0001")], baseline=baseline)
        outcomes = {o.solution_id: o for o in result.outcomes}
        self.assertEqual(outcomes["SOL-0001"].outcome, "queued")
        self.assertEqual(outcomes["SOL-0001"].confidence, "low")

    def test_over_ceiling_rejected(self):
        result = self.propose([make_solution("SOL-0001", risk_tier=RiskTier.CODE)])
        outcomes = {o.solution_id: o for o in result.outcomes}
        self.assertEqual(outcomes["SOL-0001"].outcome, "rejected")
        self.assertTrue(any("ceiling" in r.lower() for r in outcomes["SOL-0001"].reasons))
        self.assertEqual(result.queued_count, 0)

    def test_top_k_limits_queue(self):
        result = self.propose(
            [
                make_solution("SOL-0001", impact="-10% to -20%"),
                make_solution("SOL-0002", impact="-5% to -8%"),
            ]
        )
        outcomes = {o.solution_id: o for o in result.outcomes}
        self.assertEqual(outcomes["SOL-0001"].outcome, "queued")
        self.assertEqual(outcomes["SOL-0002"].outcome, "deferred")
        self.assertEqual(result.queued_count, 1)

    def test_guardrail_tradeoff_rejected_by_self_criticism(self):
        proposal = make_solution("SOL-0001")
        proposal.guardrail_tradeoffs = ["quality_score drops below baseline"]
        result = self.propose([proposal])
        outcomes = {o.solution_id: o for o in result.outcomes}
        self.assertEqual(outcomes["SOL-0001"].outcome, "rejected")
        self.assertTrue(any("B2-C1" in r for r in outcomes["SOL-0001"].reasons))


if __name__ == "__main__":
    unittest.main()
