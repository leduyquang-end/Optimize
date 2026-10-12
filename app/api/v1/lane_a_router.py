from fastapi import APIRouter, HTTPException

from src.core.schemas.brief import OptimizationBrief
from src.core.storage.file_store import FileStore
from src.modules.lane_a.domain.lane_a_service import LaneAService
from src.modules.lane_a.gates.gate_1 import Gate1Evaluator

router = APIRouter(prefix="/lane-a", tags=["Lane A - Manual Workflow"])


def _service(base_dir: str) -> LaneAService:
    return LaneAService(FileStore(base_dir))


@router.post("/brief/validate")
async def validate_brief(brief: OptimizationBrief):
    is_passed, logs = Gate1Evaluator.validate(brief)
    if not is_passed:
        raise HTTPException(status_code=400, detail={"gate": "Gate 1", "errors": logs})
    return {"status": "Gate 1 Passed", "brief": brief}


@router.post("/brief", status_code=201)
def create_brief(brief: OptimizationBrief, base_dir: str = "optimization_data"):
    """
    A1: kiểm tra Cổng 1 và lưu Brief (yêu cầu + quy tắc).
    Đạt -> ghi `briefs/BR-2026-xxxx.json` với status=validated và trả brief_id;
    chưa đạt -> 422 kèm danh sách lỗi A1-V1..A1-V6 (không lưu gì cả).
    """
    service = _service(base_dir)
    is_passed, errors = service.process_intake_brief(brief)
    if not is_passed:
        raise HTTPException(status_code=422, detail={"gate": "Gate 1", "errors": errors})
    return {
        "status": "Gate 1 Passed",
        "brief_id": brief.brief_id,
        "brief": service.file_store.read_json("briefs", f"{brief.brief_id}.json"),
    }


@router.get("/briefs")
def list_briefs(base_dir: str = "optimization_data"):
    """Danh sách Brief đã lưu (mới nhất ở cuối)."""
    store = FileStore(base_dir)
    items = [store.read_json("briefs", name) for name in store.list_json("briefs")]
    return {"briefs": [item for item in items if item]}


@router.get("/briefs/{brief_id}")
def get_brief(brief_id: str, base_dir: str = "optimization_data"):
    payload = FileStore(base_dir).read_json("briefs", f"{brief_id}.json")
    if not payload:
        raise HTTPException(status_code=404, detail={"error": f"Không tìm thấy Brief '{brief_id}'."})
    return payload
