from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from src.core.schemas.measurement import ValidityCheckResult
from src.modules.section_2.domain.verification_service import VerificationEngine, RetestResult

router = APIRouter(prefix="/section-2", tags=["Section 2 - Verification Engine"])

class RetestEvaluateRequest(BaseModel):
    solution_id: str
    snapshot_before: str
    snapshot_after: str
    baseline_p50: float = Field(..., gt=0)
    retest_p50: float = Field(..., ge=0)
    validity: ValidityCheckResult
    guardrail_breached: bool = False
    partial_retry_count: int = 0
    keep_threshold_pct: float = 25.0
    revert_threshold_pct: float = 10.0

@router.post("/retest/evaluate", response_model=RetestResult)
async def evaluate_retest(request: RetestEvaluateRequest):
    """
    Step 05 & 06: run validity checks V-1..V-6 first, then KEEP / PARTIAL / REVERT / INVALID.
    """
    return VerificationEngine.evaluate_retest(
        solution_id=request.solution_id,
        snapshot_before=request.snapshot_before,
        snapshot_after=request.snapshot_after,
        baseline_p50=request.baseline_p50,
        retest_p50=request.retest_p50,
        validity=request.validity,
        guardrail_breached=request.guardrail_breached,
        partial_retry_count=request.partial_retry_count,
        keep_threshold_pct=request.keep_threshold_pct,
        revert_threshold_pct=request.revert_threshold_pct
    )
