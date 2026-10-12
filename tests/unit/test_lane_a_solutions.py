import os
import shutil
import unittest

from src.core.schemas.brief import RiskTier
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause, ChangeDescription, ProsCons
from src.core.storage.file_store import FileStore
from src.modules.lane_a.domain.lane_a_service import LaneAService

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_lane_a")


def make_solution(solution_id, risk_tier, effort="Small", hypothesis=False, variables=None):
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
            blast_radius="step3",
        ),
        risk_tier=risk_tier,
        blast_radius="step3",
        pros=["Latency -10% to -20%"],
        cons=["Truncation risk"],
        pros_cons=[ProsCons(criterion="latency_p50_ms", pros="-10% to -20%", cons="none")],
        expected_impact_range="-10% to -20%",
        effort_estimate=effort,
        retest_plan="Compare to S-0001, 7 days, min 30 runs",
        rollback_plan="Revert to 6",
        confidence_score=0.9,
        is_unverified_hypothesis=hypothesis,
    )


class TestLaneASolutions(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(BASE_DIR, exist_ok=True)
        self.service = LaneAService(file_store=FileStore(base_dir=BASE_DIR))

    def tearDown(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR, ignore_errors=True)

    def test_order_solutions_by_risk_tier_then_effort(self):
        proposals = [
            make_solution("SOL-CODE", RiskTier.CODE, effort="L"),
            make_solution("SOL-CONFIG-L", RiskTier.CONFIG, effort="L"),
            make_solution("SOL-CONFIG-S", RiskTier.CONFIG, effort="S"),
            make_solution("SOL-PROMPT", RiskTier.PROMPT, effort="M"),
        ]
        main, hypotheses = self.service.order_solutions(proposals)
        self.assertEqual(hypotheses, [])
        # A3-R7: config -> prompt -> code; effort breaks ties
        self.assertEqual(
            [p.solution_id for p in main],
            ["SOL-CONFIG-S", "SOL-CONFIG-L", "SOL-PROMPT", "SOL-CODE"],
        )

    def test_order_solutions_separates_hypotheses(self):
        verified = make_solution("SOL-OK", RiskTier.CODE)
        hypothesis = make_solution("SOL-GUESS", RiskTier.CONFIG, hypothesis=True)
        main, hypotheses = self.service.order_solutions([hypothesis, verified])
        self.assertEqual([p.solution_id for p in main], ["SOL-OK"])
        self.assertEqual([p.solution_id for p in hypotheses], ["SOL-GUESS"])

    def test_gate_3_blocks_multi_variable_solution_before_persisting(self):
        proposal = make_solution("SOL-BAD", RiskTier.CONFIG, variables=["STEP3_SUBFLOW_MAX_STEPS", "PROMPT"])
        passed, errors = self.service.build_solution_proposal(proposal)
        self.assertFalse(passed)
        self.assertTrue(any(e.startswith("A3-V5") for e in errors))
        self.assertFalse(os.path.exists(os.path.join(BASE_DIR, "solutions", "SOL-BAD.json")))

    def test_valid_solution_is_persisted(self):
        proposal = make_solution("SOL-OK", RiskTier.CONFIG)
        passed, errors = self.service.build_solution_proposal(proposal)
        self.assertTrue(passed, errors)
        self.assertTrue(os.path.exists(os.path.join(BASE_DIR, "solutions", "SOL-OK.json")))


if __name__ == "__main__":
    unittest.main()
