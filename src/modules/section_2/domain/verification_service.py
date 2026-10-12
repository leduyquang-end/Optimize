from enum import Enum
from typing import Dict, Any, Tuple
from pydantic import BaseModel
from src.core.schemas.measurement import MeasurementReport, ValidityCheckResult

class VerificationDecision(str, Enum):
    KEEP = "KEEP"        # Improvement >= 25% and Guardrail OK
    PARTIAL = "PARTIAL"  # Improvement 10%-25%, retry allowed max 2 times
    REVERT = "REVERT"    # Improvement < 10% or Guardrail breached
    INVALID = "INVALID"  # Comparison failed validity checks V-1 to V-6

class RetestResult(BaseModel):
    snapshot_id_before: str
    snapshot_id_after: str
    solution_id: str
    baseline_p50_ms: float
    retest_p50_ms: float
    improvement_pct: float
    validity_checks: ValidityCheckResult
    guardrail_breached: bool = False
    decision: VerificationDecision
    reasoning: str

class VerificationEngine:
    """
    Step 05 & Step 06 Engine (03_SHARED_AND_SECTION_2_DESIGN.md section 12 & 13)
    """
    @staticmethod
    def evaluate_retest(
        solution_id: str,
        snapshot_before: str,
        snapshot_after: str,
        baseline_p50: float,
        retest_p50: float,
        validity: ValidityCheckResult,
        guardrail_breached: bool = False,
        partial_retry_count: int = 0,
        keep_threshold_pct: float = 25.0,
        revert_threshold_pct: float = 10.0
    ) -> RetestResult:
        # Step 05: Check V-1 to V-6
        if not validity.all_passed():
            return RetestResult(
                snapshot_id_before=snapshot_before,
                snapshot_id_after=snapshot_after,
                solution_id=solution_id,
                baseline_p50_ms=baseline_p50,
                retest_p50_ms=retest_p50,
                improvement_pct=0.0,
                validity_checks=validity,
                guardrail_breached=guardrail_breached,
                decision=VerificationDecision.INVALID,
                reasoning="INVALID: One or more validity checks (V-1 to V-6) failed. Find correct comparison pair and re-measure."
            )

        # Calculate improvement %
        if baseline_p50 <= 0:
            improvement_pct = 0.0
        else:
            improvement_pct = ((baseline_p50 - retest_p50) / baseline_p50) * 100.0

        # Step 06: Decision Engine
        if guardrail_breached:
            decision = VerificationDecision.REVERT
            reasoning = "REVERT: Guardrail constraint breached."
        elif improvement_pct >= keep_threshold_pct:
            decision = VerificationDecision.KEEP
            reasoning = f"KEEP: Improvement ({improvement_pct:.1f}%) meets threshold ({keep_threshold_pct}%)."
        elif improvement_pct >= revert_threshold_pct and partial_retry_count < 2:
            decision = VerificationDecision.PARTIAL
            reasoning = f"PARTIAL: Moderate improvement ({improvement_pct:.1f}%). Return to Step 03 for phase adjustment (retry {partial_retry_count + 1}/2)."
        else:
            decision = VerificationDecision.REVERT
            reasoning = f"REVERT: Improvement ({improvement_pct:.1f}%) below threshold ({revert_threshold_pct}%). Immediate rollback."

        return RetestResult(
            snapshot_id_before=snapshot_before,
            snapshot_id_after=snapshot_after,
            solution_id=solution_id,
            baseline_p50_ms=baseline_p50,
            retest_p50_ms=retest_p50,
            improvement_pct=round(improvement_pct, 2),
            validity_checks=validity,
            guardrail_breached=guardrail_breached,
            decision=decision,
            reasoning=reasoning
        )
