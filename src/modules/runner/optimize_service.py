import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.core.adapters.benchmark_runner import (
    BenchmarkOutcome,
    BenchmarkRunner,
    BenchmarkSpec,
    load_recorded_runs,
)
from src.core.adapters.folder_source import FolderSource
from src.core.schemas.brief import RiskTier
from src.core.schemas.baseline import BaselineReport
from src.core.schemas.solution import ChangeDescription, ProsCons, SolutionProposal, VerifiedRootCause
from src.core.storage.file_store import FileStore
from src.modules.lane_a.domain.lane_a_service import LaneAService
from src.modules.lane_a.gates.gate_3 import Gate3Evaluator
from src.modules.lane_b.domain.lane_b_service import LaneBService
from src.modules.lane_b.domain.scanner_service import ScannerService
from src.modules.runner.source_service import SourceService

MIN_PCT_FOR_HYPOTHESIS = 1.0
DEFAULT_REPEATS = 5
DEFAULT_TIMEOUT_S = 120.0


class OptimizeRequest(BaseModel):
    """Người dùng chọn lane; số đo lấy từ nguồn (folder/path/upload) do người dùng đưa vào."""

    lane: str = Field(..., description="A = thủ công (baseline -> solutions), B = tự động (scan -> propose)")
    source_id: str = Field(..., description="Nguồn đã tạo qua /optimize/sources/from-path hoặc /upload")
    brief_id: Optional[str] = Field(
        default=None,
        description="Bắt buộc với lane A: Optimization Brief đã qua Cổng 1 (POST /lane-a/brief)",
    )
    command: Optional[List[str]] = Field(
        default=None,
        description='Lệnh chạy test trong folder nguồn, ví dụ ["{python}", "main.py"]; bỏ trống thì dùng lệnh gợi ý',
    )
    feature_id: Optional[str] = None
    period: Optional[str] = None
    run_benchmark: bool = Field(default=False, description="True: chạy lệnh test trong folder nguồn trước khi phân tích")
    repeats: Optional[int] = Field(
        default=None, ge=1, description="Số lần lặp khi run_benchmark=true (mặc định 5)"
    )
    timeout_s: Optional[float] = Field(
        default=None,
        gt=0,
        le=1800,
        description="Timeout cho MỖI lần lặp (giây), mặc định 120; tăng lên nếu workload khởi tạo nặng",
    )
    self_loop: bool = Field(
        default=False,
        description=(
            "Script tự lặp N vòng trong 1 process (mỗi vòng in STEP ... rồi RUN <ms>) "
            "-> N run từ 1 lần khởi tạo; bỏ qua repeats"
        ),
    )
    preflight_timeout_s: Optional[float] = Field(
        default=None,
        ge=0,
        le=600,
        description=(
            "Chạy thử 1 lần trước N lần đo (mặc định min(120, timeout_s)); "
            "0 = bỏ qua preflight. Fail/không in STEP -> dừng ngay."
        ),
    )
    base_dir: str = "optimization_data"


class ConfirmHypothesisRequest(BaseModel):
    """Domain owner chốt ĐÚNG 1 biến cấu hình -> hypothesis nâng thành solution chính (A3-V6)."""

    variable: str = Field(..., min_length=1, description="Tên biến cấu hình duy nhất do domain owner xác nhận")
    reviewer: Optional[str] = Field(default=None, description="Tên người/domain owner xác nhận")
    base_dir: str = "optimization_data"


class BottleneckInfo(BaseModel):
    step_name: str
    pct_of_total_time: float
    p50_latency_ms: float
    p90_latency_ms: float
    p99_latency_ms: float
    signals: str


class OptimizeResult(BaseModel):
    lane: str
    feature_id: str
    period: str
    brief_id: Optional[str] = None
    blocked: bool = False
    blocked_reasons: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    benchmark: Optional[BenchmarkOutcome] = None
    runs_source: Optional[str] = None
    runs_used: int = 0
    fingerprint: Optional[str] = None
    baseline: Optional[Dict[str, Any]] = None
    gate2_passed: Optional[bool] = None
    gate2_logs: List[str] = Field(default_factory=list)
    bottlenecks: List[BottleneckInfo] = Field(default_factory=list)
    solutions: List[Dict[str, Any]] = Field(default_factory=list)
    hypotheses: List[Dict[str, Any]] = Field(default_factory=list)
    scan: Optional[Dict[str, Any]] = None
    propose: Optional[Dict[str, Any]] = None


