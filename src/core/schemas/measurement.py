from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class ValidityCheckResult(BaseModel):
    v1_same_fingerprint: bool = Field(description="V-1: Same fingerprint in both snapshots")
    v2_same_business_complexity: bool = Field(description="V-2: Same rule_set, rule_variant, run distribution")
    v3_equivalent_conditions: bool = Field(description="V-3: No outages, deploys, or spikes in window")
    v4_sufficient_sample_size: bool = Field(description="V-4: runs >= min_runs on both sides")
    v5_single_variable_diff: bool = Field(description="V-5: Config diff shows exactly 1 variable changed")
    v6_distribution_provided: bool = Field(description="V-6: Has p50, p90, p99 on both sides")

    def all_passed(self) -> bool:
        return (
            self.v1_same_fingerprint and
            self.v2_same_business_complexity and
            self.v3_equivalent_conditions and
            self.v4_sufficient_sample_size and
            self.v5_single_variable_diff and
            self.v6_distribution_provided
        )

class MeasurementReport(BaseModel):
    phase_id: str
    compare_snapshot_before: str
    compare_snapshot_after: str
    validity_checks: ValidityCheckResult
    latency_p50_change_pct: float
    latency_p90_change_pct: float
    latency_p99_change_pct: float
    tokens_change_pct: Optional[float] = 0.0
    guardrail_breached: bool = False
    is_valid_comparison: bool = True
