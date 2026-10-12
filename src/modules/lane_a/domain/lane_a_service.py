from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from src.core.schemas.brief import OptimizationBrief, OptimizationTarget, Guardrail, Threshold, RiskTier, RISK_TIER_ORDER
from src.core.schemas.baseline import BaselineReport, StepBreakdown
from src.core.schemas.solution import SolutionProposal, VerifiedRootCause
from src.core.storage.file_store import FileStore
from src.modules.lane_a.gates.gate_1 import Gate1Evaluator
from src.modules.lane_a.gates.gate_2 import Gate2Evaluator
from src.modules.lane_a.gates.gate_3 import Gate3Evaluator

class LaneAService:
    """
    Domain service orchestrating Lane A Workflow (A1 Intake -> A2 Baseline -> A3 Solutions)
    """
    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()

    def process_intake_brief(self, brief: OptimizationBrief) -> Tuple[bool, List[str]]:
        """
        A1 Intake: Validate Brief against Gate 1 and persist if valid
        """
        is_passed, errors = Gate1Evaluator.validate(brief)
        if is_passed:
            brief.brief_id = brief.brief_id or self.file_store.next_id("briefs", "BR-2026-")
            brief.status = "validated"
            self.file_store.save_brief(brief.brief_id, brief.model_dump())
        return is_passed, errors

    @staticmethod
    def compute_step_breakdowns(raw_log_runs: List[Dict[str, Any]]) -> List[StepBreakdown]:
        """
        A2: per-step breakdown computed from the actual per-step timings carried by the
        source runs (run["steps"] = {step_name: ms}). No per-step timings -> empty list
        (the step share stays unknown instead of being invented).
        """
        per_step: Dict[str, List[float]] = {}
        for run in raw_log_runs:
            steps = run.get("steps")
            if isinstance(steps, dict):
                for name, value in steps.items():
                    try:
                        per_step.setdefault(str(name), []).append(float(value))
                    except (TypeError, ValueError):
                        continue

        stats: List[Tuple[str, float, float, float, int]] = []
        for name, values in per_step.items():
            values = sorted(values)
            p50 = values[int(len(values) * 0.5)]
            p90 = values[min(int(len(values) * 0.9), len(values) - 1)]
            p99 = values[min(int(len(values) * 0.99), len(values) - 1)]
            stats.append((name, p50, p90, p99, len(values)))
        if not stats:
            return []

        stats.sort(key=lambda item: -item[1])
        total_p50 = sum(item[1] for item in stats) or 1.0
        critical_step = stats[0][0]
        return [
            StepBreakdown(
                step_name=name,
                pct_of_total_time=round(p50 / total_p50 * 100.0, 4),
                p50_latency_ms=p50,
                p90_latency_ms=p90,
                p99_latency_ms=p99,
                is_critical_path=(name == critical_step),
            )
            for name, p50, p90, p99, _count in stats
        ]

    def generate_baseline_report(
        self,
        snapshot_id: str,
        feature_id: str,
        raw_log_runs: List[Dict[str, Any]],
        active_configs: Dict[str, str],
        time_window_start: str,
        time_window_end: str,
        fingerprint: Optional[str] = None,
        created_by: str = "lane_a",
        brief_id: Optional[str] = None,
    ) -> Tuple[BaselineReport, bool, List[str]]:
        """
        A2 Baseline: Clean samples, calculate p50/p90/p99 distributions, freeze immutable Snapshot ID
        """
        # Clean samples (filter incidents/deploys) - A2-R3, every exclusion carries a reason
        excluded = [
            {"reason": r.get("exclusion_reason", r.get("status", "unknown")), "runs": 1}
            for r in raw_log_runs if r.get("status") != "success"
        ]
        cleaned_runs = [r for r in raw_log_runs if r.get("status") == "success"]
        sample_count = len(cleaned_runs)

        # Calculate distributions
        # workload_ms = tổng STEP (chỉ phần đo được); thiếu thì lấy wall clock
        workload_values = [
            float(r["workload_ms"])
            for r in cleaned_runs
            if isinstance(r.get("workload_ms"), (int, float))
        ]
        data_gaps: List[str] = []
        if cleaned_runs and len(workload_values) == len(cleaned_runs):
            latencies = sorted(workload_values)
        else:
            if workload_values:
                data_gaps.append(
                    "Một số run có workload_ms, số khác không -> dùng wall clock "
                    "cho đồng nhất (không trộn hai kiểu đo)."
                )
            latencies = sorted([r["latency_ms"] for r in cleaned_runs]) if cleaned_runs else [0.0]
        p50 = latencies[int(len(latencies) * 0.5)]
        p90 = latencies[min(int(len(latencies) * 0.9), len(latencies) - 1)]
        p99 = latencies[min(int(len(latencies) * 0.99), len(latencies) - 1)]

        step_breakdowns = self.compute_step_breakdowns(cleaned_runs)
        if not step_breakdowns:
            data_gaps.append(
                "No per-step timings in the source runs: share by step is unknown (not estimated)."
            )

        report = BaselineReport(
            snapshot_id=snapshot_id,
            feature_id=feature_id,
            fingerprint=fingerprint,
            time_window_start=time_window_start,
            time_window_end=time_window_end,
            sample_count=sample_count,
            excluded_runs=excluded,
            total_p50_latency_ms=p50,
            total_p90_latency_ms=p90,
            total_p99_latency_ms=p99,
            step_breakdowns=step_breakdowns,
            active_configs=active_configs,
            data_gaps=data_gaps,
            created_by=created_by,
            brief_id=brief_id,
        )

        is_passed, gate_logs = Gate2Evaluator.validate(report)
        if is_passed:
            self.file_store.save_snapshot(snapshot_id, report.model_dump())

        return report, is_passed, gate_logs

    def build_solution_proposal(self, proposal: SolutionProposal) -> Tuple[bool, List[str]]:
        """
        A3 Solution Builder: Validate Solution Proposal against Gate 3 and persist if valid
        """
        is_passed, errors = Gate3Evaluator.validate(proposal)
        if is_passed:
            self.file_store.save_solution(proposal.solution_id, proposal.model_dump())
        return is_passed, errors

    @staticmethod
    def order_solutions(
        proposals: List[SolutionProposal]
    ) -> Tuple[List[SolutionProposal], List[SolutionProposal]]:
        """
        A3-R7: main list ordered by risk tier (config -> prompt -> code), then effort.
        Hypotheses (A3-V6) are returned separately and never enter the main list.
        """
        effort_order = {"s": 0, "m": 1, "l": 2, "small": 0, "medium": 1, "large": 2}

        def sort_key(proposal: SolutionProposal):
            effort = effort_order.get(str(proposal.effort_estimate).strip().lower(), 9)
            return (RISK_TIER_ORDER[proposal.risk_tier], effort, proposal.solution_id)

        main = [p for p in proposals if not p.is_unverified_hypothesis]
        hypotheses = [p for p in proposals if p.is_unverified_hypothesis]
        main.sort(key=sort_key)
        return main, hypotheses
