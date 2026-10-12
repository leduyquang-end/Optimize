"""Section 2 service — nối solutions (Lane A/B) vào vòng lặp §2.

Trách nhiệm:
- list_solutions: đọc solutions/ + hypotheses/, gắn status (mặc định proposed)
- rerank (step 01): chạy RerankerService, persist status ranked + excluded
- create_plan (step 02): 1 phase / multi-phase, persist plan, status planned
- transition: validate theo state machine §7, persist status + history
- generate_report (step 07): gọi orchestrator, persist
- list_plans / get_plan: đọc plans/
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from src.core.schemas.solution import (
    SolutionProposal,
    SolutionStatus,
    SOLUTION_TRANSITIONS,
    can_transition,
)
from src.core.schemas.plan import FullSolutionPlan
from src.core.storage.file_store import FileStore
from src.modules.section_2.domain.execution_flow import Section2WorkflowOrchestrator
from src.modules.section_2.domain.reranker_service import RerankerService


class TransitionError(ValueError):
    pass


class Section2Service:
    def __init__(self, base_dir: str = "optimization_data"):
        self.store = FileStore(base_dir)
        self.orchestrator = Section2WorkflowOrchestrator(self.store)

    # ------------------------------------------------------------------ load
    def _load_solution_file(self, path: str) -> Optional[SolutionProposal]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return SolutionProposal(**data)
        except Exception:
            return None

    def list_solutions(self) -> List[SolutionProposal]:
        out: List[SolutionProposal] = []
        sol_dir = os.path.join(self.store.base_dir, "solutions")
        if os.path.isdir(sol_dir):
            for name in sorted(os.listdir(sol_dir)):
                if name.endswith(".json"):
                    p = self._load_solution_file(os.path.join(sol_dir, name))
                    if p:
                        out.append(p)
        hyp_dir = os.path.join(self.store.base_dir, "hypotheses")
        if os.path.isdir(hyp_dir):
            for name in sorted(os.listdir(hyp_dir)):
                if name.endswith(".json"):
                    p = self._load_solution_file(os.path.join(hyp_dir, name))
                    if p and p.solution_id not in {s.solution_id for s in out}:
                        out.append(p)
        return out

    def get_solution(self, solution_id: str) -> Optional[SolutionProposal]:
        for s in self.list_solutions():
            if s.solution_id == solution_id:
                return s
        return None

    def _persist_status(self, sol: SolutionProposal) -> None:
        # Determine where the file lives: solutions/ preferred, fallback hypotheses/
        sol_path = os.path.join(self.store.base_dir, "solutions", f"{sol.solution_id}.json")
        hyp_path = os.path.join(self.store.base_dir, "hypotheses", f"{sol.solution_id}.json")
        path = sol_path if os.path.exists(sol_path) else (hyp_path if os.path.exists(hyp_path) else sol_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sol.model_dump(mode="json"), f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------ transitions
    def transition(self, solution_id: str, target: str, actor: str = "system") -> SolutionProposal:
        sol = self.get_solution(solution_id)
        if not sol:
            raise FileNotFoundError(f"Không thấy solution {solution_id}")
        current = sol.status.value if isinstance(sol.status, SolutionStatus) else str(sol.status)
        if not can_transition(current, target):
            allowed = SOLUTION_TRANSITIONS.get(current, [])
            raise TransitionError(
                f"{solution_id}: không được chuyển {current} → {target}. "
                f"Trạng thái được phép: {allowed or 'không có (terminal)'}"
            )
        sol.status_history.append(f"{current}->{target} by {actor}")
        sol.status = SolutionStatus(target)
        self._persist_status(sol)
        return sol

    # -------------------------------------------------------------- step 01
    def rerank(self, base_dir: str = "optimization_data") -> Dict[str, Any]:
        sols = self.list_solutions()
        ranked, excluded = RerankerService.rerank_solutions(sols)
        for s in ranked:
            if s.status == SolutionStatus.PROPOSED:
                self.transition(s.solution_id, "ranked", actor="rerank")
        for s in sols:
            if s.solution_id in {r.solution_id for r in ranked}:
                continue
            # mark excluded in history without changing status machine
            s.status_history.append(f"excluded by rerank")
            self._persist_status(s)
        return {
            "ranked": [s.model_dump(mode="json") for s in ranked],
            "excluded": excluded,
        }

    # -------------------------------------------------------------- step 02
    def create_plan(
        self,
        solution_ids: List[str],
        owner: str = "AI Flow Engineer",
        thresholds: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        sols = []
        for sid in solution_ids:
            s = self.get_solution(sid)
            if not s:
                raise FileNotFoundError(f"Không thấy solution {sid}")
            sols.append(s)
        if len(sols) == 1:
            plan = self.orchestrator.step_02_create_plan(sols[0], owner=owner, thresholds=thresholds)
        else:
            plan = self.orchestrator.step_02_create_multi_phase_plan(sols, owner=owner, thresholds=thresholds)
        for s in sols:
            if s.status == SolutionStatus.RANKED:
                self.transition(s.solution_id, "planned", actor="plan")
        return plan.model_dump(mode="json")

    # -------------------------------------------------------------- step 07
    def generate_report(
        self,
        solution_id: str,
        snapshot_before: str,
        snapshot_after: str,
        baseline_p50: float,
        retest_p50: float,
        validity: Any,
        guardrail_breached: bool = False,
        keep_threshold_pct: float = 25.0,
        revert_threshold_pct: float = 10.0,
    ) -> Dict[str, Any]:
        result = self.orchestrator.step_05_and_06_measure_and_decide(
            solution_id=solution_id,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            baseline_p50=baseline_p50,
            retest_p50=retest_p50,
            validity=validity,
            guardrail_breached=guardrail_breached,
            keep_threshold_pct=keep_threshold_pct,
            revert_threshold_pct=revert_threshold_pct,
        )
        report = self.orchestrator.step_07_generate_report(solution_id, result)
        # advance status if possible
        sol = self.get_solution(solution_id)
        if sol:
            cur = sol.status.value
            if cur == "measuring":
                self.transition(solution_id, "decided", actor="verify")
            cur2 = self.get_solution(solution_id).status.value
            target = "kept" if result.decision.value == "KEEP" else "reverted" if result.decision.value == "REVERT" else None
            if target and cur2 == "decided":
                self.transition(solution_id, target, actor="verify")
        return {
            "retest_result": result.model_dump(mode="json"),
            "report_markdown": report,
        }

    # -------------------------------------------------------------- list plans
    def list_plans(self) -> List[Dict[str, Any]]:
        plans_dir = os.path.join(self.store.base_dir, "plans")
        out = []
        if os.path.isdir(plans_dir):
            for name in sorted(os.listdir(plans_dir)):
                if name.endswith(".json"):
                    with open(os.path.join(plans_dir, name), "r", encoding="utf-8") as f:
                        out.append(json.load(f))
        return out

    def get_plan(self, solution_id: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(self.store.base_dir, "plans", f"{solution_id}-plan.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
