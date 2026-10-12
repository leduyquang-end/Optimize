import json as jsonlib
from typing import List, Optional
from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from src.core.adapters.benchmark_runner import load_recorded_runs
from src.core.adapters.folder_source import FolderSource
from src.core.storage.file_store import FileStore
from src.modules.runner.optimize_service import (
    ConfirmHypothesisRequest,
    OptimizeRequest,
    OptimizeService,
)
from src.modules.runner.source_service import SourceService

router = APIRouter(prefix="/optimize", tags=["optimize"])


class SourcePathRequest(BaseModel):
    path: str = Field(..., description="Đường dẫn folder bài test trên máy server")
    name: Optional[str] = Field(default=None, description="Tên hiển thị (mặc định: tên folder)")


def _sources(base_dir: str) -> SourceService:
    return SourceService(FileStore(base_dir))


# ---------------------------------------------------------------- nguồn (bai test)
@router.post("/sources/from-path", status_code=201)
def create_source_from_path(request: SourcePathRequest, base_dir: str = "optimization_data"):
    """
    Đưa folder trên máy vào làm bài test: không copy dữ liệu, chỉ ghi lại đường dẫn.
    Trả về luôn kết quả quét folder (mode, script, số run sẵn có).
    """
    try:
        service = _sources(base_dir)
        info = service.from_path(request.path, request.name)
        return service.prepare(info.source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})


@router.post("/sources/upload", status_code=201)
def upload_source(
    files: List[UploadFile] = File(..., description="Các file của bài test (kèm paths để giữ cấu trúc thư mục)"),
    paths: Optional[str] = Form(
        default=None,
        description='JSON array đường dẫn tương ứng với từng file, ví dụ ["app.py","data/a.xlsx"]',
    ),
    name: Optional[str] = Form(default=None),
    base_dir: str = "optimization_data",
):
    """
    Nạp file (nhiều file có cấu trúc thư mục, hoặc 1 file .zip) vào
    optimization_data/uploads/<source_id>/. Chặn path traversal, giới hạn 2000 file / 200MB.
    """
    rel_paths: List[str] = []
    if paths:
        try:
            parsed = jsonlib.loads(paths)
        except jsonlib.JSONDecodeError:
            raise HTTPException(status_code=422, detail={"error": 'Trường "paths" phải là JSON array.'})
        if not isinstance(parsed, list):
            raise HTTPException(status_code=422, detail={"error": 'Trường "paths" phải là JSON array.'})
        rel_paths = [str(item) for item in parsed]

    try:
        service = _sources(base_dir)
        info = service.from_upload(files, rel_paths, name)
        return service.prepare(info.source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})


@router.get("/sources")
def list_sources(base_dir: str = "optimization_data"):
    """Các bài test đã đưa vào (folder path hoặc đã nạp file)."""
    return {"sources": [s.model_dump() for s in _sources(base_dir).list_sources()]}


@router.get("/sources/{source_id}")
def get_source(source_id: str, base_dir: str = "optimization_data"):
    """Quét lại một nguồn: mode chạy (recorded/script/empty), script, lệnh gợi ý."""
    try:
        return _sources(base_dir).prepare(source_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})


# ------------------------------------------------------------------------ chạy --
@router.post("/run")
def run_optimization(request: OptimizeRequest):
    """
    Người dùng chọn lane:
    - lane A: số đo -> baseline (Cổng 2) -> bottleneck -> solution/hypothesis (Cổng 3)
    - lane B: số đo -> điều kiện B0 -> scan B1 -> đề xuất B2 (cần policy được duyệt)
    Bị chặn -> 409 kèm lý do (không tự ý bỏ qua điều kiện).
    """
    try:
        result = OptimizeService(FileStore(request.base_dir)).run_optimization(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})

    if result.blocked:
        raise HTTPException(
            status_code=409,
            detail={
                "lane": result.lane,
                "feature_id": result.feature_id,
                "reasons": result.blocked_reasons,
                "blocked_fixes": result.blocked_fixes,
                "notes": result.notes,
                "errors": result.errors,
            },
        )
    return result


@router.post("/hypotheses/{hypothesis_id}/confirm", status_code=200)
def confirm_hypothesis(hypothesis_id: str, request: ConfirmHypothesisRequest):
    """
    Domain owner chốt ĐÚNG 1 biến cấu hình của hypothesis ->
    chuyển hypothesis thành solution chính thức: kiểm lại Cổng 3, cấp ID SOL- mới,
    lưu vào solutions/ (không tự bỏ qua điều kiện — người phải chỉ định biến).
    """
    try:
        return OptimizeService(FileStore(request.base_dir)).confirm_hypothesis(
            hypothesis_id, request.variable, request.reviewer
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)})


@router.get("/workloads")
def list_workloads(folder: str = Query(..., description="Đường dẫn folder mục tiêu trên máy")):
    """Liệt kê script/entry chạy được trong folder mục tiêu (bỏ .venv, cache, __pycache__)."""
    source = FolderSource(folder)
    try:
        source.validate()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail={"error": str(exc)})
    return {"folder": folder, "workloads": [w.model_dump() for w in source.list_workloads()]}


@router.get("/runs")
def list_recorded_runs(
    feature: Optional[str] = None,
    period: Optional[str] = None,
    base_dir: str = "optimization_data",
):
    """Số đo đã ghi trong raw_runs (mới nhất cho feature/period được chỉ định)."""
    runs, source = load_recorded_runs(base_dir, feature=feature, period=period)
    return {
        "source": source,
        "count": len(runs),
        "succeeded": sum(1 for r in runs if r.get("status") == "success"),
        "failed": sum(1 for r in runs if r.get("status") != "success"),
    }
