import json
import os
from typing import Callable, Dict, List, Optional
from pydantic import BaseModel, Field

from src.modules.lane_b.domain.lane_b_service import LaneBService
from src.modules.lane_b.domain.scanner_service import KillSwitchManager


class FeatureScanRecord(BaseModel):
    feature: str
    status: str  # scanned | blocked | skipped_disabled | skipped_budget | no_logs
    notes: List[str] = Field(default_factory=list)
    kept: int = 0
    rejected: int = 0
    not_comparable_runs: int = 0
    downgrade_recommended: Optional[str] = None


class JobResult(BaseModel):
    period: str
    budget_used: int = 0
    budget_limit: int = 0
    stopped_by_budget: bool = False
    errors: List[str] = Field(default_factory=list)
    features: List[FeatureScanRecord] = Field(default_factory=list)


class ScanJob:
    """
    Scheduled scan (P4-T3 / 02_LANE_B_DESIGN.md sections 3, 7, 8):
    - iterates the registry, honours kill switches (lane_b_enabled=false)
    - stops when the per-run query budget is exhausted (never scans harder)
    - tracks candidate persistence across periods in a history file
    - flags sudden sample drops as Loki anomalies -> recommend auto-downgrade to observe
    Runs only on logs that already exist; it never triggers test runs.
    """

    def __init__(
        self,
        service: LaneBService,
        runs_loader: Callable[[str, str], List[Dict[str, object]]],
        history_filename: str = "scan_history.json",
        sample_drop_ratio: float = 0.5,
    ):
        self.service = service
        self.runs_loader = runs_loader
        self.history_filename = history_filename
        self.sample_drop_ratio = sample_drop_ratio

    # ------------------------------------------------------------- history ---
    def _history_path(self) -> str:
        return os.path.join(self.service.base_dir, "observations", self.history_filename)

    def _load_history(self) -> Dict[str, dict]:
        path = self._history_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"features": {}}

    def _save_history(self, history: Dict[str, dict]) -> None:
        os.makedirs(os.path.dirname(self._history_path()), exist_ok=True)
        with open(self._history_path(), "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------- run ----
    def run(self, period: str) -> JobResult:
        try:
            registry = self.service.registry_service.load()
            policy = self.service.policy_service.get_policy()
        except FileNotFoundError as exc:
            # no policy/registry -> Lane B must not run (B0-R1); never crash the scheduler
            return JobResult(period=period, errors=[str(exc)])
        history = self._load_history()

        result = JobResult(period=period, budget_limit=policy.scan.budget_queries_per_run)

        for entry in registry:
            if result.budget_used >= result.budget_limit:
                result.stopped_by_budget = True
                result.features.append(
                    FeatureScanRecord(
                        feature=entry.feature,
                        status="skipped_budget",
                        notes=["Scan budget exhausted for this run - resume next period (B0-R1)."],
                    )
                )
                continue

            if not entry.lane_b_enabled:
                result.features.append(
                    FeatureScanRecord(
                        feature=entry.feature,
                        status="skipped_disabled",
                        notes=["Kill switch: lane_b_enabled=false (section 8)."],
                    )
                )
                continue

            runs = list(self.runs_loader(entry.feature, period) or [])
            result.budget_used += 1
            if not runs:
                result.features.append(
                    FeatureScanRecord(feature=entry.feature, status="no_logs",
                                      notes=["No existing logs for this period - nothing to scan."])
                )
                continue

            feature_history = history["features"].setdefault(
                entry.feature, {"candidates": {}, "samples": {}}
            )
            previous_samples = list(feature_history["samples"].values())
            anomaly_note = None
            if previous_samples:
                last_samples = previous_samples[-1]
                if last_samples and len(runs) < last_samples * self.sample_drop_ratio:
                    should_downgrade, message = KillSwitchManager.should_auto_downgrade(
                        guardrail_breached=False,
                        loki_data_anomalous=True,
                        feature_revert_rate=0.0,
                    )
                    anomaly_note = message if should_downgrade else None

            # persistence counts periods including the current one
            periods = {step: seen + 1 for step, seen in feature_history["candidates"].items()}
            scan_result = self.service.scan(
                feature_id=entry.feature,
                raw_runs=runs,
                period=period,
                candidate_periods=periods,
            )

            # persistence bookkeeping: candidates seen this period (+1)
            for candidate in scan_result.kept:
                step = candidate.step_name
                feature_history["candidates"][step] = periods.get(step, 1)
            for rejection in scan_result.rejected:
                if rejection.stage == "persistence":
                    step = rejection.item
                    feature_history["candidates"][step] = periods.get(step, 1)
            feature_history["samples"][period] = sum(
                1 for r in runs if r.get("status") == "success"
            )
            self._save_history(history)

            notes: List[str] = []
            if scan_result.not_comparable_runs:
                notes.append(
                    f"{scan_result.not_comparable_runs} run(s) not_comparable - never merged (B1-R2)."
                )
            if scan_result.blocked:
                result.features.append(
                    FeatureScanRecord(
                        feature=entry.feature,
                        status="blocked",
                        notes=scan_result.blocked_reasons,
                    )
                )
                continue

            result.features.append(
                FeatureScanRecord(
                    feature=entry.feature,
                    status="scanned",
                    notes=notes,
                    kept=len(scan_result.kept),
                    rejected=len(scan_result.rejected),
                    not_comparable_runs=scan_result.not_comparable_runs,
                    downgrade_recommended=anomaly_note,
                )
            )

        self._save_history(history)
        return result
