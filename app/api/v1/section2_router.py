"""Section 2 API — nối solutions (Lane A/B) vào vòng lặp §2.

GET  /section-2/solutions              → danh sách solutions + status
POST /section-2/rerank                 → step 01 (rerank + persist)
POST /section-2/plan                   → step 02 (tạo plan)
GET  /section-2/plans                  → danh sách plans
GET  /section-2/plans/{solution_id}    → 1 plan
POST /section-2/solutions/{id}/status  → chuyển trạng thái (state machine §7)
POST /section-2/report                 → step 05+06+07 (verify + report)
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.core.schemas.solution import SolutionStatus, SOLUTION_TRANSITIONS
from src.core.schemas.measurement import ValidityCheckResult
from src.modules.section_2.section2_service import Section2Service, TransitionError

router = APIRouter(prefix="/section-2", tags=["Section 2"])


def _svc(base_dir: str) -> Section2Service:
    return Section2Service(base_dir)


class RerankRequest(BaseModel):
    base_dir: str = "optimization_data"


class PlanRequest(BaseModel):
    solution_ids: List[str] = Field(..., min_length=1)
    owner: str = "AI Flow Engineer"
    keep_threshold_pct: float = 25.0
    revert_threshold_pct: float = 10.0
    base_dir: str = "optimization_data"


class StatusRequest(BaseModel):
    status: str = Field(..., description="Trạng thái đích theo state machine §7")
    actor: str = "user"
    base_dir: str = "optimization_data"


class ReportRequest(BaseModel):
    solution_id: str
    snapshot_before: str
    snapshot_after: str
    baseline_p50: float = Field(..., gt=0)
    retest_p50: float = Field(..., ge=0)
    validity: ValidityCheckResult
    guardrail_breached: bool = False
    keep_threshold_pct: float = 25.0
    revert_threshold_pct: float = 10.0
    base_dir: str = "optimization_data"


# ------------------------------------------------------------------ solutions
@router.get("/solutions")
def list_solutions(base_dir: str = "optimization_data"):
    sols = _svc(base_dir).list_solutions()
    return {
        "solutions": [s.model_dump(mode="json") for s in sols],
        "status_transitions": SOLUTION_TRANSITIONS,
    }


# ------------------------------------------------------------------ step 01
@router.post("/rerank")
def rerank(request: RerankRequest):
    result = _svc(request.base_dir).rerank(base_dir=request.base_dir)
    return result


# ------------------------------------------------------------------ step 02
@router.post("/plan")
def create_plan(request: PlanRequest):
    try:
        plan = _svc(request.base_dir).create_plan(
            request.solution_ids,
            owner=request.owner,
            thresholds={"keep": request.keep_threshold_pct, "revert": request.revert_threshold_pct},
        )
        return plan
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})


@router.get("/plans")
def list_plans(base_dir: str = "optimization_data"):
    return {"plans": _svc(base_dir).list_plans()}


@router.get("/plans/{solution_id}")
def get_plan(solution_id: str, base_dir: str = "optimization_data"):
    plan = _svc(base_dir).get_plan(solution_id)
    if not plan:
        raise HTTPException(status_code=404, detail={"error": f"Không thấy plan của {solution_id}"})
    return plan


# ------------------------------------------------------------------ transitions
@router.post("/solutions/{solution_id}/status")
def transition(solution_id: str, request: StatusRequest):
    try:
        sol = _svc(request.base_dir).transition(solution_id, request.status, actor=request.actor)
        return sol.model_dump(mode="json")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except TransitionError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})


# ------------------------------------------------------------------ step 05+06+07
@router.post("/report")
def generate_report(request: ReportRequest):
    try:
        result = _svc(request.base_dir).generate_report(
            solution_id=request.solution_id,
            snapshot_before=request.snapshot_before,
            snapshot_after=request.snapshot_after,
            baseline_p50=request.baseline_p50,
            retest_p50=request.retest_p50,
            validity=request.validity,
            guardrail_breached=request.guardrail_breached,
            keep_threshold_pct=request.keep_threshold_pct,
            revert_threshold_pct=request.revert_threshold_pct,
        )
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
