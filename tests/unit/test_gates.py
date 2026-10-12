import unittest
from src.core.schemas.brief import OptimizationBrief, OptimizationTarget, Guardrail, Threshold, RiskTier
from src.core.schemas.baseline import BaselineReport
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause, ProsCons, ChangeDescription
from src.core.schemas.measurement import ValidityCheckResult
from src.modules.lane_a.gates.gate_1 import Gate1Evaluator
from src.modules.lane_a.gates.gate_2 import Gate2Evaluator
from src.modules.lane_a.gates.gate_3 import Gate3Evaluator
from src.modules.section_2.domain.verification_service import VerificationEngine, VerificationDecision

def build_validity(passed: bool = True, **overrides) -> ValidityCheckResult:
    values = dict(
        v1_same_fingerprint=passed,
        v2_same_business_complexity=passed,
        v3_equivalent_conditions=passed,
        v4_sufficient_sample_size=passed,
        v5_single_variable_diff=passed,
        v6_distribution_provided=passed,
    )
    values.update(overrides)
    return ValidityCheckResult(**values)

class TestOptimizationGates(unittest.TestCase):
    def make_brief(self, **overrides) -> OptimizationBrief:
        fields = dict(
            feature_id="Feature_X_v2",
            optimization_targets=[
                OptimizationTarget(
                    metric_name="latency_ms",
                    unit="ms",
                    direction="decrease",
                    target_value=25000.0,
                    measurement_source="Loki: quantile_over_time(0.5, {feature=...})",
                )
            ],
            guardrails=[Guardrail(metric_name="token_count", max_allowed_change_pct=10.0)],
            thresholds=Threshold(keep_improvement_pct=25.0, revert_improvement_pct=10.0),
            max_risk_tier=RiskTier.PROMPT,
            scope_in=["config", "prompt"],
            scope_out=["model_change"],
            business_context="Applies rule-set v2 to financial profiles",
            business_rule_card="registry/cards/Feature_X_v2.md",
            business_rule_card_confirmed=True,
        )
        fields.update(overrides)
        return OptimizationBrief(**fields)

    def test_gate_1_validation_pass(self):
        brief = self.make_brief()
        is_passed, errors = Gate1Evaluator.validate(brief)
        self.assertTrue(is_passed)
        self.assertEqual(len(errors), 0)

    def test_gate_1_rejects_missing_measurement_source(self):
        brief = self.make_brief(
            optimization_targets=[
                OptimizationTarget(metric_name="latency_ms", unit="ms", direction="decrease", target_value=25000.0)
            ]
        )
        is_passed, errors = Gate1Evaluator.validate(brief)
        self.assertFalse(is_passed)
        self.assertTrue(any(e.startswith("A1-V2") for e in errors))

    def test_gate_1_rejects_keep_threshold_not_above_revert(self):
        brief = self.make_brief(thresholds=Threshold(keep_improvement_pct=5.0, revert_improvement_pct=10.0))
        is_passed, errors = Gate1Evaluator.validate(brief)
        self.assertFalse(is_passed)
        self.assertTrue(any(e.startswith("A1-V4") for e in errors))

    def test_gate_1_rejects_unconfirmed_business_rule_card(self):
        brief = self.make_brief(business_rule_card_confirmed=False)
        is_passed, errors = Gate1Evaluator.validate(brief)
        self.assertFalse(is_passed)
        self.assertTrue(any(e.startswith("A1-V6") for e in errors))

    def test_gate_1_rejects_conflicting_objectives_without_priority(self):
        brief = self.make_brief(
            optimization_targets=[
                OptimizationTarget(
                    metric_name="latency_ms", unit="ms", direction="decrease",
                    target_value=25000.0, measurement_source="loki:latency", priority=1
                ),
                OptimizationTarget(
                    metric_name="latency_ms", unit="ms", direction="increase",
                    target_value=1000.0, measurement_source="loki:latency", priority=1
                ),
            ]
        )
        is_passed, errors = Gate1Evaluator.validate(brief)
        self.assertFalse(is_passed)
        self.assertTrue(any(e.startswith("A1-V5") for e in errors))

    def test_gate_2_validation_weak_baseline(self):
        baseline = BaselineReport(
            snapshot_id="S-001",
            feature_id="Feature_X_v2",
            fingerprint="Feature_X_v2_subflow6_prod",
            time_window_start="2026-10-01T00:00:00Z",
            time_window_end="2026-10-08T00:00:00Z",
            sample_count=15,  # Below required 30
            total_p50_latency_ms=40000.0,
            total_p90_latency_ms=48000.0,
            total_p99_latency_ms=55000.0,
            step_breakdowns=[],
            active_configs={"STEP3_MAX_STEPS": "6"},
        )
        is_passed, logs = Gate2Evaluator.validate(baseline)
        self.assertTrue(is_passed)
        self.assertTrue(baseline.is_weak_baseline)
        self.assertTrue(any("below min_runs" in log for log in logs))

    def test_gate_2_rejects_fingerprint_mismatch(self):
        baseline = BaselineReport(
            snapshot_id="S-002",
            feature_id="Feature_X_v2",
            fingerprint="Feature_X_v2_subflow6_prod",
            fingerprint_mismatch_count=3,
            time_window_start="2026-10-01T00:00:00Z",
            time_window_end="2026-10-08T00:00:00Z",
            sample_count=45,
            total_p50_latency_ms=40000.0,
            total_p90_latency_ms=48000.0,
            total_p99_latency_ms=55000.0,
            step_breakdowns=[],
            active_configs={"STEP3_MAX_STEPS": "6"},
        )
        is_passed, logs = Gate2Evaluator.validate(baseline)
        self.assertFalse(is_passed)
        self.assertTrue(any(log.startswith("A2-V1 Failed") for log in logs))

    def test_gate_2_rejects_unexplained_config_mismatch(self):
        baseline = BaselineReport(
            snapshot_id="S-003",
            feature_id="Feature_X_v2",
            time_window_start="2026-10-01T00:00:00Z",
            time_window_end="2026-10-08T00:00:00Z",
            sample_count=45,
            total_p50_latency_ms=40000.0,
            total_p90_latency_ms=48000.0,
            total_p99_latency_ms=55000.0,
            step_breakdowns=[],
            active_configs={"STEP3_MAX_STEPS": "6"},
            config_mismatch=["STEP3_SUBFLOW_MAX_STEPS code=6 log=3"],
        )
        is_passed, logs = Gate2Evaluator.validate(baseline)
        self.assertFalse(is_passed)
        self.assertTrue(any(log.startswith("A2-V4 Failed") for log in logs))

    def test_gate_2_rejects_config_change_inside_window(self):
        baseline = BaselineReport(
            snapshot_id="S-004",
            feature_id="Feature_X_v2",
            time_window_start="2026-10-01T00:00:00Z",
            time_window_end="2026-10-08T00:00:00Z",
            sample_count=45,
            total_p50_latency_ms=40000.0,
            total_p90_latency_ms=48000.0,
            total_p99_latency_ms=55000.0,
            step_breakdowns=[],
            active_configs={"STEP3_MAX_STEPS": "6"},
            config_change_in_window=True,
        )
        is_passed, logs = Gate2Evaluator.validate(baseline)
        self.assertFalse(is_passed)
        self.assertTrue(any(log.startswith("A2-V6 Failed") for log in logs))

    def test_gate_3_rejects_multi_variable_change(self):
        solution = self.make_solution(variables=["STEP3_SUBFLOW_MAX_STEPS", "PROMPT_TEMPLATE"])
        is_passed, errors = Gate3Evaluator.validate(solution)
        self.assertFalse(is_passed)
        self.assertTrue(any(e.startswith("A3-V5") for e in errors))

    @staticmethod
    def make_solution(variables=None) -> SolutionProposal:
        return SolutionProposal(
            solution_id="SOL-9001",
            feature_id="Feature_X_v2_subflow6_prod",
            verified_root_cause=VerifiedRootCause(
                statement="Step 3 subflow runs all 6 steps although 70% of runs converge earlier",
                evidence_log_lines=["log_402"],
            ),
            proposed_change="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            risk_tier=RiskTier.CONFIG,
            blast_radius="step3",
            pros=["Latency down 10-20%"],
            cons=["Runs needing > 3 steps may be truncated"],
            pros_cons=[
                ProsCons(criterion="latency_p50_ms", pros="-10% to -20%", cons="none"),
                ProsCons(criterion="quality_score", pros="unchanged", cons="risk if steps too few"),
            ],
            expected_impact_range="-10% to -20%",
            effort_estimate="Small",
            retest_plan="Compare to S-0012, same fingerprint, 7 days, min 30 runs",
            rollback_plan="Revert STEP3_SUBFLOW_MAX_STEPS to 6",
            confidence_score=0.9,
            change=ChangeDescription(
                description="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
                variables=variables or ["STEP3_SUBFLOW_MAX_STEPS"],
            ),
        )

    def test_gate_3_passes_for_single_variable_verified_solution(self):
        is_passed, errors = Gate3Evaluator.validate(self.make_solution())
        self.assertTrue(is_passed, errors)

    def test_verification_engine_keep_decision(self):
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-001",
            snapshot_before="S-001",
            snapshot_after="S-002",
            baseline_p50=40000.0,
            retest_p50=25000.0,  # 37.5% improvement >= 25% KEEP
            validity=build_validity(),
        )
        self.assertEqual(res.decision, VerificationDecision.KEEP)
        self.assertEqual(res.improvement_pct, 37.5)

    def test_verification_engine_invalid_when_fingerprint_differs(self):
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-001",
            snapshot_before="S-001",
            snapshot_after="S-002",
            baseline_p50=40000.0,
            retest_p50=25000.0,
            validity=build_validity(v1_same_fingerprint=False),
        )
        self.assertEqual(res.decision, VerificationDecision.INVALID)

    def test_verification_engine_revert_on_guardrail_breach(self):
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-001",
            snapshot_before="S-001",
            snapshot_after="S-002",
            baseline_p50=40000.0,
            retest_p50=20000.0,
            validity=build_validity(),
            guardrail_breached=True,
        )
        self.assertEqual(res.decision, VerificationDecision.REVERT)

    def test_verification_engine_partial_below_keep_threshold(self):
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-001",
            snapshot_before="S-001",
            snapshot_after="S-002",
            baseline_p50=40000.0,
            retest_p50=34000.0,  # 15% improvement -> PARTIAL
            validity=build_validity(),
        )
        self.assertEqual(res.decision, VerificationDecision.PARTIAL)


if __name__ == "__main__":
    unittest.main()
