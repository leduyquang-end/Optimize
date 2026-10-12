import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from src.core.schemas.baseline import BaselineReport
from src.core.schemas.policy import FeatureRegistryEntry, FeatureMode, SystemPolicy
from src.core.schemas.solution import SolutionProposal
from src.core.storage.file_store import FileStore
from src.modules.lane_a.domain.lane_a_service import LaneAService
from src.modules.lane_b.domain.scanner_service import (
    CandidateBottleneck,
    ScannerService,
)
from src.modules.lane_b.domain.proposer_service import SelfCriticismEngine
from src.modules.lane_b.gates.gate_b1 import GateB1Evaluator
from src.modules.lane_b.gates.gate_b2 import GateB2Evaluator
from src.modules.policy_registry.domain.policy_service import PolicyService, RegistryService


class ScanRejection(BaseModel):
    stage: str
    item: str
    reason: str


class CandidateOutcome(BaseModel):
    step_name: str
    fingerprint: str = ""
    signals: str = ""
    score: float = 0.0
    periods_seen: int = 0
    snapshot_id: Optional[str] = None
    baseline_weak: bool = False


class ScanResult(BaseModel):
    feature: str
    period: str
    blocked: bool = False
    blocked_reasons: List[str] = Field(default_factory=list)
    fingerprints: List[str] = Field(default_factory=list)
    not_comparable_runs: int = 0
    kept: List[CandidateOutcome] = Field(default_factory=list)
    rejected: List[ScanRejection] = Field(default_factory=list)
    observation_file: Optional[str] = None


class ProposalOutcome(BaseModel):
    solution_id: str
    outcome: str  # queued | deferred | rejected | hypothesis | blocked
    reasons: List[str] = Field(default_factory=list)
    confidence: Optional[str] = None
    queue_file: Optional[str] = None


class ProposeResult(BaseModel):
    feature: str
    blocked: bool = False
    blocked_reasons: List[str] = Field(default_factory=list)
    outcomes: List[ProposalOutcome] = Field(default_factory=list)
    queued_count: int = 0


