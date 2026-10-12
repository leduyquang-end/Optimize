import json
import os
import shutil
import unittest

from fastapi.testclient import TestClient
from app.main import app
from src.core.storage.file_store import FileStore
from src.core.schemas.solution import (
    SolutionProposal,
    VerifiedRootCause,
    ChangeDescription,
)
from src.core.schemas.brief import RiskTier

client = TestClient(app)

TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_section2_api")


def seed(store: FileStore) -> None:
    for sid in ("SOL-0001", "SOL-0002"):
        sol = SolutionProposal(
            solution_id=sid,
            feature_id="Feature_X_v2",
            snapshot_id="S-0001",
            verified_root_cause=VerifiedRootCause(statement="root"),
            proposed_change="change",
            change=ChangeDescription(description="X", variables=["X"]),
            risk_tier=RiskTier.CONFIG,
            expected_impact_range="-30% to -40%",
            rollback_plan="revert",
        )
        store.save_solution(sid, sol.model_dump(mode="json"))


class TestSection2API(unittest.TestCase):
    def setUp(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP)
        os.makedirs(TMP)
        seed(FileStore(TMP))

    def tearDown(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP)

    def _get(self, path, **params):
        params.setdefault("base_dir", TMP)
        return client.get(path, params=params)

    def _post(self, path, **json_body):
        json_body.setdefault("base_dir", TMP)
        return client.post(path, json=json_body)

    def test_list_solutions(self):
        r = self._get("/api/v1/section-2/solutions")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        ids = [s["solution_id"] for s in d["solutions"]]
        self.assertIn("SOL-0001", ids)
        self.assertIn("SOL-0002", ids)
        self.assertIn("proposed", d["status_transitions"])

    def test_rerank(self):
        r = self._post("/api/v1/section-2/rerank")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        ranked = [s["solution_id"] for s in d["ranked"]]
        self.assertIn("SOL-0001", ranked)
        self.assertIn("SOL-0002", ranked)

    def test_create_plan_and_list(self):
        self._post("/api/v1/section-2/rerank")
        r = self._post("/api/v1/section-2/plan", solution_ids=["SOL-0001"], owner="tester")
        self.assertEqual(r.status_code, 200)
        plan = r.json()
        self.assertEqual(plan["solution_id"], "SOL-0001")
        self.assertEqual(len(plan["phases"]), 1)

        r2 = self._get("/api/v1/section-2/plans")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(len(r2.json()["plans"]), 1)

        r3 = self._get("/api/v1/section-2/plans/SOL-0001")
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.json()["solution_id"], "SOL-0001")

    def test_get_plan_not_found(self):
        r = self._get("/api/v1/section-2/plans/SOL-9999")
        self.assertEqual(r.status_code, 404)

    def test_transition_valid(self):
        r = self._post("/api/v1/section-2/solutions/SOL-0001/status", status="ranked", actor="test")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ranked")

    def test_transition_invalid_422(self):
        r = self._post("/api/v1/section-2/solutions/SOL-0001/status", status="done")
        self.assertEqual(r.status_code, 422)
        self.assertIn("không được chuyển", r.json()["detail"]["error"])

    def test_transition_not_found_404(self):
        r = self._post("/api/v1/section-2/solutions/SOL-9999/status", status="ranked")
        self.assertEqual(r.status_code, 404)

    def test_report_keep(self):
        # advance to measuring
        for st in ("ranked", "planned", "implementing", "testing", "measuring"):
            r = self._post("/api/v1/section-2/solutions/SOL-0001/status", status=st)
            self.assertEqual(r.status_code, 200, r.text)
        r = self._post(
            "/api/v1/section-2/report",
            solution_id="SOL-0001",
            snapshot_before="S-0001",
            snapshot_after="S-0002",
            baseline_p50=1000.0,
            retest_p50=600.0,
            validity={
                "v1_same_fingerprint": True,
                "v2_same_business_complexity": True,
                "v3_equivalent_conditions": True,
                "v4_sufficient_sample_size": True,
                "v5_single_variable_diff": True,
                "v6_distribution_provided": True,
            },
        )
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["retest_result"]["decision"], "KEEP")
        self.assertIn("Xong thật", d["report_markdown"])
        # solution advanced to kept
        r2 = self._get("/api/v1/section-2/solutions")
        sol1 = next(s for s in r2.json()["solutions"] if s["solution_id"] == "SOL-0001")
        self.assertEqual(sol1["status"], "kept")


if __name__ == "__main__":
    unittest.main()
