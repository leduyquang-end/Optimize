import unittest
from src.core.schemas.fingerprint import Fingerprint
from src.core.schemas.brief import OptimizationBrief, OptimizationTarget, Guardrail, Threshold, RiskTier
from src.core.schemas.baseline import BaselineReport, StepBreakdown
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause, ProsCons
from src.core.schemas.measurement import ValidityCheckResult
from src.core.schemas.policy import SystemPolicy, RiskTier as PolicyRiskTier
from src.modules.lane_a.gates.gate_1 import Gate1Evaluator
from src.modules.lane_a.gates.gate_2 import Gate2Evaluator
from src.modules.lane_a.gates.gate_3 import Gate3Evaluator
from src.modules.lane_b.domain.proposer_service import SelfCriticismEngine
from src.modules.section_2.domain.reranker_service import RerankerService
from src.modules.section_2.domain.verification_service import VerificationEngine, VerificationDecision

class TestFullArchitecture(unittest.TestCase):
    def test_fingerprint_hashing(self):
        fp1 = Fingerprint(feature="Feature_X", rule_set="v2", rule_variant="varA", subflow_steps=6)
        fp2 = Fingerprint(feature="Feature_X", rule_set="v2", rule_variant="varA", subflow_steps=6)
        fp3 = Fingerprint(feature="Feature_X", rule_set="v2", rule_variant="varB", subflow_steps=6)

        self.assertEqual(fp1.compute_hash(), fp2.compute_hash())
        self.assertNotEqual(fp1.compute_hash(), fp3.compute_hash())

    def test_gate_1_intake_validation(self):
        brief = OptimizationBrief(
            feature_id="Feature_X_v2_subflow6_prod",
            optimization_targets=[
                OptimizationTarget(
                    metric_name="latency_p50_ms", unit="ms", direction="decrease",
                    target_value=25000.0,
                    measurement_source="Loki: quantile_over_time(0.5, {feature=Feature_X_v2} | unwrap duration_ms)",
                )
            ],
            guardrails=[
                Guardrail(metric_name="quality_score", max_allowed_change_pct=0.0)
            ],
            thresholds=Threshold(keep_improvement_pct=25.0, revert_improvement_pct=10.0),
            max_risk_tier=RiskTier.PROMPT,
            scope_in=["step3"],
            scope_out=["model_change"],
            business_context="Financial profile subflow 6",
            business_rule_card="registry/cards/Feature_X_v2.md",
            business_rule_card_confirmed=True
        )
        is_passed, errors = Gate1Evaluator.validate(brief)
        self.assertTrue(is_passed)
        self.assertEqual(len(errors), 0)

    def test_gate_2_baseline_validation(self):
        baseline = BaselineReport(
            snapshot_id="S-0012",
            feature_id="Feature_X_v2_subflow6_prod",
            time_window_start="2026-10-01T00:00:00Z",
            time_window_end="2026-10-08T00:00:00Z",
            sample_count=45,
            total_p50_latency_ms=40000.0,
            total_p90_latency_ms=48000.0,
            total_p99_latency_ms=55000.0,
            step_breakdowns=[
                StepBreakdown(step_name="step3", pct_of_total_time=48.0, p50_latency_ms=19200.0, p90_latency_ms=23000.0, p99_latency_ms=26000.0, is_critical_path=True)
            ],
            active_configs={"STEP3_SUBFLOW_MAX_STEPS": "6"}
        )
        is_passed, logs = Gate2Evaluator.validate(baseline)
        self.assertTrue(is_passed)
        self.assertFalse(baseline.is_weak_baseline)

    def test_gate_3_solution_validation(self):
        sol = SolutionProposal(
            solution_id="SOL-0123",
            feature_id="Feature_X_v2_subflow6_prod",
            verified_root_cause=VerifiedRootCause(
                statement="Step 3 subflow executes all 6 steps despite 70% runs converging at step 3",
                evidence_log_lines=["log_line_1024"]
            ),
            proposed_change="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            risk_tier=RiskTier.CONFIG,
            blast_radius="step3 subflow only",
            pros=["Decrease latency and token usage"],
            cons=["30% runs needing > 3 steps might be truncated"],
            pros_cons=[
                ProsCons(criterion="latency_p50_ms", pros="-10% to -20%", cons="none"),
                ProsCons(criterion="quality_score", pros="unchanged", cons="risk of truncation"),
            ],
            expected_impact_range="-10% to -20% latency",
            effort_estimate="Small",
            retest_plan="Same fingerprint, compare to S-0012",
            rollback_plan="Revert config to 6",
            confidence_score=0.9
        )
        is_passed, errors = Gate3Evaluator.validate(sol)
        self.assertTrue(is_passed)

    def test_lane_b_self_criticism_pass(self):
        policy = SystemPolicy(effective_from="2026-10-01T00:00:00Z", approved_by="Program Owner", max_risk_tier=PolicyRiskTier.CONFIG)
        sol = SolutionProposal(
            solution_id="SOL-0124",
            feature_id="Feature_X_v2_subflow6_prod",
            verified_root_cause=VerifiedRootCause(
                statement="Validated via Loki log line 402",
                evidence_log_lines=["log_402"],
            ),
            proposed_change="STEP3_MAX_STEPS 6 -> 3",
            risk_tier=RiskTier.CONFIG,
            blast_radius="step3",
            pros=["Pros text"], cons=["Cons text"],
            expected_impact_range="-15% to -20%", effort_estimate="Small",
            retest_plan="Compare to S-0012", rollback_plan="Revert to 6", confidence_score=0.85
        )
        is_passed, rejections = SelfCriticismEngine.audit_proposal(sol, policy)
        self.assertTrue(is_passed)
        self.assertEqual(len(rejections), 0)

    def test_section_2_reranker_decision_mode(self):
        sol_config = SolutionProposal(
            solution_id="SOL-01", feature_id="F1",
            verified_root_cause=VerifiedRootCause(statement="Cause 1"), proposed_change="C1",
            risk_tier=RiskTier.CONFIG, blast_radius="Narrow", pros=["P"], cons=["C"],
            expected_impact_range="-15%", effort_estimate="S", retest_plan="R", rollback_plan="RB", confidence_score=0.9
        )
        mode = RerankerService.determine_decision_mode(sol_config)
        self.assertEqual(mode, "auto_rerank_notify")

    def test_section_2_verification_validity_check_fail(self):
        validity = ValidityCheckResult(
            v1_same_fingerprint=False,  # Failed V-1
            v2_same_business_complexity=True,
            v3_equivalent_conditions=True,
            v4_sufficient_sample_size=True,
            v5_single_variable_diff=True,
            v6_distribution_provided=True
        )
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-01", snapshot_before="S-0012", snapshot_after="S-0019",
            baseline_p50=40000.0, retest_p50=25000.0, validity=validity
        )
        self.assertEqual(res.decision, VerificationDecision.INVALID)
        self.assertIn("INVALID", res.reasoning)

    def test_section_2_verification_keep_decision(self):
        validity = ValidityCheckResult(
            v1_same_fingerprint=True, v2_same_business_complexity=True,
            v3_equivalent_conditions=True, v4_sufficient_sample_size=True,
            v5_single_variable_diff=True, v6_distribution_provided=True
        )
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-01", snapshot_before="S-0012", snapshot_after="S-0019",
            baseline_p50=40000.0, retest_p50=25000.0, validity=validity # 37.5% improvement >= 25% KEEP
        )
        self.assertEqual(res.decision, VerificationDecision.KEEP)
        self.assertEqual(res.improvement_pct, 37.5)

    def test_section_2_verification_revert_on_guardrail_breach(self):
        validity = ValidityCheckResult(
            v1_same_fingerprint=True, v2_same_business_complexity=True,
            v3_equivalent_conditions=True, v4_sufficient_sample_size=True,
            v5_single_variable_diff=True, v6_distribution_provided=True
        )
        res = VerificationEngine.evaluate_retest(
            solution_id="SOL-01", snapshot_before="S-0012", snapshot_after="S-0019",
            baseline_p50=40000.0, retest_p50=20000.0, validity=validity, guardrail_breached=True
        )
        self.assertEqual(res.decision, VerificationDecision.REVERT)

if __name__ == "__main__":
    unittest.main()
