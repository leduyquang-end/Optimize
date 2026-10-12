import os
import shutil
import unittest

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_optimize_api")
TARGET = os.path.join(TMP, "target_app")
STORE = os.path.join(TMP, "store")
REAL_FOLDER = r"E:\Nghiên cứu khoa học\Chatbot-retrieval-based\Chatbot-retrieval-based"

FAST_SCRIPT = """
import time
time.sleep(0.01)
print("STEP read 40.0")
print("STEP build 10.0")
print("STEP tail 5.0")
print("ok")
"""


def make_brief(feature_id: str = "target_app") -> dict:
    """Brief hợp lệ để qua Cổng 1 (A1-V1..V6)."""
    return {
        "feature_id": feature_id,
        "optimization_targets": [
            {
                "metric_name": "latency_p50_ms",
                "unit": "ms",
                "direction": "decrease",
                "target_value": 40000.0,
                "priority": 1,
                "measurement_source": "loki: {app='target'} | json | latency_ms",
            }
        ],
        "guardrails": [{"metric_name": "quality_score", "max_allowed_change_pct": 2.0, "hard": True}],
        "thresholds": {"keep_improvement_pct": 25.0, "revert_improvement_pct": 10.0},
        "max_risk_tier": "prompt",
        "scope_in": ["app"],
        "scope_out": ["model selection"],
        "business_context": "Giảm độ trễ cho app mục tiêu.",
        "business_rule_card": "optimization_data/registry/cards/Feature_X_v2.md",
        "business_rule_card_confirmed": True,
        "data_gaps": [],
    }


class OptimizeApiBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(TARGET, exist_ok=True)
        self.write_app(FAST_SCRIPT)
        res, body = self.create_source(TARGET, "target_app")
        self.assertEqual(res.status_code, 201, res.text)
        self.source_id = body["source"]["source_id"]
        self.prepare = body

        brief = client.post(
            "/api/v1/lane-a/brief", params={"base_dir": STORE}, json=make_brief()
        )
        self.assertEqual(brief.status_code, 201, brief.text)
        self.brief_id = brief.json()["brief_id"]

    def tearDown(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP, ignore_errors=True)

    def write_app(self, content: str) -> None:
        with open(os.path.join(TARGET, "app.py"), "w", encoding="utf-8") as f:
            f.write(content)

    @staticmethod
    def create_source(folder: str, name: str = None, store: str = STORE):
        res = client.post(
            "/api/v1/optimize/sources/from-path",
            params={"base_dir": store},
            json={"path": folder, "name": name},
        )
        return res, res.json() if res.status_code == 201 else None

    def make_source(self, folder: str, name: str = None) -> str:
        res, body = self.create_source(folder, name)
        self.assertEqual(res.status_code, 201, res.text)
        return body["source"]["source_id"]

    def run_lane(self, payload: dict):
        body = dict(payload, source_id=self.source_id, base_dir=STORE)
        body.setdefault("brief_id", self.brief_id)
        return client.post("/api/v1/optimize/run", json=body)


