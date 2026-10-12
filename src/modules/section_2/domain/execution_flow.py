from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from src.core.schemas.solution import SolutionProposal
from src.core.schemas.plan import FullSolutionPlan, PhasePlanItem
from src.core.schemas.measurement import MeasurementReport, ValidityCheckResult
from src.core.schemas.lesson import LessonEntry, LessonDecision
from src.core.schemas.brief import RiskTier, RISK_TIER_ORDER
from src.core.storage.file_store import FileStore
from src.modules.section_2.domain.reranker_service import RerankerService
from src.modules.section_2.domain.verification_service import VerificationEngine, VerificationDecision, RetestResult

class Section2WorkflowOrchestrator:
    """
    End-to-End Orchestrator for Section 2 (Steps 01 to 08)
    (03_SHARED_AND_SECTION_2_DESIGN.md)
    """
    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def step_01_rerank(self, proposals: List[SolutionProposal]) -> Tuple[List[SolutionProposal], List[Dict[str, str]]]:
        """
        Step 01: Re-rank solutions and exclude invalid/over_ceiling items
        """
        return RerankerService.rerank_solutions(proposals)

    def step_02_create_plan(
        self,
        solution: SolutionProposal,
        owner: str = "AI Flow Engineer",
        thresholds: Optional[Dict[str, float]] = None
    ) -> FullSolutionPlan:
        """
        Step 02: Create phase-based plan (1 phase = 1 variable, S02-R1..R4)
        """
        thr = {"keep": 25.0, "revert": 10.0}
        if thresholds:
            thr.update(thresholds)

        phase_item = PhasePlanItem(
            phase_id=f"{solution.solution_id}-P1",
            change_variable=solution.change.variables[0] if solution.change.variables else "",
            risk_tier=solution.risk_tier,
            done_criteria=(
                f"Latency p50 improvement >= {thr['keep']}% "
                f"and no hard guardrail degraded beyond baseline"
            ),
            tests=["Unit regression tests", "Guardrail check (quality_score, error_rate)"],
            remeasure_compare_to=solution.snapshot_id,
            remeasure_window_days=solution.remeasure_plan.window_days if solution.remeasure_plan else 7,
            remeasure_min_runs=solution.remeasure_plan.min_runs if solution.remeasure_plan else 30,
            rollback_action=solution.rollback_action,
            rollback_owner=owner,
            owner=owner
        )

        plan = FullSolutionPlan(solution_id=solution.solution_id, revision=1, phases=[phase_item])
        self.file_store.save_plan(solution.solution_id, plan.model_dump())
        return plan

    def step_02_create_multi_phase_plan(
        self,
        solutions: List[SolutionProposal],
        owner: str = "AI Flow Engineer",
        thresholds: Optional[Dict[str, float]] = None
    ) -> FullSolutionPlan:
        """
        S02-R1..R4: split the selected work into phases ordered by risk tier
        (config -> prompt -> code). One phase = one variable, each phase carries
        numeric done criteria, tests incl. guardrail, remeasure and rollback, and
        depends on the previous phase passing step 06 with KEEP.
        """
        if not solutions:
            raise ValueError("S02: at least one solution is required to build a plan.")

        thr = {"keep": 25.0, "revert": 10.0}
        if thresholds:
            thr.update(thresholds)

        ordered = sorted(solutions, key=lambda s: RISK_TIER_ORDER[s.risk_tier])
        phases: List[PhasePlanItem] = []
        previous_phase_id: Optional[str] = None

        for solution in ordered:
            phase_id = f"{solution.solution_id}-P1"
            phase = PhasePlanItem(
                phase_id=phase_id,
                change_variable=solution.change.variables[0] if solution.change.variables else "",
                risk_tier=solution.risk_tier,
                done_criteria=(
                    f"Latency p50 improvement >= {thr['keep']}% vs {solution.snapshot_id} "
                    f"and no hard guardrail degraded beyond baseline"
                ),
                tests=["Unit regression tests", "Guardrail check (quality_score, error_rate)"],
                remeasure_compare_to=solution.snapshot_id,
                remeasure_window_days=solution.remeasure_plan.window_days if solution.remeasure_plan else 7,
                remeasure_min_runs=solution.remeasure_plan.min_runs if solution.remeasure_plan else 30,
                rollback_action=solution.rollback_action,
                rollback_owner=owner,
                depends_on=[previous_phase_id] if previous_phase_id else [],
                owner=owner,
            )
            phases.append(phase)
            previous_phase_id = phase_id

        solution_id = (
            ordered[0].solution_id
            if len(ordered) == 1
            else "+".join(s.solution_id for s in ordered)
        )
        plan = FullSolutionPlan(solution_id=solution_id, revision=1, phases=phases)
        self.file_store.save_plan(solution_id, plan.model_dump())
        return plan

    def step_05_and_06_measure_and_decide(
        self,
        solution_id: str,
        snapshot_before: str,
        snapshot_after: str,
        baseline_p50: float,
        retest_p50: float,
        validity: ValidityCheckResult,
        guardrail_breached: bool = False,
        partial_retry_count: int = 0,
        fingerprint: str = "",
        change_summary: str = "",
        keep_threshold_pct: float = 25.0,
        revert_threshold_pct: float = 10.0
    ) -> RetestResult:
        """
        Step 05 & Step 06: run V-1..V-6 first, then the decision engine.
        Writes measurements/M-*.json; a lesson entry is appended only when the
        comparison is valid (INVALID means "no decision yet", S06 rules).
        """
        result = VerificationEngine.evaluate_retest(
            solution_id=solution_id,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            baseline_p50=baseline_p50,
            retest_p50=retest_p50,
            validity=validity,
            guardrail_breached=guardrail_breached,
            partial_retry_count=partial_retry_count,
            keep_threshold_pct=keep_threshold_pct,
            revert_threshold_pct=revert_threshold_pct
        )

        measurement = MeasurementReport(
            phase_id=f"{solution_id}-P1",
            compare_snapshot_before=snapshot_before,
            compare_snapshot_after=snapshot_after,
            validity_checks=validity,
            latency_p50_change_pct=result.improvement_pct,
            latency_p90_change_pct=result.improvement_pct,
            latency_p99_change_pct=result.improvement_pct,
            guardrail_breached=guardrail_breached,
            is_valid_comparison=validity.all_passed()
        )
        measurement_id = self.file_store.next_id("measurements", "M-")
        self.file_store.save_measurement(measurement_id, measurement.model_dump())

        if result.decision != VerificationDecision.INVALID:
            lesson = LessonEntry(
                lesson_id=self._next_lesson_id(),
                date=self._now(),
                solution_id=solution_id,
                fingerprint=fingerprint or "unknown",
                change=change_summary or f"Phase P1 of {solution_id}",
                measured={
                    "snapshot_before": snapshot_before,
                    "snapshot_after": snapshot_after,
                    "result": f"{result.improvement_pct}%"
                },
                decision=LessonDecision(result.decision.value),
                reason=result.reasoning,
                revisit_if=(
                    "Rule-set updated, model changed or subflow structure changed"
                    if result.decision == VerificationDecision.REVERT else None
                )
            )
            self.file_store.append_lesson(lesson.model_dump())
        return result

    def _next_lesson_id(self) -> str:
        existing = self.file_store.read_lessons()
        return f"L-{len(existing) + 1:04d}"

    def step_07_generate_report(self, solution_id: str, retest_result: RetestResult) -> str:
        """
        Step 07: 3-part Markdown report (Xong thật / Đơn giản hóa có lý do / Còn thiếu),
        written to reports/R-*.md (S07-R1..R3).
        """
        valid = retest_result.validity_checks.all_passed()
        content = f"""## Report: {solution_id}

### Xong thật
- Cặp so sánh: {retest_result.snapshot_id_before} -> {retest_result.snapshot_id_after}
- p50 trước: {retest_result.baseline_p50_ms:.1f} ms, p50 sau: {retest_result.retest_p50_ms:.1f} ms
- Mức cải thiện thực đo: {retest_result.improvement_pct}%
- Kiểm tra hợp lệ V-1..V-6: {"đủ" if valid else "một hoặc nhiều kiểm tra thất bại"}
- Quyết định: {retest_result.decision.value} ({retest_result.reasoning})

### Đơn giản hóa có lý do
- Chỉ thay đổi một biến trong một phase; không gộp thay đổi code/prompt vào phase config.
- Chưa rollout ngoài phạm vi đã chọn trong plan.

### Còn thiếu
- {"" if valid else "Phép so sánh chưa hợp lệ (V-n thất bại): cần tìm đúng cặp fingerprint rồi đo lại. "}
- Chưa có số đo guardrail chất lượng nếu không có log chất lượng tương ứng.
- Giả thuyết chưa xác minh và khoảng trống dữ liệu cần ghi tiếp ở vòng sau.
"""
        report_id = self.file_store.next_id("reports", "R-", ext=".md")
        self.file_store.save_report(report_id, content)
        return content

    def step_08_rollout_plan(self, solution: SolutionProposal) -> List[Dict[str, Any]]:
        """
        Step 08: staged rollout, each stage has observation window and rollback (S08-R1..R3)
        """
        return [
            {
                "stage": 1,
                "scope": f"{solution.change.variables[0]} on a small slice / one group",
                "observe_days": 7,
                "min_runs": 30,
                "auto_rollback_if": "hard guardrail breached, or error/retry rate over threshold",
                "owner": "rollout-owner",
                "rollback": solution.rollback_action
            },
            {
                "stage": 2,
                "scope": "full traffic for this change",
                "observe_days": 7,
                "min_runs": 30,
                "auto_rollback_if": "same as stage 1",
                "owner": "rollout-owner",
                "rollback": solution.rollback_action
            },
            {
                "stage": 3,
                "scope": f"wider behaviour change if risk_tier > config ({solution.risk_tier.value})",
                "observe_days": 14,
                "min_runs": 30,
                "auto_rollback_if": "guardrail breach or KEEP thresholds no longer met",
                "owner": "program-owner",
                "rollback": solution.rollback_action
            }
        ]
