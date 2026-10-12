import json
import os
from typing import Any, Dict, List, Optional

from src.core.storage.file_store import FileStore
from src.modules.lane_b.domain.review_service import ReviewService


class LaneBMetricsService:
    """
    Quality metrics of Lane B itself (02_LANE_B_DESIGN.md section 9):
    approval rate, keep rate, revert rate, false-alarm rate, recall vs Lane A,
    guardrail violations (target: 0).
    Every rate carries its denominator so a number can be traced back to data.
    """

    def __init__(self, file_store: Optional[FileStore] = None):
        self.file_store = file_store or FileStore()
        self.reviews = ReviewService(self.file_store)

    @staticmethod
    def _rate(numerator: int, denominator: int) -> Optional[float]:
        if denominator <= 0:
            return None
        return round(numerator / denominator, 4)

    def _observations(self) -> List[Dict[str, Any]]:
        folder = os.path.join(self.file_store.base_dir, "observations")
        if not os.path.isdir(folder):
            return []
        payloads = []
        for name in sorted(os.listdir(folder)):
            if not name.endswith(".json") or name == "scan_history.json":
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                payloads.append(json.load(f))
        return payloads

    def _lane_a_fingerprints(self) -> set:
        fingerprints = set()
        for solution_name in self.file_store.list_json("solutions"):
            solution = self.file_store.read_json("solutions", solution_name)
            if not solution:
                continue
            snapshot = self.file_store.read_json("snapshots", f"{solution.get('snapshot_id')}.json")
            if snapshot and snapshot.get("fingerprint"):
                fingerprints.add(snapshot["fingerprint"])
        return fingerprints

    def compute(self) -> Dict[str, Any]:
        lessons = self.file_store.read_lessons()
        packages = self.reviews.list_packages()
        observations = self._observations()

        # review outcomes (packages are the Lane B proposals sent to a human)
        decided = [p for p in packages if p.get("decision")]
        approved = [p for p in decided if p["decision"] in ("approved", "approved_with_changes")]
        rejected = [p for p in decided if p["decision"] == "rejected"]

        # measured outcomes (lessons where a re-measurement actually happened)
        measured = [
            lesson for lesson in lessons
            if (lesson.get("measured") or {}).get("snapshot_after")
        ]
        keeps = [l for l in measured if str(l.get("decision", "")).upper() == "KEEP"]
        reverts = [l for l in measured if str(l.get("decision", "")).upper() == "REVERT"]
        partials = [l for l in measured if str(l.get("decision", "")).upper() == "PARTIAL"]

        # B1 candidates and false alarms
        kept_candidates = sum(len(obs.get("kept", [])) for obs in observations)
        rejections = [r for obs in observations for r in obs.get("rejected", [])]
        candidate_stages = {"persistence", "lessons", "top_k", "gate_b1"}
        candidate_rejections = [r for r in rejections if r.get("stage") in candidate_stages]
        false_alarms = [r for r in candidate_rejections if r.get("stage") == "persistence"]
        candidates_total = kept_candidates + len(candidate_rejections)

        # guardrail violations in decisions or lessons (target 0)
        def mentions_guardrail(text: Any) -> bool:
            lowered = str(text or "").lower()
            return "b2-c1" in lowered or "guardrail" in lowered

        violations = sum(
            1 for p in decided if mentions_guardrail(p.get("reason"))
        ) + sum(1 for l in lessons if mentions_guardrail(l.get("reason")))

        # recall vs Lane A (fingerprints Lane A baselined that Lane B also found)
        lane_a_fps = self._lane_a_fingerprints()
        lane_b_fps = {
            candidate.get("fingerprint")
            for obs in observations
            for candidate in obs.get("kept", [])
            if candidate.get("fingerprint")
        }
        recall = self._rate(len(lane_a_fps & lane_b_fps), len(lane_a_fps))

        return {
            "approval_rate": self._rate(len(approved), len(decided)),
            "approval": {"approved": len(approved), "rejected": len(rejected), "decided": len(decided),
                         "pending": len([p for p in packages if p.get("status") == "pending"])},
            "keep_rate": self._rate(len(keeps), len(measured)),
            "revert_rate": self._rate(len(reverts), len(measured)),
            "measured": {"keep": len(keeps), "partial": len(partials), "revert": len(reverts),
                         "total": len(measured)},
            "false_alarm_rate": self._rate(len(false_alarms), candidates_total),
            "candidates": {"kept": kept_candidates, "rejected": len(candidate_rejections),
                           "false_alarms": len(false_alarms), "total": candidates_total},
            "recall_vs_lane_a": recall,
            "guardrail_violations": violations,
        }