class TestOptimizeSourcePreparation(OptimizeApiBase):
    def test_from_path_returns_prepare_with_suggested_command(self):
        self.assertEqual(self.prepare["source"]["kind"], "path")
        self.assertEqual(self.prepare["mode"], "script")
        self.assertEqual(self.prepare["runs_available"], 0)
        self.assertEqual(self.prepare["suggested_command"], ["{python}", "app.py"])
        self.assertEqual(self.prepare["suggested_feature"], "target_app")
        rels = [w["relative_path"] for w in self.prepare["scripts"]]
        self.assertIn("app.py", rels)

    def test_suggested_command_skips_web_server_and_prefers_bench_script(self):
        with open(os.path.join(TARGET, "app.py"), "w", encoding="utf-8") as f:
            f.write(
                "from flask import Flask\n"
                "app = Flask(__name__)\n"
                "if __name__ == '__main__':\n"
                "    app.run()\n"
            )
        with open(os.path.join(TARGET, "bench_me.py"), "w", encoding="utf-8") as f:
            f.write("print('STEP a 1.0')\nprint('done')\n")

        res, body = self.create_source(TARGET, "target_app")
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(body["suggested_command"], ["{python}", "bench_me.py"])
        self.assertTrue(any("web server" in n for n in body["notes"]), body["notes"])

    def test_missing_folder_is_404(self):
        res, _ = self.create_source(os.path.join(TMP, "khong_ton_tai"))
        self.assertEqual(res.status_code, 404)

    def test_duplicate_path_reuses_same_source(self):
        first = self.make_source(TARGET, "target_app")
        second = self.make_source(TARGET, "khac_ten")
        self.assertEqual(first, second)

    def test_source_list_and_get_endpoints(self):
        listed = client.get("/api/v1/optimize/sources", params={"base_dir": STORE})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["sources"][0]["source_id"], self.source_id)

        detail = client.get(
            f"/api/v1/optimize/sources/{self.source_id}", params={"base_dir": STORE}
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["mode"], "script")

        missing = client.get("/api/v1/optimize/sources/SRC-9999", params={"base_dir": STORE})
        self.assertEqual(missing.status_code, 404)


