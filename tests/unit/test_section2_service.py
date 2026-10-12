import json
import os
import shutil
import unittest

from src.core.schemas.brief import RiskTier
from src.core.schemas.solution import (
    SolutionProposal,
    SolutionStatus,
    VerifiedRootCause,
    ChangeDescription,
    can_transition,
    SOLUTION_TRANSITIONS,
)
from src.core.schemas.measurement import ValidityCheckResult
from src.core.storage.file_store import FileStore
from src.modules.section_2.section2_service import Section2Service, TransitionError

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_section2_svc")


def make_solution(solution_id: str, **kw) -> SolutionProposal:
    return SolutionProposal(
        solution_id=solution_id,
        feature_id="Feature_X_v2",
        snapshot_id="S-0001",
        verified_root_cause=VerifiedRootCause(statement="root"),
        proposed_change="change X",
        change=ChangeDescription(description="X 1->2", variables=["X"]),
        risk_tier=kw.get("risk_tier", RiskTier.CONFIG),
        expected_impact_range=kw.get("impact", "-30% to -40%"),
        effort_estimate=kw.get("effort", "Small"),
        confidence_score=kw.get("confidence", 0.9),
        rollback_plan="revert",
        is_unverified_hypothesis=kw.get("hypothesis", False),
        over_ceiling=kw.get("over_ceiling", False),
    )


class TestStateMachine(unittest.TestCase):
    def test_valid_transitions(self):
        self.assertTrue(can_transition("proposed", "ranked"))
        self.assertTrue(can_transition("ranked", "planned"))
        self.assertTrue(can_transition("planned", "implementing"))
        self.assertTrue(can_transition("decided", "kept"))
        self.assertTrue(can_transition("decided", "reverted"))

    def test_invalid_transitions(self):
        self.assertFalse(can_transition("proposed", "done"))
        self.assertFalse(can_transition("planned", "done"))
        self.assertFalse(can_transition("kept", "reverted"))
        self.assertFalse(can_transition("done", "anything"))

    def test_all_status_values_have_entry(self):
        for status in SolutionStatus:
            self.assertIn(status.value, SOLUTION_TRANSITIONS)


class TestSection2Service(unittest.TestCase):
    def setUp(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR)
        os.makedirs(BASE_DIR)
        self.svc = Section2Service(BASE_DIR)
        self.store = FileStore(BASE_DIR)
        # seed 2 solutions + 1 hypothesis
        for sid in ("SOL-0001", "SOL-0002"):
            self.store.save_solution(sid, make_solution(sid).model_dump(mode="json"))
        self.store.save_json("hypotheses", "HYP-0001", make_solution("HYP-0001", hypothesis=True).model_dump(mode="json"))

    def tearDown(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR)

    def test_list_solutions_includes_solutions_and_hypotheses(self):
        sols = self.svc.list_solutions()
        ids = [s.solution_id for s in sols]
        self.assertIn("SOL-0001", ids)
        self.assertIn("SOL-0002", ids)
        self.assertIn("HYP-0001", ids)

    def test_transition_valid_and_persisted(self):
        sol = self.svc.transition("SOL-0001", "ranked", actor="test")
        self.assertEqual(sol.status, SolutionStatus.RANKED)
        # reload from disk
        reloaded = self.svc.get_solution("SOL-0001")
        self.assertEqual(reloaded.status, SolutionStatus.RANKED)
        self.assertTrue(any("proposed->ranked" in h for h in reloaded.status_history))

    def test_transition_invalid_raises(self):
        with self.assertRaises(TransitionError):
            self.svc.transition("SOL-0001", "done")

    def test_transition_missing_solution_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.svc.transition("SOL-9999", "ranked")

    def test_rerank_ranks_solutions_and_excludes_hypotheses(self):
        result = self.svc.rerank()
        ranked_ids = [s["solution_id"] for s in result["ranked"]]
        excluded_ids = [e["id"] for e in result["excluded"]]
        self.assertIn("SOL-0001", ranked_ids)
        self.assertIn("SOL-0002", ranked_ids)
        self.assertIn("HYP-0001", excluded_ids)
        # ranked solutions transitioned to ranked
        sol1 = self.svc.get_solution("SOL-0001")
        self.assertEqual(sol1.status, SolutionStatus.RANKED)

    def test_create_plan_single(self):
        self.svc.transition("SOL-0001", "ranked")
        plan = self.svc.create_plan(["SOL-0001"], owner="tester")
        self.assertEqual(plan["solution_id"], "SOL-0001")
        self.assertEqual(len(plan["phases"]), 1)
        # plan file exists
        self.assertIsNotNone(self.svc.get_plan("SOL-0001"))
        # status advanced to planned
        self.assertEqual(self.svc.get_solution("SOL-0001").status, SolutionStatus.PLANNED)

    def test_create_plan_multi(self):
        self.svc.transition("SOL-0001", "ranked")
        self.svc.transition("SOL-0002", "ranked")
        plan = self.svc.create_plan(["SOL-0001", "SOL-0002"], owner="tester")
        self.assertEqual(len(plan["phases"]), 2)
        # phases chained
        self.assertEqual(plan["phases"][1]["depends_on"], [plan["phases"][0]["phase_id"]])

    def test_create_plan_missing_solution_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.svc.create_plan(["SOL-9999"])

    def test_generate_report_keep(self):
        self.svc.transition("SOL-0001", "ranked")
        self.svc.transition("SOL-0001", "planned")
        self.svc.transition("SOL-0001", "implementing")
        self.svc.transition("SOL-0001", "testing")
        self.svc.transition("SOL-0001", "measuring")
        validity = ValidityCheckResult(
            v1_same_fingerprint=True, v2_same_business_complexity=True,
            v3_equivalent_conditions=True, v4_sufficient_sample_size=True,
            v5_single_variable_diff=True, v6_distribution_provided=True,
        )
        result = self.svc.generate_report(
            solution_id="SOL-0001",
            snapshot_before="S-0001", snapshot_after="S-0002",
            baseline_p50=1000.0, retest_p50=600.0, validity=validity,
        )
        self.assertEqual(result["retest_result"]["decision"], "KEEP")
        self.assertIn("Xong thật", result["report_markdown"])
        # status advanced to decided then kept
        sol = self.svc.get_solution("SOL-0001")
        self.assertEqual(sol.status, SolutionStatus.KEPT)

    def test_generate_report_revert(self):
        for st in ("ranked", "planned", "implementing", "testing", "measuring"):
            self.svc.transition("SOL-0002", st)
        validity = ValidityCheckResult(
            v1_same_fingerprint=True, v2_same_business_complexity=True,
            v3_equivalent_conditions=True, v4_sufficient_sample_size=True,
            v5_single_variable_diff=True, v6_distribution_provided=True,
        )
        result = self.svc.generate_report(
            solution_id="SOL-0002",
            snapshot_before="S-0001", snapshot_after="S-0003",
            baseline_p50=1000.0, retest_p50=990.0, validity=validity,
        )
        self.assertEqual(result["retest_result"]["decision"], "REVERT")
        sol = self.svc.get_solution("SOL-0002")
        self.assertEqual(sol.status, SolutionStatus.REVERTED)

    def test_list_plans_empty(self):
        self.assertEqual(self.svc.list_plans(), [])


if __name__ == "__main__":
    unittest.main()
