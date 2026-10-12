import io
import json
import os
import shutil
import unittest
import zipfile

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_sources_upload")
STORE = os.path.join(TMP, "store")

SCRIPT = "import time\nprint('STEP work 12.0')\ntime.sleep(0.01)\nprint('ok')\n"


def make_valid_brief(feature_id: str) -> dict:
    return {
        "feature_id": feature_id,
        "optimization_targets": [
            {
                "metric_name": "latency_p50_ms",
                "unit": "ms",
                "direction": "decrease",
                "target_value": 40000.0,
                "priority": 1,
                "measurement_source": "loki: {app='upload'} | json | latency_ms",
            }
        ],
        "guardrails": [{"metric_name": "quality_score", "max_allowed_change_pct": 2.0, "hard": True}],
        "thresholds": {"keep_improvement_pct": 25.0, "revert_improvement_pct": 10.0},
        "max_risk_tier": "prompt",
        "scope_in": ["app"],
        "scope_out": ["model selection"],
        "business_context": "Giảm độ trễ app nạp qua upload.",
        "business_rule_card": "optimization_data/registry/cards/Feature_X_v2.md",
        "business_rule_card_confirmed": True,
        "data_gaps": [],
    }


def make_brief_for(source_id: str) -> str:
    """Brief hợp lệ cho feature suy ra từ source (A1 bắt buộc với lane A)."""
    res = client.post(
        "/api/v1/lane-a/brief",
        params={"base_dir": STORE},
        json=make_valid_brief(f"feature_{source_id.lower().replace('-', '_')}"),
    )
    assert res.status_code == 201, res.text
    return res.json()["brief_id"]


def upload(files, data):
    return client.post(
        "/api/v1/optimize/sources/upload",
        params={"base_dir": STORE},
        files=[("files", item) for item in files],
        data=data,
    )


class UploadApiBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()

    def tearDown(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP, ignore_errors=True)

    def uploaded_folder(self, source_id: str) -> str:
        return os.path.join(STORE, "uploads", source_id)


class TestSourceUploadApi(UploadApiBase):
    def test_upload_files_with_relative_paths(self):
        res = upload(
            [("main.py", b"print('hi')", "text/x-python"), ("data/a.txt", b"abc", "text/plain")],
            {"paths": json.dumps(["main.py", "data/a.txt"]), "name": "bai_nhap"},
        )
        self.assertEqual(res.status_code, 201, res.text)
        prepare = res.json()
        source_id = prepare["source"]["source_id"]
        folder = self.uploaded_folder(source_id)

        self.assertEqual(prepare["source"]["kind"], "upload")
        self.assertEqual(prepare["source"]["name"], "bai_nhap")
        self.assertTrue(os.path.exists(os.path.join(folder, "main.py")))
        self.assertTrue(os.path.exists(os.path.join(folder, "data", "a.txt")))
        self.assertEqual(prepare["mode"], "script")
        self.assertEqual(prepare["suggested_command"], ["{python}", "main.py"])

    def test_upload_zip_with_runs_json_is_recorded_mode(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(
                "runs.json",
                json.dumps({"runs": [{"run_id": "a", "latency_ms": 12.5, "status": "success"}]}),
            )
        res = upload([("bundle.zip", buffer.getvalue(), "application/zip")], {})
        self.assertEqual(res.status_code, 201, res.text)
        prepare = res.json()
        self.assertEqual(prepare["mode"], "recorded")
        self.assertEqual(prepare["runs_available"], 1)

        # dùng luôn số đo trong zip để chạy lane A
        run = client.post(
            "/api/v1/optimize/run",
            json={
                "lane": "A",
                "source_id": prepare["source"]["source_id"],
                "brief_id": make_brief_for(prepare["source"]["source_id"]),
                "base_dir": STORE,
            },
        )
        self.assertEqual(run.status_code, 200, run.text)
        self.assertEqual(run.json()["baseline"]["sample_count"], 1)

    def test_uploaded_script_can_be_measured_and_lane_a_run(self):
        res = upload(
            [("app.py", SCRIPT.encode("utf-8"), "text/x-python")],
            {"paths": json.dumps(["app.py"])},
        )
        self.assertEqual(res.status_code, 201, res.text)
        source_id = res.json()["source"]["source_id"]

        run = client.post(
            "/api/v1/optimize/run",
            json={
                "lane": "A",
                "source_id": source_id,
                "brief_id": make_brief_for(source_id),
                "run_benchmark": True,
                "repeats": 2,
                "period": "UPLOAD-1",
                "base_dir": STORE,
            },
        )
        self.assertEqual(run.status_code, 200, run.text)
        body = run.json()
        self.assertEqual(body["benchmark"]["succeeded"], 2)
        self.assertEqual(body["baseline"]["sample_count"], 2)
        self.assertTrue(body["bottlenecks"])  # STEP work 12ms = 100% share

    def test_path_traversal_is_rejected_with_422(self):
        res = upload([("evil.py", b"x", "text/x-python")], {"paths": json.dumps(["../evil.py"])})
        self.assertEqual(res.status_code, 422)
        self.assertIn("..", res.json()["detail"]["error"])

        uploads = os.path.join(STORE, "uploads")
        self.assertEqual(os.listdir(uploads) if os.path.isdir(uploads) else [], [])

    def test_upload_without_files_is_422(self):
        res = client.post(
            "/api/v1/optimize/sources/upload",
            params={"base_dir": STORE},
            data={"paths": json.dumps(["a.py"])},
        )
        self.assertEqual(res.status_code, 422)

    def test_paths_that_is_not_json_array_is_422(self):
        res = upload([("a.py", b"x", "text/x-python")], {"paths": "khong-phai-json"})
        self.assertEqual(res.status_code, 422)
        self.assertIn("JSON array", res.json()["detail"]["error"])


if __name__ == "__main__":
    unittest.main()
