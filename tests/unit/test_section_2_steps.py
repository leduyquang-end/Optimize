import os
import shutil
import unittest

from src.core.schemas.brief import RiskTier
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause, ChangeDescription, ProsCons
from src.core.storage.file_store import FileStore
from src.modules.section_2.domain.execution_flow import Section2WorkflowOrchestrator
from src.modules.section_2.domain.reranker_service import RerankerService

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_section2")


def make_solution(
    solution_id: str,
    risk_tier=RiskTier.CONFIG,
    impact="-10% to -20%",
    blast_radius="step3",
    confidence=0.9,
    effort="Small",
    conflicts_with=None,
    guardrail_tradeoffs=None,
    variables=None,
    hypothesis=False,
    over_ceiling=False,
) -> SolutionProposal:
    return SolutionProposal(
        solution_id=solution_id,
        feature_id="Feature_X_v2_subflow6_prod",
        snapshot_id="S-0001",
        verified_root_cause=VerifiedRootCause(
            statement="Step 3 runs all steps although most runs converge earlier",
            evidence_log_lines=["log_402"],
        ),
        proposed_change="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
        change=ChangeDescription(
            description="STEP3_SUBFLOW_MAX_STEPS 6 -> 3",
            variables=variables or ["STEP3_SUBFLOW_MAX_STEPS"],
            risk_tier=risk_tier,
            blast_radius=blast_radius,
        ),
        risk_tier=risk_tier,
        blast_radius=blast_radius,
        pros=["Latency down"],
        cons=["Truncation risk"],
        pros_cons=[ProsCons(criterion="latency_p50_ms", pros=impact, cons="none")],
        expected_impact_range=impact,
        effort_estimate=effort,
        retest_plan="Compare to S-0001, 7 days, min 30 runs",
        rollback_plan="Revert to 6",
        confidence_score=confidence,
        conflicts_with=conflicts_with or [],
        guardrail_tradeoffs=guardrail_tradeoffs or [],
        is_unverified_hypothesis=hypothesis,
        over_ceiling=over_ceiling,
    )


class TestReranker(unittest.TestCase):
    def test_decision_mode_config_narrow_instant_rollback(self):
        mode = RerankerService.determine_decision_mode(make_solution("SOL-1"))
        self.assertEqual(mode, "auto_rerank_notify")

    def test_decision_mode_prompt_is_human_pick(self):
        mode = RerankerService.determine_decision_mode(make_solution("SOL-1", risk_tier=RiskTier.PROMPT))
        self.assertEqual(mode, "auto_rerank_human_pick")

    def test_decision_mode_code_is_human_decides(self):
        mode = RerankerService.determine_decision_mode(make_solution("SOL-1", risk_tier=RiskTier.CODE))
        self.assertEqual(mode, "human_decides")

    def test_decision_mode_low_confidence_is_human_decides(self):
        mode = RerankerService.determine_decision_mode(make_solution("SOL-1", confidence=0.4))
        self.assertEqual(mode, "human_decides")

    def test_rerank_excludes_ceiling_guardrail_and_hypothesis(self):
        proposals = [
            make_solution("SOL-OK"),
            make_solution("SOL-CEIL", over_ceiling=True),
            make_solution("SOL-GR", guardrail_tradeoffs=["quality_score drops"]),
            make_solution("SOL-HYP", hypothesis=True),
        ]
        ranked, excluded = RerankerService.rerank_solutions(proposals)
        self.assertEqual([p.solution_id for p in ranked], ["SOL-OK"])
        self.assertEqual(len(excluded), 3)
        self.assertTrue(all(e["reason"] for e in excluded))  # S01-R3: reasons recorded

    def test_rerank_excludes_conflicting_pair(self):
        proposals = [
            make_solution("SOL-A", conflicts_with=["SOL-B"]),
            make_solution("SOL-B", impact="-15% to -25%"),  # higher conservative impact, ranked first
        ]
        ranked, excluded = RerankerService.rerank_solutions(proposals)
        ids = [p.solution_id for p in ranked]
        self.assertEqual(ids, ["SOL-B"])
        self.assertEqual([e["id"] for e in excluded], ["SOL-A"])
        self.assertIn("S01-R4", excluded[0]["reason"])

    def test_rerank_orders_by_conservative_impact_then_risk(self):
        proposals = [
            make_solution("SOL-CODE", risk_tier=RiskTier.CODE, impact="-40% to -50%"),
            make_solution("SOL-SMALL", impact="-5% to -8%"),
            make_solution("SOL-BIG", impact="-15% to -25%"),
        ]
        ranked, excluded = RerankerService.rerank_solutions(proposals)
        self.assertEqual(excluded, [])
        # S01-R1: order by the conservative bound of the priority criterion first,
        # risk tier only breaks ties
        self.assertEqual([p.solution_id for p in ranked], ["SOL-CODE", "SOL-BIG", "SOL-SMALL"])

    def test_rerank_uses_risk_tier_as_tie_breaker(self):
        proposals = [
            make_solution("SOL-CODE-TIE", risk_tier=RiskTier.CODE, impact="-10% to -20%"),
            make_solution("SOL-CONFIG-TIE", risk_tier=RiskTier.CONFIG, impact="-10% to -20%"),
        ]
        ranked, _ = RerankerService.rerank_solutions(proposals)
        self.assertEqual([p.solution_id for p in ranked], ["SOL-CONFIG-TIE", "SOL-CODE-TIE"])


