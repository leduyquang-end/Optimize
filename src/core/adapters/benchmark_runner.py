import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.core.storage.file_store import FileStore

DEFAULT_PREFLIGHT_TIMEOUT_S = 120.0


class BenchmarkSpec(BaseModel):
    """
    Một lần chạy test được dựng lúc chạy (từ source người dùng đưa vào):
    folder nào, lệnh gì, chạy lặp bao nhiêu lần, config nào đang bật.
    """
    benchmark_id: str
    feature: str
    folder: str
    command: List[str] = Field(min_length=1)
    repeats: int = Field(default=30, ge=1, le=10000)
    self_loop: bool = Field(
        default=False,
        description=(
            "Script tự lặp N vòng trong MỘT process, mỗi vòng in STEP <tên> <ms> "
            "rồi RUN <ms> (wall của vòng) -> tách thành N run, chỉ tốn 1 lần khởi tạo"
        ),
    )
    timeout_s: float = Field(default=120.0, gt=0)
    preflight_timeout_s: Optional[float] = Field(
        default=None,
        ge=0,
        description=(
            "Chạy thử 1 lần TRƯỚC N lần đo; fail/không in STEP -> dừng ngay, "
            "không tốn N×timeout. None = mặc định min(120, timeout_s); 0 = bỏ qua preflight."
        ),
    )
    config: Dict[str, str] = Field(default_factory=dict)
    description: str = ""


class BenchmarkOutcome(BaseModel):
    benchmark_id: str
    feature: str
    period: str
    folder: str
    fingerprint: str
    runs_file: Optional[str] = None
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    steps_seen: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    preflight: Optional[Dict[str, Any]] = Field(
        default=None, description="Kết quả chạy thử 1 lần trước N lần đo (nếu có)."
    )