class OptimizeService:
    """
    Entry point where the user chooses Lane A or Lane B (03_SHARED... section 2):
    - data: a local folder (either run it now via benchmark, or read recorded runs)
    - Lane A: baseline (Gate 2) -> bottlenecks -> solutions/hypotheses (Gate 3 checked)
    - Lane B: preconditions (B0) -> scan (B1) -> propose (B2, needs an approved policy)
    Lane B never applies a change; blocked conditions are reported, not bypassed.
    """

    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()
        self.base_dir = self.file_store.base_dir
        self.lane_a = LaneAService(self.file_store)
        self.lane_b = LaneBService(self.file_store)
        self.sources = SourceService(self.file_store)

    # ------------------------------------------------------------------ data --
    def _acquire_runs(
        self, request: OptimizeRequest
    ) -> Tuple[str, str, List[Dict[str, object]], Optional[str], Optional[BenchmarkOutcome], List[str]]:
        period = request.period or datetime.now(timezone.utc).strftime("%G-W%V")
        source = self.sources.get(request.source_id)
        feature = (request.feature_id or "").strip() or SourceService.feature_name(source.name)
        warnings: List[str] = []

        if request.run_benchmark:
            command = list(request.command or [])
            if not command:
                command = list(self.sources.prepare(source.source_id).suggested_command or [])
            if not command:
                raise ValueError(
                    f"Folder '{source.name}' không có script nào để chạy. "
                    'Truyền "command", ví dụ ["{python}", "main.py"].'
                )
            spec = BenchmarkSpec(
                benchmark_id=f"BM-{source.source_id}",
                feature=feature,
                folder=source.folder,
                command=command,
                repeats=request.repeats if request.repeats is not None else DEFAULT_REPEATS,
                timeout_s=float(request.timeout_s) if request.timeout_s else DEFAULT_TIMEOUT_S,
                self_loop=bool(request.self_loop),
                preflight_timeout_s=(
                    float(request.preflight_timeout_s)
                    if request.preflight_timeout_s is not None
                    else None
                ),
                config={"source": source.source_id},
            )
            outcome = BenchmarkRunner(self.file_store).run(spec, period=period)
            runs: List[Dict[str, object]] = []
            if outcome.runs_file:
                with open(outcome.runs_file, "r", encoding="utf-8") as f:
                    runs = json.load(f).get("runs", [])
            return feature, period, runs, outcome.runs_file, outcome, warnings

        folder_runs = FolderSource(source.folder).load_runs()
        if folder_runs:
            return feature, period, folder_runs, os.path.join(source.folder, "runs.*"), None, warnings

        recorded, recorded_source = load_recorded_runs(
            self.base_dir, feature=feature, period=request.period, source=request.source_id or None
        )
        if not recorded:
            other, other_path = load_recorded_runs(
                self.base_dir, feature=feature, period=request.period
            )
            if other_path:
                other_src = (
                    str((other[0].get("config") or {}).get("source") or "?") if other else "?"
                )
                warnings.append(
                    f"File số đo mới nhất trong raw_runs ({other_path}) thuộc nguồn {other_src} — "
                    f"không dùng cho {request.source_id}. Hãy chạy benchmark cho nguồn này "
                    "hoặc chọn đúng nguồn bài test."
                )
        return feature, period, recorded, recorded_source, None, warnings

    @staticmethod
    def _active_configs(runs: List[Dict[str, object]]) -> Dict[str, str]:
        configs: Dict[str, str] = {}
        for run in runs:
            config = run.get("config")
            if isinstance(config, dict):
                configs.update({str(k): str(v) for k, v in config.items()})
        return configs

    # -------------------------------------------------------------- solutions --
    @staticmethod
    def _evidence_lines(runs: List[Dict[str, object]], step_name: str, source: str, limit: int = 3) -> List[str]:
        lines = []
        for run in runs[:limit]:
            steps = run.get("steps") or {}
            value = steps.get(step_name)
            workload = run.get("workload_ms")
            total = workload if isinstance(workload, (int, float)) else run.get("latency_ms")
            suffix = f"{step_name}={value}ms" if value is not None else "per-step timing n/a"
            lines.append(
                f"{os.path.basename(str(source or 'runs'))}#{run.get('run_id')}: "
                f"total={total}ms status={run.get('status')} {suffix}"
            )
        return lines

    def _build_hypothesis(
        self,
        step,
        signals: str,
        baseline,
        runs: List[Dict[str, object]],
        source: str,
        lane: str,
    ) -> SolutionProposal:
        pct = round(step.pct_of_total_time, 2)
        # Hypothesis không nằm trong solutions/ (A3-V6) nên ID lấy theo thư mục
        # riêng "hypotheses/" — mỗi lần sinh là 1 file mới, ID tăng dần, không trùng.
        solution_id = self.file_store.next_id("hypotheses", "HYP-")
        statement = (
            f"Bước '{step.step_name}' chiếm {pct}% tổng thời gian p50 "
            f"({step.p50_latency_ms:.1f}/{baseline.total_p50_latency_ms:.1f} ms) "
            f"trên {baseline.sample_count} run đo được (fingerprint {baseline.fingerprint}); "
            f"tín hiệu: {signals}"
        )
        proposed_change = (
            f"Giảm thời gian của bước '{step.step_name}': domain owner chỉ định 1 biến cấu hình "
            f"duy nhất của bước này (ví dụ giới hạn số vòng lặp/đọc bớt dữ liệu), "
            f"rồi đo lại so với snapshot {baseline.snapshot_id}."
        )
        proposal = SolutionProposal(
            solution_id=solution_id,
            feature_id=baseline.feature_id,
            source_lane=lane,
            snapshot_id=baseline.snapshot_id,
            verified_root_cause=VerifiedRootCause(
                statement=statement,
                evidence_log_lines=self._evidence_lines(runs, step.step_name, source),
            ),
            proposed_change=proposed_change,
            change=ChangeDescription(
                description=proposed_change,
                variables=[step.step_name],
                risk_tier=RiskTier.CONFIG,
                blast_radius=step.step_name,
            ),
            risk_tier=RiskTier.CONFIG,
            blast_radius=step.step_name,
            pros=[f"Nếu bước '{step.step_name}' về 0 ms thì p50 tổng giảm tới {pct}% (giới hạn lý thuyết)"],
            cons=["Chưa xác định được biến cấu hình thật: không áp dụng trước khi domain owner xác nhận"],
            pros_cons=[
                ProsCons(
                    criterion="latency_p50_ms",
                    pros=f"0% đến -{pct}% (bằng 0 nếu bước bị loại hoàn toàn)",
                    cons="chưa đo được khi chưa đổi biến",
                ),
                ProsCons(
                    criterion="quality_score",
                    pros="không đổi (chưa áp thay đổi)",
                    cons="giảm quá sâu có thể mất dữ liệu đầu vào của bước sau",
                ),
            ],
            expected_impact_range=f"0% to -{pct}%",
            effort_estimate="M",
            retest_plan=(
                f"Chạy lại benchmark cùng fingerprint, so với {baseline.snapshot_id}, "
                f"tối thiểu 30 run, chỉ đổi 1 biến"
            ),
            rollback_plan=f"Đưa biến của '{step.step_name}' về giá trị hiện tại trong {baseline.snapshot_id}",
            confidence_score=0.5,
            confidence_level="low",
            is_unverified_hypothesis=True,
        )
        self.file_store.save_json("hypotheses", solution_id, proposal.model_dump())
        return proposal

    # ------------------------------------------------------------------ brief --
    def resolve_brief(self, brief_id: Optional[str]) -> Tuple[str, List[str]]:
        """A1: lane A chỉ chạy với Brief đã qua Cổng 1 (status=validated)."""
        text = (brief_id or "").strip()
        if not text:
            return "", [
                "Lane A cần Optimization Brief đã qua Cổng 1 (A1): hãy nhập yêu cầu & quy tắc "
                "(khối ② Brief) rồi bấm 'Kiểm tra & lưu Brief' trước khi chạy."
            ]
        payload = self.file_store.read_json("briefs", f"{text}.json")
        if not payload:
            raise FileNotFoundError(f"Không tìm thấy Brief '{text}' trong briefs/.")
        if payload.get("status") != "validated":
            return text, [
                f"Brief '{text}' chưa qua Cổng 1 (status={payload.get('status')}). "
                "Hãy kiểm tra lại Brief rồi lưu lại."
            ]
        return text, []

    # ------------------------------------------------- xác nhận hypothesis --
    def confirm_hypothesis(
        self, hypothesis_id: str, variable: str, reviewer: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        A3-V6: hypothesis chỉ được chuyển vào danh sách solution chính khi
        domain owner chốt ĐÚNG 1 biến cấu hình. Lúc đó: gắn biến thật,
        bỏ cờ hypothesis, kiểm lại Cổng 3, cấp ID SOL- mới và lưu solutions/.
        """
        hid = (hypothesis_id or "").strip()
        payload = self.file_store.read_json("hypotheses", f"{hid}.json")
        if not payload:
            raise FileNotFoundError(f"Không tìm thấy hypothesis '{hid}' trong hypotheses/.")
        if payload.get("confirmed_solution_id"):
            raise ValueError(f"Hypothesis '{hid}' đã được chốt thành '{payload['confirmed_solution_id']}'.")
        var = (variable or "").strip()
        if not var:
            raise ValueError("Cần nhập ĐÚNG 1 tên biến cấu hình do domain owner chốt.")
        who = (reviewer or "").strip() or "domain-owner"
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        proposal = SolutionProposal(**payload)
        step_name = (proposal.change.variables or ["?"])[0]
        proposal.change.variables = [var]
        proposal.change.description = (
            f"Đổi biến cấu hình '{var}' của bước '{step_name}' để giảm thời gian bước này; "
            f"domain owner '{who}' đã chốt lúc {stamp}."
        )
        proposal.verified_root_cause.statement += (
            f"; domain owner '{who}' chốt biến cấu hình '{var}' lúc {stamp} (A3-V6)."
        )
        proposal.verified_root_cause.evidence_log_lines.append(
            f"domain owner {who}: chốt biến '{var}' cho {hid} lúc {stamp}"
        )
        proposal.is_unverified_hypothesis = False
        new_id = self.file_store.next_id("solutions", "SOL-")
        proposal.solution_id = new_id

        passed, errors = Gate3Evaluator.validate(proposal)
        if not passed:
            raise ValueError("Cổng 3 chưa qua sau khi chốt biến: " + "; ".join(errors))

        self.file_store.save_solution(new_id, proposal.model_dump())
        payload["confirmed_solution_id"] = new_id
        payload["confirmed_variable"] = var
        payload["confirmed_by"] = who
        self.file_store.save_json("hypotheses", hid, payload)
        return {
            "hypothesis_id": hid,
            "solution_id": new_id,
            "variable": var,
            "reviewer": who,
            "gate3": {"passed": passed, "errors": errors},
            "solution": proposal.model_dump(),
        }

    def _saved_solutions(self, feature_id: str) -> List[Dict[str, Any]]:
        """Solution chính thức đã chốt (qua confirm_hypothesis) của cùng feature."""
        out: List[Dict[str, Any]] = []
        for name in self.file_store.list_json("solutions"):
            payload = self.file_store.read_json("solutions", name) or {}
            if payload.get("feature_id") != feature_id or payload.get("is_unverified_hypothesis"):
                continue
            out.append(payload)
        return out

    def _confirmed_steps(self, feature_id: str) -> List[str]:
        """Tên các bước đã có hypothesis được domain owner chốt -> không sinh trùng."""
        steps: List[str] = []
        for name in self.file_store.list_json("hypotheses"):
            payload = self.file_store.read_json("hypotheses", name) or {}
            if not payload.get("confirmed_solution_id"):
                continue
            if payload.get("feature_id") != feature_id:
                continue
            for var in (payload.get("change") or {}).get("variables") or []:
                if var not in steps:
                    steps.append(var)
        return steps

    # ------------------------------------------------------------------ run ----
    def run_optimization(self, request: OptimizeRequest) -> OptimizeResult:
        lane = (request.lane or "").strip().upper()
        if lane not in {"A", "B"}:
            raise ValueError(f"lane must be 'A' or 'B' (got '{request.lane}')")

        brief_id = ""
        if lane == "A":
            brief_id, brief_blockers = self.resolve_brief(request.brief_id)
            if brief_blockers:
                period = request.period or datetime.now(timezone.utc).strftime("%G-W%V")
                return OptimizeResult(
                    lane="A",
                    feature_id="",
                    period=period,
                    brief_id=brief_id or None,
                    blocked=True,
                    blocked_reasons=brief_blockers,
                )

        feature_id, period, runs, runs_source, benchmark, run_warnings = self._acquire_runs(request)
        result = OptimizeResult(
            lane=lane,
            feature_id=feature_id,
            period=period,
            brief_id=brief_id or None,
            benchmark=benchmark,
            runs_source=runs_source,
            runs_used=len(runs),
        )
        result.notes.extend(run_warnings)

        if benchmark is not None:
            result.errors.extend(benchmark.errors)
            result.notes.append(
                f"Benchmark {benchmark.benchmark_id}: {benchmark.succeeded}/{benchmark.total} run thành công "
                f"(fingerprint {benchmark.fingerprint})."
            )

        if not runs:
            result.blocked = True
            preflight = (benchmark.preflight if benchmark else None) or {}
            if preflight.get("ok") is False:
                result.blocked_reasons.append(
                    "Preflight (chạy thử 1 lần) thất bại nên chưa có số đo nào — "
                    "xem 'Lỗi benchmark' ở kết quả để biết vì sao script không đo được "
                    "(thường: web server, import lỗi, hoặc không in dòng 'STEP <tên> <ms>')."
                )
            else:
                result.blocked_reasons.append(
                    "Chưa có số đo của nguồn này: chạy với run_benchmark=true (cần script trong folder nguồn "
                    'hoặc truyền "command"), hay nạp runs.json vào folder, '
                    f"hoặc dùng số đo đã lưu trong {self.base_dir}/raw_runs."
                )
            return result

        succeeded = [r for r in runs if r.get("status") == "success"]
        if not succeeded:
            result.blocked = True
            result.blocked_reasons.append(
                f"0/{len(runs)} run thành công trong {runs_source}: không có số đo để ra giải pháp. "
                "Xem 'Lỗi benchmark' ở kết quả; script đo phải in dòng 'STEP <tên> <ms>' rồi thoát "
                "(web server app.run/ hoặc script không in STEP sẽ không ra bottleneck)."
            )
            return result

        if not feature_id:
            feature_id = str(runs[0].get("feature_id") or "unknown_feature")
            result.feature_id = feature_id

        active_configs = self._active_configs(runs)
        result.fingerprint = str(runs[0].get("fingerprint") or "")
        timestamps = [str(r.get("timestamp", "")) for r in runs if r.get("timestamp")]
        window_start = min(timestamps) if timestamps else ""
        window_end = max(timestamps) if timestamps else ""

        if lane == "A":
            self._run_lane_a(
                result, runs, feature_id, active_configs, window_start, window_end, runs_source,
                brief_id=brief_id,
            )
        else:
            self._run_lane_b(result, runs, feature_id, active_configs, window_start, window_end, runs_source)
        return result

    # ---------------------------------------------------------------- lane A --
    def _run_lane_a(
        self, result, runs, feature_id, active_configs, window_start, window_end, runs_source,
        brief_id: str = "",
    ):
        snapshot_id = self.file_store.next_id("snapshots", "S-")
        baseline, gate_ok, gate_logs = self.lane_a.generate_baseline_report(
            snapshot_id=snapshot_id,
            feature_id=feature_id,
            raw_log_runs=runs,
            active_configs=active_configs,
            time_window_start=window_start,
            time_window_end=window_end,
            fingerprint=str(runs[0].get("fingerprint") or "") or None,
            created_by="optimize_api_lane_a",
            brief_id=brief_id or None,
        )
        result.baseline = baseline.model_dump()
        result.gate2_passed = gate_ok
        result.gate2_logs = gate_logs
        if not gate_ok:
            result.notes.append("Cổng 2 chưa qua: baseline chỉ dùng để xem, chưa làm căn cứ quyết định.")

        candidates = ScannerService.detect_bottlenecks(baseline)
        result.bottlenecks = [
            BottleneckInfo(
                step_name=step.step_name,
                pct_of_total_time=step.pct_of_total_time,
                p50_latency_ms=step.p50_latency_ms,
                p90_latency_ms=step.p90_latency_ms,
                p99_latency_ms=step.p99_latency_ms,
                signals=signals,
            )
            for step, signals in candidates
        ]

        source = str(runs_source or "runs")
        confirmed = self._confirmed_steps(feature_id)
        eligible = [
            (step, signals)
            for step, signals in candidates
            if step.pct_of_total_time >= MIN_PCT_FOR_HYPOTHESIS and step.step_name not in confirmed
        ]
        skipped = [step.step_name for step, _ in candidates if step.pct_of_total_time < MIN_PCT_FOR_HYPOTHESIS]
        if skipped:
            result.notes.append(
                f"Giữ nguyên số liệu nhưng không đề xuất cho bước có tác động < {MIN_PCT_FOR_HYPOTHESIS}%: "
                + ", ".join(skipped)
            )
        reconfirmed = [s for s in confirmed if any(step.step_name == s for step, _ in candidates)]
        if reconfirmed:
            result.notes.append(
                "Bước đã có solution chính thức (domain owner đã chốt biến) nên không sinh hypothesis trùng: "
                + ", ".join(sorted(reconfirmed))
                + "."
            )
        proposals = [
            self._build_hypothesis(step, signals, baseline, runs, source, lane="A")
            for step, signals in eligible[:3]
        ]
        main_solutions, hypotheses = LaneAService.order_solutions(proposals)

        for proposal in hypotheses:
            payload = proposal.model_dump()
            passed, errors = Gate3Evaluator.validate(proposal)
            payload["gate3"] = {"passed": passed, "errors": errors}
            result.hypotheses.append(payload)

        result.solutions = [p.model_dump() for p in main_solutions] + self._saved_solutions(
            baseline.feature_id
        )

        if not candidates:
            result.notes.append(
                "Không bước nào vượt tín hiệu bottleneck (share >= 25%, tail, retry) trên baseline này."
                + (" (baseline thiếu per-step timing)" if baseline.data_gaps else "")
            )
        result.notes.append(
            "Hypothesis có số đo thật nhưng chưa chốt biến cấu hình: domain owner nhập tên "
            "1 biến cấu hình (ô bên dưới mỗi thẻ, hoặc POST /api/v1/optimize/hypotheses/{id}/confirm) "
            "để chuyển thành solution chính (A3-V6) — hệ thống không tự chốt thay người."
        )

    # ---------------------------------------------------------------- lane B --
    def _run_lane_b(self, result, runs, feature_id, active_configs, window_start, window_end, runs_source):
        blocked = self.lane_b.check_preconditions(feature_id)
        if blocked:
            result.blocked = True
            result.blocked_reasons.extend(blocked)
            return

        scan_result = self.lane_b.scan(
            feature_id=feature_id,
            raw_runs=runs,
            period=result.period,
            active_configs=active_configs,
        )
        result.scan = scan_result.model_dump()
        if scan_result.blocked:
            result.blocked = True
            result.blocked_reasons.extend(scan_result.blocked_reasons)
            return

        kept = scan_result.kept
        if not kept:
            result.notes.append(
                "B1 không giữ ứng viên nào (persistence/threshold/baseline yếu) - xem observations/."
            )
            return

        snapshot_id = kept[0].snapshot_id
        snapshot = self.file_store.read_json("snapshots", f"{snapshot_id}.json")
        if not snapshot:
            result.blocked = True
            result.blocked_reasons.append(f"Snapshot {snapshot_id} của ứng viên không đọc được.")
            return
        baseline_obj = BaselineReport(**snapshot)

        candidates = ScannerService.detect_bottlenecks(baseline_obj)
        eligible = [(step, signals) for step, signals in candidates if step.pct_of_total_time >= MIN_PCT_FOR_HYPOTHESIS]
        proposals = [
            self._build_hypothesis(step, signals, baseline_obj, runs, str(runs_source or "runs"), lane="B")
            for step, signals in eligible[:3]
        ]
        if not proposals:
            result.notes.append("Ứng viên được giữ nhưng không còn tín hiệu trên snapshot - không đề xuất.")
            return

        propose_result = self.lane_b.propose(
            feature_id=feature_id,
            baseline=baseline_obj,
            proposals=proposals,
            period=result.period,
        )
        result.propose = propose_result.model_dump()
        if propose_result.blocked:
            result.blocked = True
            result.blocked_reasons.extend(propose_result.blocked_reasons)
            return
        result.solutions = [
            o.model_dump() for o in propose_result.outcomes if o.outcome == "queued"
        ]
