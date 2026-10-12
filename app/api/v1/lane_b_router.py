from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from src.core.schemas.baseline import BaselineReport
from src.core.schemas.policy import SystemPolicy
from src.core.schemas.solution import SolutionProposal
from src.core.storage.file_store import FileStore
from src.modules.lane_b.domain.proposer_service import SelfCriticismEngine
from src.modules.lane_b.domain.lane_b_service import LaneBService, ScanResult, ProposeResult
from src.modules.lane_b.domain.review_service import ReviewService, VALID_DECISIONS
from src.modules.lane_b.domain.metrics_service import LaneBMetricsService

router = APIRouter(prefix="/lane-b", tags=["Lane B - Automated Discovery Workflow"])


class ScanRequest(BaseModel):
    feature_id: str
    period: str
    runs: List[Dict[str, Any]] = Field(default_factory=list)
    runs_per_week: int = 0
    candidate_periods: Optional[Dict[str, int]] = None
    active_configs: Optional[Dict[str, str]] = None
    base_dir: str = "optimization_data"


class ProposeRequest(BaseModel):
    feature_id: str
    period: str
    baseline: BaselineReport
    proposals: List[SolutionProposal]
    base_dir: str = "optimization_data"


class ReviewDecisionRequest(BaseModel):
    solution_id: str
    decision: str = Field(..., description=" | ".join(VALID_DECISIONS))
    reviewer: str
    reason: Optional[str] = None
    required_changes: Optional[List[str]] = None
    base_dir: str = "optimization_data"


@router.post("/proposal/self-criticism")
async def audit_proposal(proposal: SolutionProposal, policy: SystemPolicy):
    is_passed, rejections = SelfCriticismEngine.audit_proposal(proposal, policy)
    if not is_passed:
        raise HTTPException(status_code=400, detail={"gate": "Gate B2 / Self-Criticism", "rejections": rejections})
    return {"status": "Gate B2 Passed", "proposal": proposal}


@router.post("/scan", response_model=ScanResult)
async def scan(request: ScanRequest):
    """
    B1: scan existing logs only (no test runs), group by fingerprint, detect candidates,
    apply persistence + lessons filters, freeze a baseline snapshot per kept candidate
    and write the observation log (kept and rejected with reasons).
    """
    service = LaneBService(FileStore(request.base_dir))
    result = service.scan(
        feature_id=request.feature_id,
        raw_runs=request.runs,
        period=request.period,
        runs_per_week=request.runs_per_week,
        candidate_periods=request.candidate_periods,
        active_configs=request.active_configs,
    )
    if result.blocked:
        raise HTTPException(
            status_code=409,
            detail={"gate": "B0 Preconditions", "reasons": result.blocked_reasons},
        )
    return result


@router.post("/propose", response_model=ProposeResult)
async def propose(request: ProposeRequest):
    """
    B2: propose only - never applies a change. Hypotheses and over-ceiling ideas stay
    out of the queue; at most top_k packages per period are queued for human review.
    """
    service = LaneBService(FileStore(request.base_dir))
    result = service.propose(
        feature_id=request.feature_id,
        baseline=request.baseline,
        proposals=request.proposals,
        period=request.period,
    )
    if result.blocked:
        raise HTTPException(
            status_code=409,
            detail={"gate": "B0 / Mode Preconditions", "reasons": result.blocked_reasons},
        )
    return result


@router.get("/review/list")
async def list_review_packages(status: Optional[str] = None, base_dir: str = "optimization_data"):
    """Pending queue for the human reviewer (B2-R1: never self-approved)."""
    return {"packages": ReviewService(FileStore(base_dir)).list_packages(status=status)}


@router.get("/review/overdue")
async def overdue_review_packages(base_dir: str = "optimization_data"):
    """Packages past their 2 business-day due date: remind reviewer, then program owner."""
    overdue = ReviewService(FileStore(base_dir)).overdue()
    return {"count": len(overdue), "packages": overdue}


@router.post("/review/decide")
async def decide_review(request: ReviewDecisionRequest):
    """
    Decision on a package. Rejection requires a reason and the reason is appended
    to lessons.jsonl so the same direction is not proposed again without a new condition.
    """
    try:
        package = ReviewService(FileStore(request.base_dir)).decide(
            solution_id=request.solution_id,
            decision=request.decision,
            reviewer=request.reviewer,
            reason=request.reason,
            required_changes=request.required_changes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": str(exc)})
    return package


@router.get("/metrics")
async def lane_b_metrics(base_dir: str = "optimization_data"):
    """Section 9: quality metrics of Lane B itself, each with its denominator."""
    return LaneBMetricsService(FileStore(base_dir)).compute()
