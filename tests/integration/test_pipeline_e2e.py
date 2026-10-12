import unittest
import os
import shutil
from src.core.schemas.brief import OptimizationBrief, OptimizationTarget, Guardrail, Threshold, RiskTier
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause, ChangeDescription, ProsCons
from src.core.schemas.measurement import ValidityCheckResult
from src.core.storage.file_store import FileStore
from src.modules.lane_a.domain.lane_a_service import LaneAService
from src.modules.lane_b.domain.scanner_service import ScannerService, CandidateBottleneck, KillSwitchManager
from src.modules.section_2.domain.execution_flow import Section2WorkflowOrchestrator
from src.modules.section_2.domain.verification_service import VerificationDecision

class TestE2EPipeline(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_optimization_data"
        self.file_store = FileStore(base_dir=self.test_dir)
        self.lane_a_service = LaneAService(file_store=self.file_store)
        self.orchestrator = Section2WorkflowOrchestrator(file_store=self.file_store)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_full_optimization_lifecycle(self):
        # 1. A1 Intake Brief
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
            business_context="Financial profile evaluation",
            business_rule_card="registry/cards/Feature_X_v2.md",
            business_rule_card_confirmed=True
        )
        is_passed, errors = self.lane_a_service.process_intake_brief(brief)
        self.assertTrue(is_passed)

        # 2. A2 Baseline Report & Snapshot
        raw_logs = [
            {"latency_ms": 40000.0, "status": "success"},
            {"latency_ms": 42000.0, "status": "success"},
            {"latency_ms": 39000.0, "status": "success"}
        ]
        report, is_passed, gate_logs = self.lane_a_service.generate_baseline_report(
            snapshot_id="S-0012",
            feature_id="Feature_X_v2_subflow6_prod",
            raw_log_runs=raw_logs,
            active_configs={"STEP3_SUBFLOW_MAX_STEPS": "6"},
            time_window_start="2026-10-01T00:00:00Z",
            time_window_end="2026-10-08T00:00:00Z"
        )
        self.assertTrue(is_passed)
        self.assertEqual(report.total_p50_latency_ms, 40000.0)

        # 3. A3 Solution Proposal
        proposal = SolutionProposal(
            solution_id="SOL-0123",
            feature_id="Feature_X_v2_subflow6_prod",
            snapshot_id="S-0012",
            verified_root_cause=VerifiedRootCause(
                statement="Step 3 subflow executes 6 steps despite early convergence",
                evidence_log_lines=["log_402"]
            ),
            proposed_change="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            change=ChangeDescription(description="STEP3_SUBFLOW_MAX_STEPS 6 -> 3", variables=["STEP3_SUBFLOW_MAX_STEPS"]),
            risk_tier=RiskTier.CONFIG,
            blast_radius="step3",
            pros=["Latency -20%"],
            cons=["Quality might drop if > 3 steps needed"],
            pros_cons=[
                ProsCons(criterion="latency_p50_ms", pros="-10% to -20%", cons="none"),
                ProsCons(criterion="quality_score", pros="unchanged", cons="risk if steps too few"),
            ],
            expected_impact_range="-10% to -20%",
            effort_estimate="Small",
            retest_plan="Compare to S-0012",
            rollback_plan="Revert to 6",
            confidence_score=0.9
        )
        is_passed, errors = self.lane_a_service.build_solution_proposal(proposal)
        self.assertTrue(is_passed)

        # 4. §2 Step 01 & Step 02 (Re-rank & Plan)
        ranked, excluded = self.orchestrator.step_01_rerank([proposal])
        self.assertEqual(len(ranked), 1)

        plan = self.orchestrator.step_02_create_plan(proposal)
        self.assertEqual(len(plan.phases), 1)

        # 5. §2 Step 05 & 06 (Retest & Decision Engine)
        validity = ValidityCheckResult(
            v1_same_fingerprint=True,
            v2_same_business_complexity=True,
            v3_equivalent_conditions=True,
            v4_sufficient_sample_size=True,
            v5_single_variable_diff=True,
            v6_distribution_provided=True
        )
        result = self.orchestrator.step_05_and_06_measure_and_decide(
            solution_id="SOL-0123",
            snapshot_before="S-0012",
            snapshot_after="S-0019",
            baseline_p50=40000.0,
            retest_p50=25000.0, # 37.5% improvement >= 25% KEEP
            validity=validity
        )

        self.assertEqual(result.decision, VerificationDecision.KEEP)
        self.assertEqual(result.improvement_pct, 37.5)

        # Verify Lesson recorded in lessons.jsonl
        lessons_path = os.path.join(self.test_dir, "lessons", "lessons.jsonl")
        self.assertTrue(os.path.exists(lessons_path))
        with open(lessons_path, "r", encoding="utf-8") as f:
            self.assertIn("SOL-0123", f.read())

        # Measurement report (Step 05) must be persisted with an ID
        measurement_files = os.listdir(os.path.join(self.test_dir, "measurements"))
        self.assertEqual(len(measurement_files), 1)

        # 6. §2 Step 07 (Report) and Step 08 (Rollout plan)
        report = self.orchestrator.step_07_generate_report("SOL-0123", result)
        self.assertIn("### Xong thật", report)
        self.assertIn("### Còn thiếu", report)
        report_files = os.listdir(os.path.join(self.test_dir, "reports"))
        self.assertEqual(len(report_files), 1)
        self.assertTrue(report_files[0].startswith("R-"))

        rollout = self.orchestrator.step_08_rollout_plan(proposal)
        self.assertEqual(len(rollout), 3)
        self.assertTrue(all(stage["rollback"] for stage in rollout))

if __name__ == "__main__":
    unittest.main()
