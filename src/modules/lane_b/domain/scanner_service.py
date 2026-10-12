from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel
from src.core.schemas.baseline import BaselineReport, StepBreakdown
from src.core.schemas.policy import SystemPolicy, FeatureMode

class CandidateBottleneck(BaseModel):
    step_name: str
    share_time: float
    runs_per_week: int
    stability: float
    headroom: float

    def compute_score(self) -> float:
        """
        Ranker formula (02_LANE_B_DESIGN.md section 5.4):
        score = share_time * runs_per_week * stability * headroom
        """
        norm_runs = min(self.runs_per_week / 1000.0, 1.0)
        return round(self.share_time * norm_runs * self.stability * self.headroom, 4)

class ScannerService:
    """
    Lane B Auto-Scanner & Ranking Engine (B1)
    """
    TAIL_RATIO_THRESHOLD = 3.0
    RETRY_RATE_THRESHOLD = 0.1

    @classmethod
    def detect_bottlenecks(
        cls,
        baseline: BaselineReport,
        share_threshold: float = 0.25,
        tail_ratio_threshold: Optional[float] = None,
        retry_threshold: Optional[float] = None,
    ) -> List[Tuple[StepBreakdown, str]]:
        """
        02_LANE_B_DESIGN.md section 5.1: a step is a candidate when any signal fires
        - time/token share >= share_threshold
        - long tail: p99 / p50 >= tail_ratio_threshold
        - high retry rate >= retry_threshold
        - on the critical path (parallelizable but running sequentially)
        Returns (step, signal) pairs so observations can explain the pick.
        """
        tail_threshold = tail_ratio_threshold or cls.TAIL_RATIO_THRESHOLD
        retry_threshold = retry_threshold or cls.RETRY_RATE_THRESHOLD

        candidates: List[Tuple[StepBreakdown, str]] = []
        for step in baseline.step_breakdowns:
            signals = []
            if (step.pct_of_total_time / 100.0) >= share_threshold:
                signals.append("share")
            if step.p50_latency_ms > 0 and (step.p99_latency_ms / step.p50_latency_ms) >= tail_threshold:
                signals.append("long_tail")
            if step.retry_rate is not None and step.retry_rate >= retry_threshold:
                signals.append("high_retry")
            if step.is_critical_path and step.parallelizable:
                signals.append("sequential_but_parallelizable")

            if signals:
                candidates.append((step, ",".join(signals)))
        return candidates

    @staticmethod
    def filter_persistence(candidate_periods: Dict[str, int], min_periods: int = 2) -> List[str]:
        """
        B1-V4: Must persist over at least min_periods scanning periods
        """
        return [step for step, periods in candidate_periods.items() if periods >= min_periods]

    @staticmethod
    def filter_lessons_learned(candidates: List[str], past_reverted_steps: List[str]) -> List[str]:
        """
        B1-V5 / B1-R6: deduplicate against reverted lessons store
        """
        return [c for c in candidates if c not in past_reverted_steps]

    @staticmethod
    def rank_candidates(candidates: List[CandidateBottleneck], top_k: int = 3) -> List[CandidateBottleneck]:
        """
        Ranks candidates by compute_score() descending and picks top_k
        """
        candidates.sort(key=lambda c: c.compute_score(), reverse=True)
        return candidates[:top_k]

    @staticmethod
    def build_baseline_weak(baseline: BaselineReport, min_runs: int) -> bool:
        """B1-R5: weak baseline (sample_count < min_runs) must not reach B2."""
        return baseline.sample_count < min_runs

class KillSwitchManager:
    """
    Kill Switches & Auto-Downgrade Engine (02_LANE_B_DESIGN.md section 8)
    """
    @staticmethod
    def should_auto_downgrade(
        guardrail_breached: bool,
        loki_data_anomalous: bool,
        feature_revert_rate: float,
        max_revert_rate_threshold: float = 0.2
    ) -> Tuple[bool, str]:
        if guardrail_breached:
            return True, "Auto-downgraded to 'observe': Proposal breached hard guardrail constraint."
        if loki_data_anomalous:
            return True, "Auto-downgraded to 'observe': Loki log data anomaly or missing labels detected."
        if feature_revert_rate > max_revert_rate_threshold:
            return True, (
                f"Auto-downgraded to 'observe': Feature revert rate ({feature_revert_rate:.2f}) "
                f"exceeded threshold ({max_revert_rate_threshold:.2f})."
            )
        return False, "Feature active in 'propose' mode."
