from typing import Tuple, List
from src.core.schemas.baseline import BaselineReport

class GateB1Evaluator:
    """
    Gate B1: Validates auto-discovered candidate bottlenecks from B1
    """
    @staticmethod
    def validate(baseline: BaselineReport, past_reverted_snapshots: List[str]) -> Tuple[bool, List[str]]:
        errors = []
        if baseline.is_weak_baseline:
            errors.append("Gate B1 Failed: Weak baseline detected. Candidate cannot be pushed to B2.")

        if baseline.snapshot_id in past_reverted_snapshots:
            errors.append(f"Gate B1 Failed: Bottleneck from snapshot '{baseline.snapshot_id}' was previously reverted. Skipping duplicate.")

        is_passed = len(errors) == 0
        return is_passed, errors