class TestOptimizeRunLaneA(OptimizeApiBase):
    def test_lane_a_without_brief_is_blocked_with_reason(self):
        res = self.run_lane({"lane": "A", "brief_id": ""})
        self.assertEqual(res.status_code, 409)
        reasons = res.json()["detail"]["reasons"]
        self.assertTrue(any("Brief" in r for r in reasons), reasons)

    def test_unknown_brief_is_404(self):
        res = self.run_lane({"lane": "A", "brief_id": "BR-9999"})
        self.assertEqual(res.status_code, 404)
        self.assertIn("BR-9999", res.json()["detail"]["error"])

    def test_brief_gate_blocks_before_running_benchmark(self):
        res = self.run_lane(
            {"lane": "A", "brief_id": "", "run_benchmark": True, "repeats": 3}
        )
        self.assertEqual(res.status_code, 409)
        # Brief chưa đạt thì không được chạy benchmark trước
        raw = os.path.join(STORE, "raw_runs")
        leftovers = [] if not os.path.isdir(raw) else [f for _r, _d, fs in os.walk(raw) for f in fs]
        self.assertEqual(leftovers, [])

    def test_benchmark_then_lane_a_returns_baseline_and_hypotheses(self):
        res = self.run_lane(
            {"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W99"}
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()

        self.assertEqual(body["lane"], "A")
        self.assertEqual(body["brief_id"], self.brief_id)
        self.assertEqual(body["baseline"]["brief_id"], self.brief_id)
        self.assertEqual(body["runs_used"], 3)
        self.assertEqual(body["benchmark"]["succeeded"], 3)
        self.assertTrue(body["gate2_passed"])
        self.assertEqual(body["baseline"]["sample_count"], 3)
        self.assertTrue(body["baseline"]["is_weak_baseline"])  # 3 < min_runs 30

        # bottleneck thật từ số đo: STEP read chiếm 40/55 = 72.7%
        self.assertTrue(body["bottlenecks"])
        top = body["bottlenecks"][0]
        self.assertEqual(top["step_name"], "read")
        self.assertIn("share", top["signals"])
        self.assertAlmostEqual(top["pct_of_total_time"], 72.73, places=1)

        # chưa xác minh biến cấu hình -> chỉ nằm trong hypotheses (A3-V6)
        self.assertEqual(body["solutions"], [])
        self.assertTrue(body["hypotheses"])
        hypothesis = body["hypotheses"][0]
        self.assertTrue(hypothesis["is_unverified_hypothesis"])
        self.assertEqual(hypothesis["source_lane"], "A")
        self.assertFalse(hypothesis["gate3"]["passed"])
        self.assertTrue(any(e.startswith("A3-V1") for e in hypothesis["gate3"]["errors"]))
        self.assertTrue(hypothesis["verified_root_cause"]["evidence_log_lines"])
        self.assertIn("total=", hypothesis["verified_root_cause"]["evidence_log_lines"][0])

    def test_tiny_step_is_reported_but_not_proposed(self):
        # noise có long tail (p99/p50 >= 3) nhưng share cực nhỏ
        script = (
            "import os\n"
            "import time\n"
            "time.sleep(0.01)\n"
            "print('STEP read 40.0')\n"
            "print('STEP build 10.0')\n"
            "counter = os.path.join(os.path.dirname(__file__), 'counter.txt')\n"
            "n = int(open(counter).read()) if os.path.exists(counter) else 0\n"
            "open(counter, 'w').write(str(n + 1))\n"
            "print('STEP noise', 0.05 if n % 3 == 2 else 0.01)\n"
            "print('ok')\n"
        )
        self.write_app(script)

        res = self.run_lane({"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W95"})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()

        step_names = {b["step_name"] for b in body["bottlenecks"]}
        self.assertIn("noise", step_names)  # tín hiệu long_tail vẫn được ghi nhận
        self.assertNotIn("noise", [h["change"]["variables"][0] for h in body["hypotheses"]])
        self.assertTrue(any("noise" in note for note in body["notes"]))

    def test_lane_a_without_runs_is_blocked_with_reason(self):
        res = self.run_lane({"lane": "A"})
        self.assertEqual(res.status_code, 409)
        detail = res.json()["detail"]
        self.assertIn("Chưa có số đo", detail["reasons"][0])

    def test_recorded_runs_can_be_reused_without_rerunning(self):
        first = self.run_lane(
            {"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W98"}
        )
        self.assertEqual(first.status_code, 200, first.text)

        second = self.run_lane({"lane": "A", "period": "2026-W98"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["runs_used"], 3)
        self.assertIsNone(second.json()["benchmark"])

    def test_hypothesis_ids_are_unique_and_never_saved_as_solutions(self):
        first = self.run_lane(
            {"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W97"}
        )
        self.assertEqual(first.status_code, 200, first.text)
        second = self.run_lane({"lane": "A", "period": "2026-W97"})
        self.assertEqual(second.status_code, 200, second.text)

        ids1 = [h["solution_id"] for h in first.json()["hypotheses"]]
        ids2 = [h["solution_id"] for h in second.json()["hypotheses"]]
        self.assertTrue(ids1, "cần ít nhất 1 hypothesis từ số đo")
        self.assertEqual(len(set(ids1 + ids2)), len(ids1) + len(ids2))
        for sid in ids1 + ids2:
            self.assertTrue(sid.startswith("HYP-"), sid)
            self.assertTrue(os.path.exists(os.path.join(STORE, "hypotheses", f"{sid}.json")))
            self.assertFalse(os.path.exists(os.path.join(STORE, "solutions", f"{sid}.json")))

    def test_confirm_hypothesis_promotes_to_main_solution(self):
        res = self.run_lane({"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W93"})
        self.assertEqual(res.status_code, 200, res.text)
        hid = res.json()["hypotheses"][0]["solution_id"]

        missing_var = client.post(
            f"/api/v1/optimize/hypotheses/{hid}/confirm",
            json={"variable": "   ", "base_dir": STORE},
        )
        self.assertEqual(missing_var.status_code, 422)

        ok = client.post(
            f"/api/v1/optimize/hypotheses/{hid}/confirm",
            json={"variable": "READ_CHUNK", "reviewer": "mai", "base_dir": STORE},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        body = ok.json()
        self.assertTrue(body["gate3"]["passed"], body)
        self.assertTrue(body["solution_id"].startswith("SOL-"))
        self.assertEqual(body["variable"], "READ_CHUNK")
        self.assertTrue(os.path.exists(os.path.join(STORE, "solutions", body["solution_id"] + ".json")))
        saved_hyp = None
        with open(os.path.join(STORE, "hypotheses", f"{hid}.json"), "r", encoding="utf-8") as f:
            import json as jsonlib

            saved_hyp = jsonlib.load(f)
        self.assertEqual(saved_hyp["confirmed_solution_id"], body["solution_id"])
        self.assertTrue(saved_hyp["is_unverified_hypothesis"])  # hồ sơ gốc vẫn là hypothesis

        again = client.post(
            f"/api/v1/optimize/hypotheses/{hid}/confirm",
            json={"variable": "X", "base_dir": STORE},
        )
        self.assertEqual(again.status_code, 422)

        unknown = client.post(
            "/api/v1/optimize/hypotheses/HYP-9999/confirm",
            json={"variable": "X", "base_dir": STORE},
        )
        self.assertEqual(unknown.status_code, 404)

        # chạy lại lane A (dùng số đo đã ghi): solution đã chốt nằm trong result.solutions,
        # bước đã chốt biến không sinh hypothesis trùng
        rerun = self.run_lane({"lane": "A", "period": "2026-W93"})
        self.assertEqual(rerun.status_code, 200, rerun.text)
        body2 = rerun.json()
        ids = [s["solution_id"] for s in body2["solutions"]]
        self.assertIn(body["solution_id"], ids)
        self.assertFalse(body2["solutions"][0]["is_unverified_hypothesis"])
        self.assertEqual(body2["hypotheses"], [])
        self.assertTrue(any("chốt biến" in n for n in body2["notes"]), body2["notes"])

    def test_lane_a_blocks_when_zero_runs_succeeded(self):
        self.write_app("import sys\nsys.stderr.write('boom\\n')\nsys.exit(1)\n")
        res = self.run_lane(
            {"lane": "A", "run_benchmark": True, "repeats": 2, "period": "2026-W92"}
        )
        self.assertEqual(res.status_code, 409, res.text)
        detail = res.json()["detail"]
        # preflight chạy thử 1 lần -> fail -> dừng ngay, lý do rõ ràng
        self.assertTrue(any("Preflight" in r for r in detail["reasons"]), detail["reasons"])
        self.assertTrue(any("Preflight" in e for e in detail["errors"]), detail["errors"])
        self.assertTrue(any("boom" in e for e in detail["errors"]), detail["errors"])

    def test_preflight_can_be_skipped_with_zero(self):
        # run đầu fail, run sau in STEP: preflight tắt (0) thì vẫn chạy đủ 2 lần
        self.write_app(
            "import os, sys\n"
            "if not os.path.exists('done.txt'):\n"
            "    open('done.txt', 'w').write('1')\n"
            "    sys.exit(1)\n"
            "print('STEP a 1.0')\n"
        )
        res = self.run_lane(
            {
                "lane": "A",
                "run_benchmark": True,
                "repeats": 2,
                "preflight_timeout_s": 0,
                "period": "2026-W88",
            }
        )
        self.assertEqual(res.status_code, 200, res.text)
        bench = res.json()["benchmark"]
        self.assertEqual(bench["total"], 2)
        self.assertEqual(bench["succeeded"], 1)
        self.assertIsNone(bench["preflight"])

    def test_recorded_runs_of_another_source_are_not_used_silently(self):
        # số đo tốt của nguồn này
        good = self.run_lane(
            {"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W91"}
        )
        self.assertEqual(good.status_code, 200, good.text)

        # file mới hơn nhưng thuộc nguồn khác (cùng feature/period)
        from src.core.storage.file_store import FileStore

        FileStore(STORE).save_raw_runs(
            "target_app",
            "2026-W91",
            {
                "runs": [
                    {
                        "run_id": "rX",
                        "status": "success",
                        "latency_ms": 1.0,
                        "steps": {},
                        "config": {"source": "SRC-OTHER"},
                    }
                ],
                "config": {"source": "SRC-OTHER"},
            },
        )

        rerun = self.run_lane({"lane": "A", "period": "2026-W91"})
        self.assertEqual(rerun.status_code, 200, rerun.text)
        body = rerun.json()
        self.assertEqual(body["runs_used"], 3)  # vẫn lấy file của nguồn này
        self.assertNotIn("2026-W91-2", body["runs_source"] or "")  # không lấy file của SRC-OTHER

    def test_unknown_source_is_404(self):
        res = client.post(
            "/api/v1/optimize/run",
            json={
                "lane": "A",
                "source_id": "SRC-9999",
                "brief_id": self.brief_id,
                "base_dir": STORE,
            },
        )
        self.assertEqual(res.status_code, 404)


class TestOptimizeRunLaneB(OptimizeApiBase):
    def test_lane_b_is_blocked_when_policy_and_registry_are_missing(self):
        res = self.run_lane(
            {"lane": "B", "run_benchmark": True, "repeats": 3, "period": "2026-W97"}
        )
        self.assertEqual(res.status_code, 409, res.text)
        detail = res.json()["detail"]
        self.assertEqual(detail["lane"], "B")
        self.assertTrue(detail["reasons"])
        self.assertTrue(
            any("registry" in r.lower() or "policy" in r.lower() for r in detail["reasons"])
        )


    def test_blocked_409_carries_benchmark_errors(self):
        # script lỗi -> preflight chạy thử 1 lần, fail là dừng (không tốn 2×timeout),
        # stderr vẫn hiện trong 409, không được nuốt
        self.write_app("import sys\nsys.exit(3)\n")
        res = self.run_lane(
            {"lane": "B", "run_benchmark": True, "repeats": 2, "period": "2026-W96"}
        )
        self.assertEqual(res.status_code, 409, res.text)
        detail = res.json()["detail"]
        self.assertIn("errors", detail)
        self.assertTrue(any("Preflight" in e for e in detail["errors"]), detail["errors"])
        self.assertTrue(any("exit code 3" in e for e in detail["errors"]), detail["errors"])
        self.assertTrue(any("dừng ngay" in e for e in detail["errors"]), detail["errors"])


    def test_self_loop_script_counts_each_cycle_as_a_run(self):
        self.write_app(
            "import time\n"
            "for _ in range(3):\n"
            "    t = time.perf_counter()\n"
            "    print('STEP work 10.0')\n"
            "    print('RUN %.1f' % ((time.perf_counter() - t) * 1000))\n"
            "print('done')\n"
        )
        res = self.run_lane(
            {"lane": "B", "run_benchmark": True, "self_loop": True, "period": "2026-W94"}
        )
        self.assertEqual(res.status_code, 409, res.text)
        notes = res.json()["detail"]["notes"]
        self.assertTrue(any("3/3 run thành công" in n for n in notes), notes)

    def test_timeout_s_is_passed_to_each_run(self):
        self.write_app("import time\ntime.sleep(1.5)\nprint('done')\n")
        res = self.run_lane(
            {
                "lane": "B",
                "run_benchmark": True,
                "repeats": 1,
                "timeout_s": 0.3,
                "period": "2026-W95",
            }
        )
        self.assertEqual(res.status_code, 409, res.text)
        errors = res.json()["detail"]["errors"]
        self.assertTrue(any("timeout after 0.3" in e for e in errors), errors)


class TestOptimizeRequestValidation(OptimizeApiBase):
    def test_invalid_lane_is_rejected(self):
        res = self.run_lane({"lane": "C"})
        self.assertEqual(res.status_code, 422)
        self.assertIn("lane", res.json()["detail"]["error"])

    def test_non_positive_timeout_is_rejected(self):
        res = self.run_lane({"lane": "A", "timeout_s": 0})
        self.assertEqual(res.status_code, 422)
        self.assertIn("timeout_s", str(res.json()["detail"]))

    def test_command_escaping_folder_is_rejected(self):
        outside = os.path.join(TMP, "ngoai.py")
        with open(outside, "w", encoding="utf-8") as f:
            f.write("print('x')\n")

        res = self.run_lane(
            {
                "lane": "A",
                "run_benchmark": True,
                "command": ["{python}", outside],
            }
        )
        self.assertEqual(res.status_code, 422)
        self.assertIn("ngoai.py", res.json()["detail"]["error"])


class TestOptimizeSupportEndpoints(OptimizeApiBase):
    def test_workloads_endpoint_lists_scripts_and_skips_venv(self):
        os.makedirs(os.path.join(TARGET, ".venv"), exist_ok=True)
        with open(os.path.join(TARGET, ".venv", "pkg.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n")

        res = client.get("/api/v1/optimize/workloads", params={"folder": TARGET})
        self.assertEqual(res.status_code, 200, res.text)
        rels = [w["relative_path"] for w in res.json()["workloads"]]
        self.assertIn("app.py", rels)
        self.assertFalse(any(".venv" in r for r in rels))

    def test_workloads_endpoint_404_for_missing_folder(self):
        res = client.get("/api/v1/optimize/workloads", params={"folder": os.path.join(TMP, "khong")})
        self.assertEqual(res.status_code, 404)

    def test_runs_endpoint_reports_recorded_runs(self):
        self.assertEqual(
            self.run_lane(
                {"lane": "A", "run_benchmark": True, "repeats": 3, "period": "2026-W96"}
            ).status_code,
            200,
        )
        res = client.get(
            "/api/v1/optimize/runs",
            params={"feature": "target_app", "period": "2026-W96", "base_dir": STORE},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["succeeded"], 3)
        self.assertIsNotNone(body["source"])


class TestUiPages(unittest.TestCase):
    def test_ui_serves_html_and_assets(self):
        for url, marker in (
            ("/ui", "Chọn lane"),
            ("/ui/", "nguồn bài test"),
            ("/ui/app.js", "runLane"),
            ("/ui/app.css", ".badge"),
        ):
            res = client.get(url)
            self.assertEqual(res.status_code, 200, url)
            self.assertIn(marker.lower(), res.text.lower())

    def test_root_redirects_to_ui_and_health_reports_json(self):
        res = client.get("/", follow_redirects=True)
        self.assertIn("Chọn lane", res.text)
        self.assertEqual(client.get("/health").json()["ui"], "/ui")


class TestRealFolderSmoke(unittest.TestCase):
    """Smoke trên folder mục tiêu thật (bỏ qua nếu máy không có folder đó)."""

    def setUp(self):
        self.tearDown()

    def tearDown(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP, ignore_errors=True)

    @unittest.skipUnless(os.path.isdir(REAL_FOLDER), "khong tim thay folder muc tieu")
    def test_real_folder_is_readable_as_source(self):
        store = os.path.join(TMP, "real_store")
        res = client.post(
            "/api/v1/optimize/sources/from-path",
            params={"base_dir": store},
            json={"path": REAL_FOLDER},
        )
        self.assertEqual(res.status_code, 201, res.text)
        prepare = res.json()
        self.assertEqual(prepare["mode"], "script")
        self.assertTrue(prepare["scripts"])
        self.assertTrue(prepare["suggested_command"][0] == "{python}")

        # Brief hợp lệ trước, sau đó chạy -> đúng 409 "Chưa có số đo" (không bịa baseline)
        brief = client.post(
            "/api/v1/lane-a/brief",
            params={"base_dir": store},
            json=make_brief(prepare["suggested_feature"]),
        )
        self.assertEqual(brief.status_code, 201, brief.text)

        blocked = client.post(
            "/api/v1/optimize/run",
            json={
                "lane": "A",
                "source_id": prepare["source"]["source_id"],
                "brief_id": brief.json()["brief_id"],
                "base_dir": store,
            },
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("Chưa có số đo", blocked.json()["detail"]["reasons"][0])


if __name__ == "__main__":
    unittest.main()
