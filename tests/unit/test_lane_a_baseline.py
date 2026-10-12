import unittest
from typing import List, Dict, Any

from src.modules.lane_a.domain.lane_a_service import LaneAService


def run(latency: float, steps: Dict[str, float] = None, workload: float = None) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "run_id": "r1",
        "status": "success",
        "latency_ms": latency,
        "steps": steps or {},
    }
    if workload is not None:
        item["workload_ms"] = workload
    return item


class TestBaselineTotals(unittest.TestCase):
    def service(self) -> LaneAService:
        return LaneAService()

    def report(self, runs: List[Dict[str, Any]]):
        return self.service().generate_baseline_report(
            snapshot_id="S-TEST",
            feature_id="Feat",
            raw_log_runs=runs,
            active_configs={},
            time_window_start="2026-10-01",
            time_window_end="2026-10-08",
        )

    def test_workload_ms_wins_when_every_run_has_it(self):
        # wall clock chứa thời gian khởi tạo process (import model ~25s),
        # baseline phải lấy workload (tổng STEP) chứ không lấy startup
        runs = [
            run(27000.0, {"classify": 100.0, "retrieve": 200.0}, workload=300.0),
            run(26000.0, {"classify": 90.0, "retrieve": 190.0}, workload=280.0),
            run(28000.0, {"classify": 110.0, "retrieve": 210.0}, workload=320.0),
        ]
        report, _passed, _logs = self.report(runs)

        self.assertEqual(report.total_p50_latency_ms, 300.0)
        self.assertEqual(report.data_gaps, [])

    def test_runs_without_workload_keep_wall_clock(self):
        runs = [run(40000.0), run(42000.0), run(39000.0)]
        report, _passed, _logs = self.report(runs)

        self.assertEqual(report.total_p50_latency_ms, 40000.0)
        self.assertTrue(any("No per-step timings" in g for g in report.data_gaps))

    def test_mixed_workload_falls_back_to_wall_clock_with_gap(self):
        runs = [
            run(40000.0, {"a": 10.0}, workload=10.0),
            run(42000.0),  # không có workload_ms -> không trộn hai kiểu đo
        ]
        report, _passed, _logs = self.report(runs)

        # p50 của [40000, 42000] theo convention hiện tại = phần tử giữa (42000)
        self.assertEqual(report.total_p50_latency_ms, 42000.0)
        self.assertTrue(any("workload_ms" in g for g in report.data_gaps))


if __name__ == "__main__":
    unittest.main()