def _file_source(path: str) -> str:
    """config.source của 1 file raw_runs (rỗng nếu file cũ/không ghi)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str((payload.get("config") or {}).get("source") or "")


def load_recorded_runs(
    base_dir: str,
    feature: Optional[str] = None,
    period: Optional[str] = None,
    source: Optional[str] = None,
) -> Tuple[List[Dict[str, object]], Optional[str]]:
    """
    Newest raw_runs file for a feature (or everything when feature is None).
    Khi truyền `source`: chỉ nhận file có config.source trùng (mỗi nguồn bài test
    có số đo riêng — file của nguồn khác không được dùng ngầm).
    """
    root = os.path.join(base_dir, "raw_runs")
    if not os.path.isdir(root):
        return [], None
    candidates: List[Tuple[float, str]] = []
    for entry in sorted(os.listdir(root)):
        folder = os.path.join(root, entry)
        if not os.path.isdir(folder) or (feature and entry != feature):
            continue
        for name in os.listdir(folder):
            if name.endswith(".json") and (period is None or name.startswith(period)):
                path = os.path.join(folder, name)
                if source:
                    file_source = _file_source(path)
                    if file_source and file_source != source:
                        continue
                # xếp theo thời điểm ghi: hậu tố -2/-10 làm thứ tự tên sai
                candidates.append((os.path.getmtime(path), path))
    if not candidates:
        return [], None
    path = max(candidates)[1]
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    runs = payload.get("runs", []) if isinstance(payload, dict) else []
    return runs, path


class BenchmarkRunner:
    """
    Runs a declared command N times inside the target folder and records each
    repetition as a run (latency from wall clock, per-step ms from STEP markers
    printed by the command). Only reads/executes inside the target folder and
    never prints environment files (.env) or secrets.
    """

    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()

    # ---------------------------------------------------------------- helpers --
    STEP_PATTERN = re.compile(r"^\s*STEP\s+([A-Za-z0-9_.\-]+)\s+(-?\d+(?:\.\d+)?)\s*$")
    RUN_PATTERN = re.compile(r"^\s*RUN\s+(\d+(?:\.\d+)?)\s*$")

    @classmethod
    def parse_steps(cls, stdout: str, marker: str = "STEP") -> Dict[str, float]:
        """'STEP read_excel 123.4' -> {'read_excel': 123.4}; repeated markers are summed."""
        pattern = cls.STEP_PATTERN if marker == "STEP" else re.compile(
            rf"^\s*{re.escape(marker)}\s+([A-Za-z0-9_.\-]+)\s+(-?\d+(?:\.\d+)?)\s*$"
        )
        steps: Dict[str, float] = {}
        for line in (stdout or "").splitlines():
            match = pattern.match(line)
            if match:
                name = match.group(1)
                steps[name] = round(steps.get(name, 0.0) + float(match.group(2)), 3)
        return steps

    @classmethod
    def parse_self_loop(cls, stdout: str) -> List[Dict[str, object]]:
        """
        Mode tự lặp: mỗi vòng in các dòng STEP ... rồi kết thúc bằng RUN <ms>
        (wall của vòng do script tự đo) -> tách thành từng run riêng.
        """
        runs: List[Dict[str, object]] = []
        block: Dict[str, float] = {}
        for line in (stdout or "").splitlines():
            run_match = cls.RUN_PATTERN.match(line)
            if run_match:
                runs.append(
                    {
                        "latency_ms": float(run_match.group(1)),
                        "workload_ms": round(sum(block.values()), 3) if block else None,
                        "steps": dict(block),
                    }
                )
                block = {}
                continue
            step_match = cls.STEP_PATTERN.match(line)
            if step_match:
                name = step_match.group(1)
                block[name] = round(block.get(name, 0.0) + float(step_match.group(2)), 3)
        return runs

    def _resolve_command(self, command: List[str], cwd: str) -> List[str]:
        """{python} -> interpreter; path -> toạ độ tuyệt đối; tên trần -> PATH.

        Subprocess chạy với cwd = folder mục tiêu nên mọi path phải là tuyệt đối,
        nếu không sẽ bị hiểu sai (folder tương đối của server ≠ folder tương đối
        của subprocess) và lệnh thất bại ngay "can't open file".
        """
        resolved = []
        for token in command:
            if token == "{python}":
                resolved.append(sys.executable)
                # -u: unbuffered stdout/stderr — preflight timeout vẫn bắt được partial output
                resolved.append("-u")
                continue
            if os.path.isabs(token):
                resolved.append(token)
                continue
            in_folder = os.path.join(cwd, token)
            if os.path.exists(in_folder):
                resolved.append(os.path.abspath(in_folder))
                continue
            # token gõ theo toạ độ tương đối của process server
            # (đã qua validate_command nên vẫn nằm trong folder mục tiêu)
            if (os.sep in token or "/" in token) and os.path.exists(token):
                resolved.append(os.path.abspath(token))
                continue
            resolved.append(token)
        return resolved

    @staticmethod
    def is_interpreter(path: str) -> bool:
        """Trình thông dịch (kể cả venv của dự án) không tính là 'file ngoài folder'."""
        name = os.path.basename(path).lower()
        if name in ("python", "py.exe", "pyw.exe", "pythonw.exe"):
            return True
        return name.startswith("python") and not name.endswith(".py")

    @classmethod
    def validate_command(cls, command: List[str], folder: str) -> None:
        """Mọi path trong lệnh phải nằm trong folder mục tiêu; tên trần dùng PATH."""
        folder_real = os.path.realpath(folder)
        for token in command:
            if token == "{python}":
                continue
            if os.path.isabs(token):
                candidate = os.path.realpath(token)
            elif os.sep in token or "/" in token:
                candidate = os.path.realpath(os.path.join(folder, token))
            else:
                continue  # tên trần (vd: python, pytest) -> tìm trong PATH
            if candidate == sys.executable or cls.is_interpreter(candidate):
                continue
            if os.path.commonpath([folder_real, candidate]) != folder_real:
                raise ValueError(
                    f"Lệnh trỏ ra ngoài folder mục tiêu ('{token}'). "
                    "Chỉ chạy được file nằm trong folder đã chọn."
                )

    @staticmethod
    def fingerprint(spec: BenchmarkSpec) -> str:
        """FP: folder + command + config (same basis -> comparable runs)."""
        basis = {
            "folder": os.path.normcase(os.path.normpath(spec.folder)),
            "command": list(spec.command),
            "config": dict(spec.config),
        }
        return hashlib.sha256(json.dumps(basis, sort_keys=True).encode("utf-8")).hexdigest()[:12]

    # -------------------------------------------------------------------- run --
    @staticmethod
    def tail_stderr(text: str, limit: int = 600) -> str:
        """Giữ PHẦN CUỐI của stderr — dòng lỗi nằm cuối traceback."""
        cleaned = (text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return "…" + cleaned[-limit:]

    def preflight_budget(self, spec: "BenchmarkSpec") -> float:
        if spec.preflight_timeout_s is not None:
            return float(spec.preflight_timeout_s)
        return min(DEFAULT_PREFLIGHT_TIMEOUT_S, spec.timeout_s)

    _DIAGNOSE_PATTERNS = [
        # (regex pattern, chẩn đoán, cách fix)
        (
            r"ModuleNotFoundError: No module named '([^']+)'",
            "Thiếu thư viện Python '{0}' — script import module chưa được cài.",
            "Chạy: pip install {0}  (hoặc thêm vào requirements.txt rồi pip install -r requirements.txt)",
        ),
        (
            r"ImportError: cannot import name '([^']+)' from '([^']+)'",
            "Không tìm thấy '{0}' trong module '{1}' — hàm/class bị đổi tên hoặc xóa.",
            "Kiểm tra {1}.py: hàm '{0}' còn tồn tại không? Nếu đổi tên thì cập nhật import trong script đo.",
        ),
        (
            r"FileNotFoundError: \[Errno 2\] No such file or directory: '([^']+)'",
            "Thiếu file '{0}' — script cần file dữ liệu/model chưa có.",
            "Kiểm tra đường dẫn {0}; có thể cần chạy bước build/ingest trước (ví dụ ingest_knowledge.py, build_kg.py).",
        ),
        (
            r"SyntaxError",
            "Script có lỗi cú pháp Python — không chạy được.",
            "Chạy: python -m py_compile <script.py> để biết dòng lỗi; sửa syntax rồi chạy lại.",
        ),
        (
            r"ConnectionError|ConnectionRefusedError|Cannot connect",
            "Không kết nối được dịch vụ bên ngoài (database, API, server).",
            "Kiểm tra dịch vụ đã chạy chưa (Neo4j, Redis, web server...); hoặc chọn script đo local không cần network.",
        ),
        (
            r"Neo4j|neo4j",
            "Script phụ thuộc Neo4j — cần Neo4j đang chạy.",
            "Khởi động Neo4j, hoặc dùng script đo mode 'rag' local (không cần Neo4j).",
        ),
        (
            r"PermissionError",
            "Không có quyền truy cập file/folder.",
            "Kiểm tra quyền file, hoặc chạy script từ folder có quyền ghi.",
        ),
        (
            r"MemoryError|Killed",
            "Script hết RAM — nạp dữ liệu/model quá lớn.",
            "Giảm batch_size, giảm số mẫu test, hoặc dùng script đo nhỏ hơn.",
        ),
    ]

    def _diagnose(self, info: Dict[str, Any]) -> Dict[str, str]:
        """Phân tích preflight_info → (chẩn đoán, cách fix) cụ thể cho người dùng."""
        combined = (info.get("stderr_tail") or "") + "\n" + (info.get("stdout_tail") or "") + "\n" + (info.get("reason") or "")
        for pattern, diagnosis_tpl, fix_tpl in self._DIAGNOSE_PATTERNS:
            m = re.search(pattern, combined)
            if m:
                args = m.groups() if m.groups() else (m.group(0),)
                return {
                    "diagnosis": diagnosis_tpl.format(*args),
                    "fix": fix_tpl.format(*args),
                }
        # Không khớp pattern nào — phân tích theo loại fail
        if info.get("ok"):
            return {}
        if info.get("exit_code") is not None and info.get("exit_code") != 0:
            return {
                "diagnosis": f"Script thoát với mã lỗi {info['exit_code']}.",
                "fix": "Chạy tay script này trong terminal để xem lỗi đầy đủ, sửa rồi chạy lại benchmark.",
            }
        if "timeout" in (info.get("reason") or "").lower():
            return {
                "diagnosis": "Script treo hoặc khởi tạo quá lâu (import nặng / web server / chờ input).",
                "fix": "Chọn script đo batch in STEP ngay (bench_*.py), hoặc tăng 'Timeout preflight' nếu đúng là import ~25s.",
            }
        if "KHÔNG in dòng" in (info.get("reason") or ""):
            return {
                "diagnosis": "Script chạy hết nhưng không in dòng 'STEP <tên> <ms>' — không có dữ liệu bottleneck.",
                "fix": "Thêm lệnh in STEP vào script (ví dụ: print('STEP classify 12.3')), hoặc dùng driver đo chung templates/bench_driver.py.",
            }
        return {
            "diagnosis": "Không xác định được nguyên nhân cụ thể từ output.",
            "fix": "Chạy tay script trong terminal với cùng lệnh để quan sát, rồi sửa lỗi trước khi benchmark.",
        }

    def _preflight(self, command: List[str], folder: str, timeout_s: float, self_loop: bool) -> Dict[str, Any]:
        """Chạy thử 1 lần với timeout ngắn: fail / không in STEP -> dừng trước N lần đo."""
        started = time.perf_counter()
        info: Dict[str, Any] = {"ok": False, "timeout_s": timeout_s, "exit_code": None, "steps_seen": []}
        try:
            process = subprocess.run(
                command,
                cwd=folder,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            info["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
            # TimeoutExpired.stdout/.stderr chứa output đã nhận được trước khi kill
            partial_out = ""
            partial_err = ""
            if exc.stdout:
                partial_out = exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
            if exc.stderr:
                partial_err = exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
            info["stdout_tail"] = self.tail_stderr(partial_out)
            info["stderr_tail"] = self.tail_stderr(partial_err)
            hint_lines = []
            if partial_out.strip():
                hint_lines.append(f"Script đã in trước khi timeout:\n{self.tail_stderr(partial_out)}")
            if partial_err.strip():
                hint_lines.append(f"stderr:\n{self.tail_stderr(partial_err)}")
            if not partial_out.strip() and not partial_err.strip():
                hint_lines.append("Script không in gì trước khi timeout (khởi tạo treo hoặc import nặng).")
            info["reason"] = (
                f"timeout after {timeout_s:g}s mà chưa in xong 'STEP <tên> <ms>'. "
                + " ".join(hint_lines)
            )
            diag = self._diagnose(info)
            info["diagnosis"] = diag.get("diagnosis", "")
            info["fix"] = diag.get("fix", "")
            return info
        stdout = process.stdout or ""
        steps = self.parse_steps(stdout)
        has_run_marker = bool(self.RUN_PATTERN.search(stdout))
        info["exit_code"] = process.returncode
        info["steps_seen"] = sorted(steps)
        info["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
        if process.returncode != 0:
            info["stderr_tail"] = self.tail_stderr(process.stderr or "")
            info["stdout_tail"] = self.tail_stderr(stdout)
            parts = [f"exit code {process.returncode}."]
            if process.stderr and process.stderr.strip():
                parts.append(f"stderr:\n{self.tail_stderr(process.stderr)}")
            if stdout.strip():
                parts.append(f"stdout:\n{self.tail_stderr(stdout)}")
            info["reason"] = " ".join(parts)
            diag = self._diagnose(info)
            info["diagnosis"] = diag.get("diagnosis", "")
            info["fix"] = diag.get("fix", "")
            return info
        if not steps and not (self_loop and has_run_marker):
            info["stdout_tail"] = self.tail_stderr(stdout)
            shown = self.tail_stderr(stdout) if stdout.strip() else "(trống)"
            info["reason"] = (
                "script chạy hết nhưng KHÔNG in dòng 'STEP <tên> <ms>' nào — "
                "harness sẽ không có dữ liệu bottleneck. Script đã in:\n"
                f"{shown}"
            )
            diag = self._diagnose(info)
            info["diagnosis"] = diag.get("diagnosis", "")
            info["fix"] = diag.get("fix", "")
            return info
        info["ok"] = True
        return info

    def run(self, spec: BenchmarkSpec, period: Optional[str] = None) -> BenchmarkOutcome:
        folder = os.path.abspath(spec.folder)
        if not os.path.isdir(folder):
            raise FileNotFoundError(
                f"Benchmark folder not found: '{spec.folder}'. Nothing was executed."
            )
        period = period or datetime.now(timezone.utc).strftime("%G-W%V")
        self.validate_command(spec.command, folder)
        command = self._resolve_command(spec.command, folder)
        fingerprint = self.fingerprint(spec)

        # Preflight: chạy thử 1 lần trước N lần đo — fail là dừng, không tốn N×timeout
        budget = self.preflight_budget(spec)
        preflight_info: Optional[Dict[str, Any]] = None
        if budget > 0:
            preflight_info = self._preflight(command, folder, budget, spec.self_loop)
            if not preflight_info.get("ok"):
                return BenchmarkOutcome(
                    benchmark_id=spec.benchmark_id,
                    feature=spec.feature,
                    period=period,
                    folder=spec.folder,
                    fingerprint=fingerprint,
                    runs_file=None,
                    total=0,
                    succeeded=0,
                    failed=0,
                    steps_seen=[],
                    errors=[
                        f"Preflight (chạy thử 1 lần, timeout {budget:g}s) thất bại — "
                        "dừng ngay, không chạy tiếp "
                        f"{spec.repeats if not spec.self_loop else 1} lần đo để tránh tốn thời gian. "
                        + str(preflight_info.get("reason") or "lỗi không rõ.")
                        + (f"\n→ Chẩn đoán: {preflight_info['diagnosis']}" if preflight_info.get("diagnosis") else "")
                        + (f"\n→ Cách fix: {preflight_info['fix']}" if preflight_info.get("fix") else "")
                    ],
                    preflight=preflight_info,
                )

        runs: List[Dict[str, object]] = []
        failures: List[Tuple[str, str]] = []  # (run_id, thông điệp lỗi)
        steps_seen = set()
        # self_loop: 1 process tự lặp N vòng -> N run (chỉ tốn 1 lần khởi tạo)
        iterations = 1 if spec.self_loop else spec.repeats

        for index in range(iterations):
            run_id = f"r{index + 1}"
            started = time.perf_counter()
            stdout, stderr, status = "", "", "success"
            try:
                process = subprocess.run(
                    command,
                    cwd=folder,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=spec.timeout_s,
                )
                stdout = process.stdout or ""
                stderr = process.stderr or ""
                if process.returncode != 0:
                    status = "failed"
                    failures.append(
                        (run_id, f"exit code {process.returncode}: {self.tail_stderr(stderr)}")
                    )
            except subprocess.TimeoutExpired:
                status = "failed"
                failures.append((run_id, f"timeout after {spec.timeout_s}s"))
            except OSError as exc:
                raise RuntimeError(f"Cannot execute benchmark command {command}: {exc}")

            process_ms = round((time.perf_counter() - started) * 1000.0, 3)

            if status != "success":
                runs.append(self.make_run(run_id, fingerprint, spec, process_ms, None, {}, status))
                continue

            if spec.self_loop:
                loop_runs = self.parse_self_loop(stdout)
                if not loop_runs:
                    failures.append(
                        (
                            run_id,
                            "mode tự lặp: không tìm thấy dòng 'RUN <ms>' — mỗi vòng phải in "
                            "các dòng STEP <tên> <ms> rồi kết thúc bằng RUN <ms>.",
                        )
                    )
                    runs.append(self.make_run(run_id, fingerprint, spec, process_ms, None, {}, "failed"))
                    continue
                for item in loop_runs:
                    steps_seen.update(item["steps"])
                    runs.append(
                        self.make_run(
                            f"r{len(runs) + 1}",
                            fingerprint,
                            spec,
                            float(item["latency_ms"]),
                            item["workload_ms"],
                            item["steps"],
                        )
                    )
                continue

            steps = self.parse_steps(stdout)
            steps_seen.update(steps)
            # workload_ms = tổng STEP, tách khỏi thời gian khởi tạo process
            workload_ms = round(sum(steps.values()), 3) if steps else None
            runs.append(self.make_run(run_id, fingerprint, spec, process_ms, workload_ms, steps))

        payload = {
            "benchmark_id": spec.benchmark_id,
            "feature": spec.feature,
            "period": period,
            "command": command,
            "fingerprint": fingerprint,
            "config": dict(spec.config),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runs": runs,
        }
        path = self.file_store.save_raw_runs(spec.feature, period, payload)

        return BenchmarkOutcome(
            benchmark_id=spec.benchmark_id,
            feature=spec.feature,
            period=period,
            folder=spec.folder,
            fingerprint=fingerprint,
            runs_file=path,
            total=len(runs),
            succeeded=sum(1 for r in runs if r["status"] == "success"),
            failed=sum(1 for r in runs if r["status"] != "success"),
            steps_seen=sorted(steps_seen),
            errors=self.group_failures(failures),
            preflight=preflight_info,
        )

    @staticmethod
    def make_run(
        run_id: str,
        fingerprint: str,
        spec: BenchmarkSpec,
        latency_ms: float,
        workload_ms: Optional[float],
        steps: Dict[str, float],
        status: str = "success",
    ) -> Dict[str, object]:
        return {
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "latency_ms": latency_ms,
            "workload_ms": workload_ms,
            "status": status,
            "fingerprint": fingerprint,
            "config": dict(spec.config),
            "steps": steps,
        }

    @staticmethod
    def group_failures(failures: List[Tuple[str, str]]) -> List[str]:
        """Gộp các run lỗi giống hệt nhau: 'run r1,r2,r3: exit code 1: ...'."""
        order: List[str] = []
        grouped: Dict[str, List[str]] = {}
        for run_id, message in failures:
            if message not in grouped:
                grouped[message] = []
                order.append(message)
            grouped[message].append(run_id)
        return [f"run {','.join(grouped[m])}: {m}" for m in order]
