import io
import os
import re
import shutil
import zipfile
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence

from pydantic import BaseModel, Field

from src.core.adapters.folder_source import FolderSource, Workload
from src.core.storage.file_store import FileStore

MAX_FILES = 2000
MAX_TOTAL_BYTES = 200 * 1024 * 1024
COPY_CHUNK = 1024 * 1024


class SourceInfo(BaseModel):
    """Một bài test người dùng đưa vào: folder trên máy hoặc tập file đã nạp."""

    source_id: str
    kind: str  # path | upload
    name: str
    folder: str
    created_at: str


class SourcePrepare(BaseModel):
    """Quét folder để người dùng chọn cách chạy test trước khi bấm lane."""

    source: SourceInfo
    mode: str  # recorded | script | empty
    runs_available: int
    scripts: List[Workload]
    suggested_command: Optional[List[str]] = None
    suggested_feature: str
    notes: List[str] = Field(
        default_factory=list,
        description="Cảnh báo khi script có vẻ là web server (benchmark sẽ timeout)",
    )


class SourceService:
    """
    Nhận bài test từ người dùng: dán đường dẫn folder (không copy) hoặc nạp
    file/zip (lưu vào optimization_data/uploads/<id>/). Không bao giờ đọc file
    ngoài folder đã chọn (.env, venv, cache bị bỏ qua sẵn ở FolderSource).
    """

    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()

    # ------------------------------------------------------------- registry ---
    def list_sources(self) -> List[SourceInfo]:
        infos = []
        for name in self.file_store.list_json("sources"):
            payload = self.file_store.read_json("sources", name)
            if payload:
                infos.append(SourceInfo(**payload))
        infos.sort(key=lambda s: s.created_at)
        return infos

    def get(self, source_id: str) -> SourceInfo:
        payload = self.file_store.read_json("sources", f"{source_id}.json")
        if not payload:
            raise FileNotFoundError(
                f"Không tìm thấy nguồn '{source_id}'. Hãy tạo nguồn trước "
                "(from-path hoặc upload) rồi chạy lại."
            )
        return SourceInfo(**payload)

    def _save(self, source_id: str, kind: str, name: str, folder: str) -> SourceInfo:
        info = SourceInfo(
            source_id=source_id,
            kind=kind,
            name=name,
            folder=folder,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.file_store.save_json("sources", source_id, info.model_dump())
        return info

    @staticmethod
    def feature_name(name: str) -> str:
        text = re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_")
        return text[:60] or "source"

    # ----------------------------------------------------------------- path ---
    def from_path(self, path: str, name: Optional[str] = None) -> SourceInfo:
        folder = os.path.abspath(os.path.expanduser(path or "").strip())
        if not os.path.isdir(folder):
            raise FileNotFoundError(f"Không tìm thấy folder: '{path}'")
        key = os.path.normcase(os.path.normpath(folder))
        for existing in self.list_sources():
            if os.path.normcase(os.path.normpath(existing.folder)) == key:
                return existing
        source_id = self.file_store.next_id("sources", "SRC-")
        display = (name or "").strip() or os.path.basename(folder.rstrip("\\/")) or source_id
        return self._save(source_id, "path", display, folder)

    # --------------------------------------------------------------- upload ---
    @staticmethod
    def safe_rel(rel: str) -> str:
        """Đường dẫn tương đối trong upload: không '..', không đĩa tuyệt đối."""
        text = (rel or "").replace("\\", "/").strip()
        if not text:
            raise ValueError("Thiếu đường dẫn file khi nạp.")
        if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
            raise ValueError(f"Đường dẫn tuyệt đối bị chặn: '{rel}'")
        parts = [p for p in text.split("/") if p not in ("", ".")]
        if not parts or any(p == ".." for p in parts):
            raise ValueError(f"Đường dẫn không hợp lệ ('..'): '{rel}'")
        if len(parts) > 20:
            raise ValueError(f"Đường dẫn file quá sâu: '{rel}'")
        return "/".join(parts)

    def _copy(self, fileobj: Any, dst: str) -> int:
        source = getattr(fileobj, "file", fileobj)
        written = 0
        with open(dst, "wb") as out:
            while True:
                chunk = source.read(COPY_CHUNK)
                if not chunk:
                    break
                out.write(chunk)
                written += len(chunk)
        return written

    def from_upload(
        self,
        files: Sequence[Any],
        paths: Optional[Sequence[str]] = None,
        name: Optional[str] = None,
    ) -> SourceInfo:
        files = list(files)
        if not files:
            raise ValueError("Chưa có file nào được nạp.")
        if len(files) > MAX_FILES:
            raise ValueError(f"Quá nhiều file ({len(files)} > {MAX_FILES} file).")

        paths = list(paths or [])
        single = files[0]
        is_zip = (
            len(files) == 1
            and not paths
            and (getattr(single, "filename", "") or "").lower().endswith(".zip")
        )

        source_id = self.file_store.next_id("sources", "SRC-")
        uploads = os.path.join(self.file_store.base_dir, "uploads")
        folder = os.path.join(uploads, source_id)
        os.makedirs(folder, exist_ok=True)

        try:
            if is_zip:
                display = os.path.basename((single.filename or "upload.zip").rstrip("\\/"))
                self._extract_zip(single, folder)
            else:
                total = 0
                for index, item in enumerate(files):
                    rel_raw = paths[index] if index < len(paths) and paths[index] else (
                        getattr(item, "filename", "") or ""
                    )
                    rel = self.safe_rel(rel_raw)
                    dst = os.path.join(folder, *rel.split("/"))
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    total += self._copy(item, dst)
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError(
                            f"Dung lượng nạp vượt giới hạn {MAX_TOTAL_BYTES // (1024 * 1024)} MB."
                        )
                first = self.safe_rel(paths[0] if paths and paths[0] else (files[0].filename or "upload"))
                display = (name or "").strip() or first.split("/")[0]
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

        if not os.listdir(folder):
            shutil.rmtree(folder, ignore_errors=True)
            raise ValueError("Không có file nào được nạp (zip rỗng?).")

        display = (name or "").strip() or display
        return self._save(source_id, "upload", display, folder)

    def _extract_zip(self, upload: Any, folder: str) -> None:
        source = getattr(upload, "file", upload)
        source.seek(0)
        data = source.read()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if len(infos) > MAX_FILES:
                raise ValueError(f"Zip chứa quá nhiều file ({len(infos)} > {MAX_FILES}).")
            if sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
                raise ValueError("Zip giải nén vượt giới hạn dung lượng 200 MB.")
            total = 0
            for info in infos:
                rel = self.safe_rel(info.filename)
                dst = os.path.join(folder, *rel.split("/"))
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                with archive.open(info) as src, open(dst, "wb") as out:
                    while True:
                        chunk = src.read(COPY_CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        total += len(chunk)
                        if total > MAX_TOTAL_BYTES:
                            raise ValueError("Zip giải nén vượt giới hạn dung lượng 200 MB.")
    # -------------------------------------------------------------- prepare ---
    SERVER_MARKERS = ("app.run(", "uvicorn.run(", "socketio.run(", ".launch(", "gradio.")
    BENCH_HINTS = ("bench", "measure", "profile", "perf", "loadtest")

    def prepare(self, source_id: str) -> SourcePrepare:
        source = self.get(source_id)
        folder_source = FolderSource(source.folder)
        scripts = folder_source.list_workloads()
        runs = folder_source.load_runs()
        server_paths = self._server_paths(scripts)
        batch = [w for w in scripts if w.absolute_path not in server_paths]
        hinted = [
            w
            for w in batch
            if any(h in os.path.basename(w.relative_path).lower() for h in self.BENCH_HINTS)
        ]
        candidates = hinted or batch or scripts
        entries = [w for w in candidates if w.kind == "entry"]
        pick = entries or candidates
        suggested = ["{python}", pick[0].relative_path] if pick else None
        mode = "recorded" if runs else ("script" if suggested else "empty")
        notes = self.server_notes(scripts)
        if server_paths and batch:
            notes.append(
                "Lệnh gợi ý đã bỏ qua script web server; chọn lại ô lệnh nếu bạn thực sự "
                "muốn đo server (cần script batch in dòng 'STEP <tên> <ms>')."
            )
        if any(os.path.isdir(os.path.join(source.folder, d)) for d in ("services", "core")):
            notes.append(
                "Folder có services/ hoặc core/: có thể copy templates/bench_driver.py vào "
                "folder làm script đo dùng chung (import thẳng hàm, in STEP, không treo server; "
                "chỉnh khối STEP_SPECS rồi chạy --discover để xem hàm đo được)."
            )
        return SourcePrepare(
            source=source,
            mode=mode,
            runs_available=len(runs),
            scripts=scripts,
            suggested_command=suggested,
            suggested_feature=self.feature_name(source.name),
            notes=notes,
        )

    def _server_paths(self, entries: List[Workload]) -> set:
        paths = set()
        for workload in entries:
            try:
                with open(workload.absolute_path, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(8000)
            except OSError:
                continue
            if any(marker in head for marker in self.SERVER_MARKERS):
                paths.add(workload.absolute_path)
        return paths

    @classmethod
    def server_notes(cls, scripts: List[Workload]) -> List[str]:
        """Cảnh báo script là web server: benchmark chạy sẽ treo tới timeout."""
        notes: List[str] = []
        for workload in scripts:
            try:
                with open(workload.absolute_path, "r", encoding="utf-8", errors="replace") as f:
                    head = f.read(8000)
            except OSError:
                continue
            if any(marker in head for marker in cls.SERVER_MARKERS):
                notes.append(
                    f"{workload.relative_path} có vẻ là web server (gặp app.run/uvicorn/gradio...) — "
                    "chạy benchmark sẽ treo tới timeout. Hãy chọn script chạy batch "
                    "(in ra dòng 'STEP <tên> <ms>') hoặc tự viết script đo."
                )
        return notes
