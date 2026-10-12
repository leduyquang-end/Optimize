import json
import os
import shutil
import unittest

from src.core.adapters.benchmark_runner import (
    BenchmarkRunner,
    BenchmarkSpec,
    load_recorded_runs,
)
from src.core.storage.file_store import FileStore

TMP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_tmp_benchmark")
TARGET = os.path.join(TMP, "target")
STORE = os.path.join(TMP, "store")

FAST_SCRIPT = """
import time
time.sleep(0.01)
print("STEP load 12.5")
print("STEP parse 3.0")
print("STEP load 0.5")
print("done")
"""

FAILING_SCRIPT = """
import sys
print("STEP partial 1.0")
sys.exit(3)
"""


class BenchmarkBase(unittest.TestCase):
    def setUp(self):
        self.tearDown()
        os.makedirs(TARGET, exist_ok=True)
        self.store = FileStore(base_dir=STORE)
        self.runner = BenchmarkRunner(file_store=self.store)

    def tearDown(self):
        if os.path.isdir(TMP):
            shutil.rmtree(TMP, ignore_errors=True)

    def write_script(self, name: str, content: str) -> str:
        path = os.path.join(TARGET, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def spec(self, script="ok.py", repeats=3, config=None) -> BenchmarkSpec:
        return BenchmarkSpec(
            benchmark_id="BM-TEST",
            feature="Feat_Test",
            folder=TARGET,
            command=["{python}", script],
            repeats=repeats,
            timeout_s=20,
            config=config or {"VARIANT": "baseline"},
        )


class TestBenchmarkRunner(BenchmarkBase):
    def test_runs_command_and_records_runs_with_steps(self):
        self.write_script("ok.py", FAST_SCRIPT)
        outcome = self.runner.run(self.spec(), period="2026-W99")

        self.assertEqual(outcome.total, 3)
        self.assertEqual(outcome.succeeded, 3)
        self.assertEqual(outcome.failed, 0)
        self.assertEqual(outcome.steps_seen, ["load", "parse"])
        self.assertTrue(os.path.exists(outcome.runs_file))

        with open(outcome.runs_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertEqual(payload["feature"], "Feat_Test")
        self.assertEqual(payload["period"], "2026-W99")
        for run in payload["runs"]:
            self.assertEqual(run["status"], "success")
            self.assertGreater(run["latency_ms"], 0)
            self.assertEqual(run["fingerprint"], outcome.fingerprint)
            self.assertEqual(run["steps"]["load"], 13.0)  # 12.5 + 0.5 được cộng dồn
            self.assertEqual(run["steps"]["parse"], 3.0)
            self.assertEqual(run["workload_ms"], 16.0)  # tổng STEP, tách khỏi startup
            self.assertEqual(run["config"], {"VARIANT": "baseline"})

    def test_run_without_step_markers_has_no_workload(self):
        self.write_script("plain.py", "print('hi')\n")
        # preflight tắt (0): run không in STEP vẫn được ghi (chỉ mất bottleneck)
        spec = self.spec(script="plain.py", repeats=1).model_copy(
            update={"preflight_timeout_s": 0}
        )
        outcome = self.runner.run(spec, period="2026-W99")

        self.assertEqual(outcome.succeeded, 1, outcome.errors)
        with open(outcome.runs_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        self.assertIsNone(payload["runs"][0]["workload_ms"])
        self.assertEqual(payload["runs"][0]["steps"], {})

    def test_fingerprint_depends_on_folder_command_and_config(self):
        self.write_script("ok.py", FAST_SCRIPT)
        base = self.runner.fingerprint(self.spec())
        same = self.runner.fingerprint(self.spec())
        other_config = self.runner.fingerprint(self.spec(config={"VARIANT": "khac"}))
        self.assertEqual(base, same)
        self.assertNotEqual(base, other_config)

    def test_failing_command_is_recorded_not_hidden(self):
        self.write_script("bad.py", FAILING_SCRIPT)
        # preflight tắt (0): chạy đủ 2 lần để test cách ghi nhận lỗi từng run
        spec = self.spec(script="bad.py", repeats=2).model_copy(update={"preflight_timeout_s": 0})
        outcome = self.runner.run(spec, period="2026-W99")

        self.assertEqual(outcome.succeeded, 0)
        self.assertEqual(outcome.failed, 2)
        # lỗi giống hệt nhau được gộp, vẫn hiện đủ run và dòng lỗi cuối
        self.assertEqual(len(outcome.errors), 1)
        self.assertIn("run r1,r2", outcome.errors[0])
        self.assertIn("exit code 3", outcome.errors[0])

    def test_preflight_failure_aborts_before_repeats(self):
        # FAILING_SCRIPT: preflight thấy exit code 3 -> dừng ngay, KHÔNG chạy 5 lần
        self.write_script("bad.py", FAILING_SCRIPT)
        spec = self.spec(script="bad.py", repeats=5).model_copy(update={"timeout_s": 120})
        outcome = self.runner.run(spec, period="2026-W99")

        self.assertEqual(outcome.total, 0)
        self.assertIsNone(outcome.runs_file)
        self.assertFalse(outcome.preflight["ok"])
        self.assertIn("Preflight", outcome.errors[0])
        self.assertIn("exit code 3", outcome.errors[0])
        self.assertIn("dừng ngay", outcome.errors[0])
        # không được ghi file raw_runs rỗng làm hỏng recorded mode sau này
        raw = os.path.join(STORE, "raw_runs")
        files = [] if not os.path.isdir(raw) else [f for _r, _d, fs in os.walk(raw) for f in fs]
        self.assertEqual(files, [])

    def test_preflight_detects_missing_step_markers(self):
        self.write_script("plain.py", "print('chay het nhung khong in STEP')\n")
        spec = self.spec(script="plain.py", repeats=5)
        outcome = self.runner.run(spec, period="2026-W99")

        self.assertEqual(outcome.total, 0)
        self.assertFalse(outcome.preflight["ok"])
        self.assertIn("STEP", outcome.errors[0])
        self.assertIn("bench_driver.py", outcome.errors[0])  # gợi ý driver đo chung

    def test_preflight_ok_is_reported_and_runs_proceed(self):
        self.write_script("ok.py", FAST_SCRIPT)
        outcome = self.runner.run(self.spec(script="ok.py", repeats=3), period="2026-W99")

        self.assertTrue(outcome.preflight["ok"], outcome.preflight)
        self.assertEqual(outcome.preflight["steps_seen"], ["load", "parse"])
        self.assertEqual(outcome.total, 3)  # preflight không tính vào số run

    def test_stderr_error_shows_tail_not_head(self):
        # traceback dài: phần đầu toàn path site-packages, dòng lỗi nằm cuối
        long_tail = "x" * 1000 + "\nImportError: cannot import name 'y'"
        self.assertEqual(
            BenchmarkRunner.tail_stderr(long_tail),
            "…" + long_tail.strip()[-600:],
        )
        self.assertIn("ImportError", BenchmarkRunner.tail_stderr(long_tail))

    def test_missing_folder_never_executes(self):
        spec = self.spec().model_copy(update={"folder": os.path.join(TMP, "khong_ton_tai")})
        with self.assertRaises(FileNotFoundError):
            self.runner.run(spec)

    def test_relative_folder_is_resolved_to_absolute_paths(self):
        # folder tương đối (như nguồn upload): trước đây lệnh bị hiểu sai
        # tương đối với subprocess cwd -> "can't open file" -> 0 run thành công
        self.write_script("ok.py", FAST_SCRIPT)
        rel_folder = os.path.relpath(TARGET)
        spec = self.spec().model_copy(update={"folder": rel_folder})

        resolved = BenchmarkRunner()._resolve_command(spec.command, os.path.abspath(rel_folder))
        # resolved = [python, -u, <abs script>]
        script_idx = next(i for i, t in enumerate(resolved) if t.endswith("ok.py"))
        self.assertTrue(os.path.isabs(resolved[script_idx]), resolved)
        self.assertTrue(os.path.exists(resolved[script_idx]))

        outcome = self.runner.run(spec, period="2026-W99")
        self.assertEqual(outcome.succeeded, 3, outcome.errors)

    def test_parse_steps_sums_and_ignores_noise(self):
        steps = BenchmarkRunner.parse_steps("STEP a 1.5\nnoise\nSTEP a 2.5\nSTEP b 4\n")
        self.assertEqual(steps, {"a": 4.0, "b": 4.0})


class TestCommandValidation(BenchmarkBase):
    def test_command_inside_folder_is_allowed(self):
        self.write_script("ok.py", FAST_SCRIPT)
        BenchmarkRunner.validate_command(["{python}", "ok.py"], TARGET)

    def test_bare_name_is_allowed_via_path_lookup(self):
        BenchmarkRunner.validate_command(["python", "-V"], TARGET)

    def test_absolute_path_outside_folder_is_rejected(self):
        outside = os.path.join(TMP, "ngoai.py")
        with self.assertRaises(ValueError):
            BenchmarkRunner.validate_command(["{python}", outside], TARGET)

    def test_project_venv_interpreter_outside_folder_is_allowed(self):
        venv_python = os.path.join(TMP, "venv", "Scripts", "python.exe")
        BenchmarkRunner.validate_command(["{python}", "ok.py"], TARGET)  # smoke
        BenchmarkRunner.validate_command([venv_python, "ok.py"], TARGET)
        # nhưng file .py ngoài folder vẫn bị chặn dù tên bắt đầu bằng "python"
        with self.assertRaises(ValueError):
            BenchmarkRunner.validate_command(
                [os.path.join(TMP, "python_utils.py")], TARGET
            )

    def test_relative_escape_is_rejected(self):
        with self.assertRaises(ValueError):
            BenchmarkRunner.validate_command(["{python}", os.path.join("..", "ngoai.py")], TARGET)

    def test_run_refuses_command_that_escapes_folder(self):
        self.write_script("ok.py", FAST_SCRIPT)
        outside = os.path.join(TMP, "ngoai.py")
        with self.assertRaises(ValueError):
            self.runner.run(self.spec().model_copy(update={"command": ["{python}", outside]}))


class TestSelfLoop(BenchmarkBase):
    SELF_LOOP_SCRIPT = """
import time
with open("starts.txt", "a") as fh:
    fh.write("x\\n")
for _ in range(3):
    t = time.perf_counter()
    print("STEP work 10.0")
    print("STEP other 5.0")
    print("RUN %.1f" % ((time.perf_counter() - t) * 1000))
print("done")
"""

    def test_self_loop_splits_one_process_into_runs(self):
        self.write_script("loop.py", self.SELF_LOOP_SCRIPT)
        spec = self.spec(script="loop.py", repeats=7).model_copy(update={"self_loop": True})
        outcome = self.runner.run(spec, period="2026-W99")

        # 3 vòng -> 3 run, KHÔNG chạy 7 process
        self.assertEqual(outcome.total, 3, outcome.errors)
        self.assertEqual(outcome.succeeded, 3)
        self.assertEqual(outcome.failed, 0)

        # 2 process khởi tạo: 1 preflight + 1 lần đo chính (preflight cũng 1 process)
        with open(os.path.join(TARGET, "starts.txt"), "r", encoding="utf-8") as fh:
            self.assertEqual(len(fh.read().splitlines()), 2)

        with open(outcome.runs_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        for run in payload["runs"]:
            self.assertEqual(run["steps"], {"work": 10.0, "other": 5.0})
            self.assertEqual(run["workload_ms"], 15.0)
            self.assertLess(run["latency_ms"], 1000.0)  # wall của vòng, không gồm startup

    def test_self_loop_without_run_marker_is_reported(self):
        self.write_script("noloop.py", "import time\nprint('STEP a 1.0')\ntime.sleep(0.01)\n")
        spec = self.spec(script="noloop.py").model_copy(update={"self_loop": True})
        outcome = self.runner.run(spec, period="2026-W99")

        self.assertEqual(outcome.succeeded, 0)
        self.assertEqual(outcome.failed, 1)
        self.assertIn("RUN <ms>", outcome.errors[0])

    def test_parse_self_loop_ignores_trailing_steps(self):
        stdout = "STEP a 1.0\nRUN 12.5\nSTEP b 2.0\nRUN 9.9\nSTEP c 3.0\n"
        runs = BenchmarkRunner.parse_self_loop(stdout)
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0], {"latency_ms": 12.5, "workload_ms": 1.0, "steps": {"a": 1.0}})
        self.assertEqual(runs[1], {"latency_ms": 9.9, "workload_ms": 2.0, "steps": {"b": 2.0}})


class TestBenchmarkSpecLoading(BenchmarkBase):
    def test_load_recorded_runs_returns_latest_file(self):
        self.store.save_raw_runs("Feat_Test", "2026-W01", {"runs": [{"run_id": "old", "latency_ms": 1}]})
        latest = self.store.save_raw_runs(
            "Feat_Test", "2026-W02", {"runs": [{"run_id": "new", "latency_ms": 2}]}
        )

        runs, source = load_recorded_runs(STORE, feature="Feat_Test")
        self.assertEqual(source, latest)
        self.assertEqual(runs[0]["run_id"], "new")

        none_runs, none_source = load_recorded_runs(STORE, feature="Feature_Khac")
        self.assertEqual(none_runs, [])
        self.assertIsNone(none_source)

    def test_latest_file_is_by_mtime_not_suffix_order(self):
        # cùng period: hậu tố -10 sort trước -2 theo tên -> phải chọn theo mtime
        stamps = {"": 1_800_000_001, "-2": 1_800_000_002, "-10": 1_800_000_003}
        for suffix in ("", "-2", "-10"):
            path = self.store.save_raw_runs(
                "Feat_Test", f"2026-W05{suffix}", {"runs": [{"run_id": suffix or "base"}]}
            )
            os.utime(path, (stamps[suffix], stamps[suffix]))

        runs, source = load_recorded_runs(STORE, feature="Feat_Test", period="2026-W05")
        self.assertTrue(source.endswith("2026-W05-10.json"), source)
        self.assertEqual(runs[0]["run_id"], "-10")


if __name__ == "__main__":
    unittest.main()
