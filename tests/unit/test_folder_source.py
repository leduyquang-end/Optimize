import json
import os
import shutil
import unittest

from src.core.adapters.folder_source import FolderSource

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_folder_source")


class TestFolderSource(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(os.path.join(BASE_DIR, "sub"), exist_ok=True)
        os.makedirs(os.path.join(BASE_DIR, ".venv", "lib"), exist_ok=True)
        os.makedirs(os.path.join(BASE_DIR, "__pycache__"), exist_ok=True)

        self._write("main.py", "print('entry')\n")
        self._write("helper.py", "def h(): return 1\n")
        self._write(os.path.join("sub", "worker.py"), "def w(): return 2\n")
        self._write(os.path.join(".venv", "lib", "site_module.py"), "x = 1\n")
        self._write(os.path.join("__pycache__", "cached.py"), "y = 2\n")
        self._write(".env", "SECRET=do-not-read\n")

    def tearDown(self):
        if os.path.isdir(BASE_DIR):
            shutil.rmtree(BASE_DIR, ignore_errors=True)

    def _write(self, rel: str, content: str) -> str:
        path = os.path.join(BASE_DIR, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    # ------------------------------------------------------------- workloads ---
    def test_lists_scripts_and_skips_venv_and_cache(self):
        workloads = FolderSource(BASE_DIR).list_workloads()
        rels = sorted(w.relative_path for w in workloads)

        self.assertIn("main.py", rels)
        self.assertIn("helper.py", rels)
        self.assertIn(os.path.join("sub", "worker.py"), rels)
        self.assertFalse(any(".venv" in r for r in rels))
        self.assertFalse(any("__pycache__" in r for r in rels))

        kinds = {w.relative_path: w.kind for w in workloads}
        self.assertEqual(kinds["main.py"], "entry")
        self.assertEqual(kinds["helper.py"], "script")

    def test_missing_folder_raises(self):
        with self.assertRaises(FileNotFoundError):
            FolderSource(os.path.join(BASE_DIR, "khong_ton_tai")).list_workloads()

    # -------------------------------------------------------------- run files ---
    def test_load_runs_from_json_jsonl_and_csv(self):
        with open(os.path.join(BASE_DIR, "runs.json"), "w", encoding="utf-8") as f:
            json.dump({"runs": [{"run_id": "a", "latency_ms": 12.5, "status": "success"}]}, f)
        with open(os.path.join(BASE_DIR, "runs.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"run_id": "b", "latency_ms": 20}) + "\n")
            f.write("\n")
        with open(os.path.join(BASE_DIR, "runs.csv"), "w", encoding="utf-8", newline="") as f:
            f.write("run_id,latency_ms,status\n")
            f.write("c,33.5,success\n")

        runs = FolderSource(BASE_DIR).load_runs()
        self.assertEqual(len(runs), 3)
        self.assertEqual({r["run_id"] for r in runs}, {"a", "b", "c"})
        self.assertEqual([r["latency_ms"] for r in runs], [12.5, 20.0, 33.5])
        self.assertTrue(all(r["status"] == "success" for r in runs))

    def test_rows_without_latency_are_dropped_not_estimated(self):
        with open(os.path.join(BASE_DIR, "runs.json"), "w", encoding="utf-8") as f:
            json.dump(
                [
                    {"run_id": "ok", "latency_ms": 10},
                    {"run_id": "no-latency", "status": "success"},
                    {"run_id": "bad", "latency_ms": "khong phai so"},
                ],
                f,
            )
        runs = FolderSource(BASE_DIR).load_runs()
        self.assertEqual([r["run_id"] for r in runs], ["ok"])

    def test_no_run_files_returns_empty(self):
        self.assertEqual(FolderSource(BASE_DIR).load_runs(), [])


if __name__ == "__main__":
    unittest.main()
