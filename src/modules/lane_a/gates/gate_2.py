from typing import Tuple, List
from src.core.schemas.baseline import BaselineReport

class Gate2Evaluator:
    """
    Gate 2 Validation (01_LANE_A_DESIGN.md section 5):
    - A2-V1: All log rows match the exact fingerprint
    - A2-V2: runs >= min_runs (or weak = True with reason)
    - A2-V3: Distribution provided (p50, p90, p99)
    - A2-V4: config_mismatch is empty or explained
    - A2-V5: Second person reproduced the snapshot within tolerance
    - A2-V6: Window contains no config change event
    """
    DEFAULT_MIN_RUNS = 30
    REPLICATION_TOLERANCE_PCT = 1.0

    @classmethod
    def validate(cls, baseline: BaselineReport) -> Tuple[bool, List[str]]:
        errors = []
        warnings = []

        # A2-V1: fingerprint must match on every included row
        if baseline.fingerprint_mismatch_count > 0:
            errors.append(
                f"A2-V1 Failed: {baseline.fingerprint_mismatch_count} log row(s) do not match fingerprint "
                f"'{baseline.fingerprint}'. Not comparable - do not merge."
            )
        if not baseline.fingerprint:
            warnings.append("A2-V1 Warning: No fingerprint recorded on this baseline (FP-3: not comparable).")

        # A2-V2
        if baseline.sample_count < cls.DEFAULT_MIN_RUNS:
            baseline.is_weak_baseline = True
            baseline.weak_baseline_reason = (
                f"Sample count ({baseline.sample_count}) is below min_runs ({cls.DEFAULT_MIN_RUNS})."
            )
            warnings.append(f"A2-V2 Warning: {baseline.weak_baseline_reason}")

        # A2-V3
        if baseline.total_p50_latency_ms <= 0 or baseline.total_p90_latency_ms <= 0 or baseline.total_p99_latency_ms <= 0:
            errors.append("A2-V3 Failed: Baseline must report p50, p90, and p99 distributions.")
        if not baseline.step_breakdowns:
            warnings.append("A2-V3 Warning: No per-step breakdown provided (share by step unknown).")

        # A2-V4
        if baseline.config_mismatch and not baseline.config_mismatch_explained:
            errors.append(
                f"A2-V4 Failed: config_mismatch {baseline.config_mismatch} is not explained. "
                "Find the cause before proceeding."
            )

        # A2-V5
        if baseline.replication_delta_pct is None:
            warnings.append("A2-V5 Warning: Second-person replication not recorded yet.")
        elif baseline.replication_delta_pct > cls.REPLICATION_TOLERANCE_PCT:
            errors.append(
                f"A2-V5 Failed: replication delta {baseline.replication_delta_pct}% exceeds "
                f"{cls.REPLICATION_TOLERANCE_PCT}% tolerance."
            )

        # A2-V6
        if baseline.config_change_in_window:
            errors.append("A2-V6 Failed: Baseline window contains a config change event; pick another window.")

        # Snapshot identity (A2-R6)
        if not baseline.snapshot_id:
            errors.append("A2-V5 Failed: Snapshot ID is missing.")

        # Runtime config captured (A2-R5)
        if not baseline.active_configs:
            errors.append("A2-V4 Failed: Runtime config must be captured.")

        is_passed = len(errors) == 0
        return is_passed, errors + warnings