class TestPlanPhases(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(BASE_DIR, exist_ok=True)
        self.orchestrator = Section2WorkflowOrchestrator(file_store=FileStore(base_dir=BASE_DIR))

    def tearDown(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR, ignore_errors=True)

    def test_multi_phase_plan_ordered_by_risk_with_dependencies(self):
        solutions = [
            make_solution("SOL-CODE", risk_tier=RiskTier.CODE, variables=["parallel_executor"]),
            make_solution("SOL-PROMPT", risk_tier=RiskTier.PROMPT, variables=["PROMPT_TEMPLATE"]),
            make_solution("SOL-CONFIG", risk_tier=RiskTier.CONFIG, variables=["STEP3_SUBFLOW_MAX_STEPS"]),
        ]
        plan = self.orchestrator.step_02_create_multi_phase_plan(solutions, owner="khoa")

        self.assertEqual(len(plan.phases), 3)
        self.assertEqual([p.risk_tier for p in plan.phases], [RiskTier.CONFIG, RiskTier.PROMPT, RiskTier.CODE])
        self.assertEqual(len({p.change_variable for p in plan.phases}), 3)  # S02-R3: one variable each

        # S02-R4: dependencies chain phase by phase
        self.assertEqual(plan.phases[0].depends_on, [])
        self.assertEqual(plan.phases[1].depends_on, [plan.phases[0].phase_id])
        self.assertEqual(plan.phases[2].depends_on, [plan.phases[1].phase_id])

        # S02-R1/R2: every phase has numeric done criteria, tests, remeasure, rollback
        for phase in plan.phases:
            self.assertIn(">=", phase.done_criteria)
            self.assertTrue(phase.tests)
            self.assertTrue(phase.remeasure_compare_to)
            self.assertGreater(phase.remeasure_window_days, 0)
            self.assertGreaterEqual(phase.remeasure_min_runs, 1)
            self.assertTrue(phase.rollback_action)
            self.assertEqual(phase.rollback_owner, "khoa")

        saved = os.path.join(BASE_DIR, "plans", f"{plan.solution_id}-plan.json")
        self.assertTrue(os.path.exists(saved))

    def test_single_phase_plan_keeps_solution_id(self):
        plan = self.orchestrator.step_02_create_multi_phase_plan([make_solution("SOL-1")])
        self.assertEqual(plan.solution_id, "SOL-1")
        self.assertEqual(len(plan.phases), 1)


if __name__ == "__main__":
    unittest.main()
