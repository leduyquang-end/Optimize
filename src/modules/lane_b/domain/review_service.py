import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.schemas.lesson import LessonDecision, LessonEntry
from src.core.storage.file_store import FileStore

VALID_DECISIONS = ("approved", "approved_with_changes", "rejected")


class ReviewService:
    """
    Review queue for Lane B proposals (02_LANE_B_DESIGN.md section 7):
    - decision: approved | approved_with_changes | rejected
    - rejection always carries a reason and the reason goes into the lessons store
    - due in 2 business days: overdue packages are escalated, never self-approved
    """

    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()

    # ------------------------------------------------------------- reading ---
    def queue_dir(self) -> str:
        return os.path.join(self.file_store.base_dir, "queue", "review")

    def list_packages(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        folder = self.queue_dir()
        if not os.path.isdir(folder):
            return []
        packages = []
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                package = json.load(f)
            package["_file"] = name
            if status is None or package.get("status") == status:
                packages.append(package)
        return packages

    def get(self, solution_id: str) -> Optional[Dict[str, Any]]:
        for package in self.list_packages():
            if package.get("solution_id") == solution_id:
                return package
        return None

    def overdue(self, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Pending packages past due_at: remind the reviewer, then the program owner."""
        moment = now or datetime.now(timezone.utc)
        overdue = []
        for package in self.list_packages(status="pending"):
            due_at = package.get("due_at")
            if not due_at:
                continue
            try:
                due = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
            except ValueError:
                continue
            if due < moment:
                overdue.append(package)
        return overdue

    # ------------------------------------------------------------ deciding ---
    def decide(
        self,
        solution_id: str,
        decision: str,
        reviewer: str,
        reason: Optional[str] = None,
        required_changes: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}, got '{decision}'.")
        if not reviewer or not reviewer.strip():
            raise ValueError("reviewer is required - proposals are never self-approved (B2-R1).")

        package = self.get(solution_id)
        if package is None:
            raise ValueError(f"No review package found for '{solution_id}'.")

        current_status = package.get("status", "pending")
        if current_status != "pending":
            raise ValueError(
                f"Package '{solution_id}' was already decided as '{current_status}' "
                f"by {package.get('reviewer')} at {package.get('decided_at')}."
            )

        if decision == "rejected" and not (reason and reason.strip()):
            raise ValueError("Rejection always requires a written reason (section 7).")
        if decision == "approved_with_changes" and not required_changes:
            raise ValueError("approved_with_changes requires the list of required changes.")

        now = datetime.now(timezone.utc).isoformat()
        package["status"] = decision
        package["decision"] = decision
        package["reviewer"] = reviewer.strip()
        package["decided_at"] = now
        package["reason"] = reason
        package["required_changes"] = required_changes or []

        filepath = os.path.join(self.queue_dir(), package["_file"])
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(
                {k: v for k, v in package.items() if k != "_file"},
                f,
                indent=2,
                ensure_ascii=False,
            )

        if decision == "rejected":
            self._append_rejection_lesson(package, reviewer, reason, now)

        return package

    def _append_rejection_lesson(
        self,
        package: Dict[str, Any],
        reviewer: str,
        reason: str,
        decided_at: str,
    ) -> str:
        evidence = package.get("evidence") or {}
        measured = evidence.get("measured") or {}
        lesson = LessonEntry(
            lesson_id=self._next_lesson_id(),
            date=decided_at,
            solution_id=str(package.get("solution_id", "")),
            fingerprint=str(evidence.get("fingerprint") or ""),
            change=str(package.get("proposal", "")),
            measured={
                "snapshot_before": evidence.get("snapshot_id"),
                "snapshot_after": measured.get("snapshot_after"),
                "result": f"not measured - rejected at review by {reviewer}",
            },
            decision=LessonDecision.REVERT,
            reason=f"Rejected at review by {reviewer}: {reason} (no change was applied).",
            revisit_if="New evidence, new business condition, or policy/registry change",
        )
        self.file_store.append_lesson(lesson.model_dump())
        return lesson.lesson_id

    def _next_lesson_id(self) -> str:
        return f"L-{len(self.file_store.read_lessons()) + 1:04d}"