class LaneBService:
    """
    Lane B end-to-end (02_LANE_B_DESIGN.md):
    - B0: preconditions (valid policy, registry entry, Business Rule Card, budget)
    - B1: scan, group by fingerprint, detect, persistence, lesson dedup, rank, baseline+snapshot, observation
    - B2: hypothesis/verified split, ceiling + self-criticism, confidence, top_k, review package
    Lane B only proposes; it never applies a change.
    """

    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()
        self.base_dir = self.file_store.base_dir
        self.policy_service = PolicyService(self.base_dir)
        self.registry_service = RegistryService(self.base_dir)
        self.lane_a = LaneAService(self.file_store)

    # ------------------------------------------------------------------ B0 ---
    def check_preconditions(self, feature_id: str) -> List[str]:
        reasons: List[str] = []
        policy: Optional[SystemPolicy] = None

        try:
            policy = self.policy_service.get_policy()
        except FileNotFoundError as exc:
            reasons.append(str(exc))

        if policy is not None:
            now = datetime.now(timezone.utc)

            def parse(value: str) -> Optional[datetime]:
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
                except ValueError:
                    return None

            effective = parse(policy.effective_from)
            if effective is None:
                reasons.append(f"B0-R1: policy.effective_from '{policy.effective_from}' is not ISO 8601.")
            elif now < effective:
                reasons.append("B0-R1: policy is not effective yet; Lane B must not run.")
            if policy.expires_at:
                expires = parse(policy.expires_at)
                if expires is None:
                    reasons.append(f"B0-R1: policy.expires_at '{policy.expires_at}' is not ISO 8601.")
                elif now > expires:
                    reasons.append("B0-R1: policy expired; Lane B must stop and report to the program owner.")
            if policy.scan.budget_queries_per_run <= 0:
                reasons.append("B0-R1: scan budget exhausted (budget_queries_per_run <= 0).")

        try:
            registry = self.registry_service.load()
        except FileNotFoundError as exc:
            reasons.append(str(exc))
            registry = []

        entry = RegistryService.entry_for(registry, feature_id) if registry else None
        if registry and entry is None:
            reasons.append(f"B0-R1: feature '{feature_id}' is not in the feature registry.")

        if entry is not None:
            if not entry.domain_owner or entry.domain_owner.upper().startswith("PENDING"):
                reasons.append(
                    f"B0-R1: feature '{feature_id}' has no confirmed domain owner "
                    "(Business Rule Card cannot be validated)."
                )
            if not entry.business_rule_card:
                reasons.append(f"B0-R1: feature '{feature_id}' has no Business Rule Card.")
            else:
                card_path = os.path.join(self.base_dir, entry.business_rule_card)
                if not os.path.exists(card_path):
                    reasons.append(
                        f"B0-R1: Business Rule Card '{entry.business_rule_card}' not found for '{feature_id}'."
                    )

        return reasons

    # ------------------------------------------------------------------ B1 ---
    @staticmethod
    def group_runs_by_fingerprint(
        runs: List[Dict[str, object]]
    ) -> Tuple[Dict[str, List[Dict[str, object]]], int]:
        """B1-R2: runs whose fingerprint cannot be derived are marked not_comparable."""
        grouped: Dict[str, List[Dict[str, object]]] = {}
        not_comparable = 0
        for run in runs:
            fingerprint = run.get("fingerprint")
            if not fingerprint:
                not_comparable += 1
                continue
            grouped.setdefault(str(fingerprint), []).append(run)
        return grouped, not_comparable

    @staticmethod
    def _reverted_changes(lessons: List[Dict[str, object]]) -> List[str]:
        return [
            str(lesson.get("change", ""))
            for lesson in lessons
            if str(lesson.get("decision", "")).upper() == "REVERT" and lesson.get("change")
        ]

    @staticmethod
    def _matches_reverted(step_name: str, reverted_changes: List[str]) -> Optional[str]:
        for change in reverted_changes:
            if step_name.lower() in change.lower() or change.lower() in step_name.lower():
                return change
        return None

    @staticmethod
    def _unique_name(folder: str, stem: str, ext: str) -> str:
        candidate = f"{stem}{ext}"
        counter = 2
        while os.path.exists(os.path.join(folder, candidate)):
            candidate = f"{stem}-{counter}{ext}"
            counter += 1
        return candidate

    def scan(
        self,
        feature_id: str,
        raw_runs: List[Dict[str, object]],
        period: str,
        runs_per_week: int = 0,
        candidate_periods: Optional[Dict[str, int]] = None,
        active_configs: Optional[Dict[str, str]] = None,
    ) -> ScanResult:
        result = ScanResult(feature=feature_id, period=period)

        blocked = self.check_preconditions(feature_id)
        if blocked:
            result.blocked = True
            result.blocked_reasons = blocked
            return result

        policy = self.policy_service.get_policy()
        lessons = self.file_store.read_lessons()
        reverted_changes = self._reverted_changes(lessons)

        if active_configs is None:
            active_configs = {}
            for run in raw_runs:
                config = run.get("config")
                if isinstance(config, dict):
                    active_configs.update({str(k): str(v) for k, v in config.items()})

        grouped, not_comparable = self.group_runs_by_fingerprint(raw_runs)
        result.not_comparable_runs = not_comparable
        result.fingerprints = sorted(grouped)

        reservoir: List[Tuple[CandidateBottleneck, str, str, int, BaselineReport]] = []

        for fingerprint, fingerprint_runs in sorted(grouped.items()):
            usable_runs = [r for r in fingerprint_runs if r.get("latency_ms") is not None]
            for run in fingerprint_runs:
                if run.get("latency_ms") is None:
                    result.rejected.append(
                        ScanRejection(
                            stage="clean",
                            item=f"{fingerprint}:{run.get('run_id', '?')}",
                            reason="Missing field latency_ms - data gap, value not estimated (A2-R7).",
                        )
                    )

            snapshot_id = self.file_store.next_id("snapshots", "S-")
            baseline, gate_ok, gate_logs = self.lane_a.generate_baseline_report(
                snapshot_id=snapshot_id,
                feature_id=feature_id,
                raw_log_runs=usable_runs,
                active_configs=active_configs or {},
                time_window_start=str(fingerprint_runs[0].get("timestamp", "")),
                time_window_end=str(fingerprint_runs[-1].get("timestamp", "")),
                fingerprint=fingerprint,
                created_by="lane_b",
            )

            if not gate_ok:
                result.rejected.append(
                    ScanRejection(
                        stage="gate_b1",
                        item=fingerprint,
                        reason="; ".join(gate_logs),
                    )
                )
                continue

            candidates = ScannerService.detect_bottlenecks(
                baseline, share_threshold=policy.persistence.share_threshold
            )
            if not candidates:
                result.rejected.append(
                    ScanRejection(
                        stage="detect",
                        item=fingerprint,
                        reason="No step crossed any bottleneck signal on this period.",
                    )
                )
                continue

            for step, signals in candidates:
                periods_seen = (candidate_periods or {}).get(step.step_name, 1)

                # persistence filter (B1-R3 / B1-V4)
                if periods_seen < policy.persistence.min_periods:
                    result.rejected.append(
                        ScanRejection(
                            stage="persistence",
                            item=step.step_name,
                            reason=(
                                f"Seen in {periods_seen} period(s) < min_periods "
                                f"{policy.persistence.min_periods}: transient, not structural."
                            ),
                        )
                    )
                    continue

                # lesson dedup (B1-R6)
                reverted_hit = self._matches_reverted(step.step_name, reverted_changes)
                if reverted_hit:
                    result.rejected.append(
                        ScanRejection(
                            stage="lessons",
                            item=step.step_name,
                            reason=f"Already reverted in lessons store: '{reverted_hit}' (no new condition).",
                        )
                    )
                    continue

                share = step.pct_of_total_time / 100.0
                bottleneck = CandidateBottleneck(
                    step_name=step.step_name,
                    share_time=share,
                    runs_per_week=runs_per_week,
                    stability=min(periods_seen / max(policy.persistence.min_periods, 1), 1.0),
                    headroom=0.5,  # not estimable yet - default 0.5 and record it (02 5.4)
                )
                reservoir.append((bottleneck, signals, fingerprint, periods_seen, baseline))

        # rank (B1-R4) and cut to top_k
        ranked = sorted(reservoir, key=lambda item: item[0].compute_score(), reverse=True)
        top_k = policy.scan.top_k

        for bottleneck, signals, fingerprint, periods_seen, baseline in ranked[:top_k]:
            weak = ScannerService.build_baseline_weak(baseline, policy.min_runs)
            gate_passed, gate_errors = GateB1Evaluator.validate(baseline, self._reverted_snapshots(lessons))
            if not gate_passed or weak:
                result.rejected.append(
                    ScanRejection(
                        stage="gate_b1",
                        item=bottleneck.step_name,
                        reason="; ".join(gate_errors) or "Baseline weaker than min_runs - not pushed to B2.",
                    )
                )
                continue
            result.kept.append(
                CandidateOutcome(
                    step_name=bottleneck.step_name,
                    fingerprint=fingerprint,
                    signals=signals,
                    score=bottleneck.compute_score(),
                    periods_seen=periods_seen,
                    snapshot_id=baseline.snapshot_id,
                    baseline_weak=weak,
                )
            )

        for bottleneck, _, fingerprint, _, _ in ranked[top_k:]:
            result.rejected.append(
                ScanRejection(
                    stage="top_k",
                    item=bottleneck.step_name,
                    reason=f"Ranked below top_k={top_k} this period; deferred to the next scan.",
                )
            )

        # observation log (kept AND rejected with reasons)
        obs_folder = os.path.join(self.base_dir, "observations")
        obs_name = self._unique_name(obs_folder, f"scan-{feature_id}-{period}", ".json")
        payload = {
            "feature": feature_id,
            "period": period,
            "fingerprints": result.fingerprints,
            "not_comparable_runs": result.not_comparable_runs,
            "kept": [c.model_dump() for c in result.kept],
            "rejected": [r.model_dump() for r in result.rejected],
        }
        result.observation_file = self.file_store.save_observation(obs_name[:-5], payload)
        return result

    def _reverted_snapshots(self, lessons: List[Dict[str, object]]) -> List[str]:
        snapshots: List[str] = []
        for lesson in lessons:
            if str(lesson.get("decision", "")).upper() == "REVERT":
                measured = lesson.get("measured") or {}
                for key in ("snapshot_before", "snapshot_after"):
                    value = measured.get(key)
                    if value:
                        snapshots.append(str(value))
        return snapshots

    # ------------------------------------------------------------------ B2 ---
    @staticmethod
    def _has_direct_evidence(proposal: SolutionProposal) -> bool:
        cause = proposal.verified_root_cause
        return bool(cause.evidence_log_lines or cause.kg_nodes or cause.code_references)

    @staticmethod
    def _conservative_impact(proposal: SolutionProposal) -> float:
        import re

        numbers = re.findall(r"-?\d+(?:\.\d+)?", proposal.expected_impact_range)
        return abs(float(numbers[0])) if numbers else 0.0

    def _confidence(
        self,
        proposal: SolutionProposal,
        baseline: BaselineReport,
        lessons: List[Dict[str, object]],
    ) -> str:
        if baseline.is_weak_baseline or not self._has_direct_evidence(proposal):
            return "low"
        prior_keep = any(
            str(lesson.get("decision", "")).upper() == "KEEP"
            and lesson.get("fingerprint") == baseline.fingerprint
            for lesson in lessons
        )
        return "high" if prior_keep else "medium"

    def propose(
        self,
        feature_id: str,
        baseline: BaselineReport,
        proposals: List[SolutionProposal],
        period: str,
    ) -> ProposeResult:
        result = ProposeResult(feature=feature_id)

        blocked = self.check_preconditions(feature_id)
        if blocked:
            result.blocked = True
            result.blocked_reasons = blocked
            return result

        registry = self.registry_service.load()
        entry = RegistryService.entry_for(registry, feature_id)
        if entry is None or entry.mode != FeatureMode.PROPOSE:
            result.blocked = True
            result.blocked_reasons = [
                f"Feature '{feature_id}' is in observe mode: scan only, proposals are not allowed (B2-R1)."
            ]
            return result

        policy = self.policy_service.get_policy()
        lessons = self.file_store.read_lessons()
        reverted_changes = self._reverted_changes(lessons)

        accepted: List[Tuple[SolutionProposal, str]] = []
        for proposal in proposals:
            proposal.source_lane = "B"

            if proposal.is_unverified_hypothesis or not self._has_direct_evidence(proposal):
                result.outcomes.append(
                    ProposalOutcome(
                        solution_id=proposal.solution_id,
                        outcome="hypothesis",
                        reasons=[
                            "B2-R2: no direct evidence (log/KG/code) - kept out of the review package (A3-V6)."
                        ],
                    )
                )
                continue

            gate_errors = GateB2Evaluator.validate(proposal, policy)[1]
            if gate_errors:
                result.outcomes.append(
                    ProposalOutcome(
                        solution_id=proposal.solution_id,
                        outcome="rejected",
                        reasons=gate_errors,
                    )
                )
                continue

            passed, rejections = SelfCriticismEngine.audit_proposal(
                proposal, policy, past_reverted_changes=reverted_changes
            )
            if not passed:
                result.outcomes.append(
                    ProposalOutcome(
                        solution_id=proposal.solution_id,
                        outcome="rejected",
                        reasons=rejections,
                    )
                )
                continue

            confidence = self._confidence(proposal, baseline, lessons)
            proposal.confidence_level = confidence
            accepted.append((proposal, confidence))

        # top_k by conservative impact (avoid review-by-inertia, B2-R6)
        accepted.sort(key=lambda item: self._conservative_impact(item[0]), reverse=True)
        top_k = policy.scan.top_k
        for proposal, confidence in accepted[:top_k]:
            queue_file = self._queue_package(proposal, baseline, confidence, period)
            result.outcomes.append(
                ProposalOutcome(
                    solution_id=proposal.solution_id,
                    outcome="queued",
                    reasons=[
                        f"Passed B2 gate and self-criticism; confidence={confidence}"
                        + (" - domain owner must review (low confidence)." if confidence == "low" else ".")
                    ],
                    confidence=confidence,
                    queue_file=queue_file,
                )
            )
        for proposal, confidence in accepted[top_k:]:
            result.outcomes.append(
                ProposalOutcome(
                    solution_id=proposal.solution_id,
                    outcome="deferred",
                    reasons=[f"Over top_k={top_k} for this period; queued next cycle (B2-R6)."],
                    confidence=confidence,
                )
            )

        result.queued_count = len([o for o in result.outcomes if o.outcome == "queued"])
        return result

    @staticmethod
    def _plus_business_days(start: datetime, days: int) -> datetime:
        current = start
        added = 0
        while added < days:
            current += timedelta(days=1)
            if current.weekday() < 5:
                added += 1
        return current

    def _queue_package(
        self,
        proposal: SolutionProposal,
        baseline: BaselineReport,
        confidence: str,
        period: str,
    ) -> str:
        """Executive review package (02_LANE_B_DESIGN.md section 6.5 + section 7)."""
        folder = os.path.join(self.base_dir, "queue", "review")
        name = self._unique_name(folder, f"REV-{proposal.solution_id}", ".json")
        now = datetime.now(timezone.utc)
        due = self._plus_business_days(now, 2)
        package = {
            "solution_id": proposal.solution_id,
            "status": "pending",
            "problem": (
                f"Step share/tail on {proposal.feature_id} (snapshot {baseline.snapshot_id}) "
                f"is the dominant cost driver."
            ),
            "proposal": proposal.proposed_change,
            "tradeoff": {"pros": proposal.pros, "cons": proposal.cons},
            "evidence": {
                "root_cause": proposal.verified_root_cause.statement,
                "log_lines": proposal.verified_root_cause.evidence_log_lines,
                "kg_nodes": proposal.verified_root_cause.kg_nodes,
                "code_references": proposal.verified_root_cause.code_references,
                "snapshot_id": baseline.snapshot_id,
                "fingerprint": baseline.fingerprint,
                "queries": baseline.queries,
            },
            "confidence": confidence,
            "risk_tier": proposal.risk_tier.value,
            "rollback": proposal.rollback_action,
            "remeasure": proposal.retest_plan,
            "decision_needed": "Approve / approve with changes / reject (with reason, reason goes to lessons).",
            "period": period,
            "created_at": now.isoformat(),
            "due_at": due.isoformat(),
            "decision": None,
            "reviewer": None,
            "decided_at": None,
            "reason": None,
            "required_changes": [],
            "due": "2 business days - escalate to program owner, never self-approve (B2-R1).",
        }
        self.file_store.save_review_package(name[:-5], package)
        return os.path.join("queue", "review", name)
