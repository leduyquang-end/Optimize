from typing import Dict, List, Optional
from pydantic import BaseModel, Field

class StepBreakdown(BaseModel):
    step_name: str
    pct_of_total_time: float
    p50_latency_ms: float
    p90_latency_ms: float
    p99_latency_ms: float
    avg_token_count: Optional[float] = None
    is_critical_path: bool = False
    retry_rate: Optional[float] = Field(
        default=None, description="B1 signal: retry ratio of the step"
    )
    parallelizable: bool = False

class BaselineReport(BaseModel):
    """
    Schema for Baseline Measurement (A2 / B1) - 01_LANE_A_DESIGN.md section 4.2
    """
    snapshot_id: str
    feature_id: str
    fingerprint: Optional[str] = Field(
        default=None, description="FP-1: hash of feature+rule_set+rule_variant+steps+env"
    )
    time_window_start: str
    time_window_end: str
    sample_count: int
    excluded_runs: List[Dict[str, object]] = Field(
        default_factory=list, description="A2-R3: excluded runs with reason"
    )
    is_weak_baseline: bool = False
    weak_baseline_reason: Optional[str] = None
    total_p50_latency_ms: float
    total_p90_latency_ms: float
    total_p99_latency_ms: float
    step_breakdowns: List[StepBreakdown]
    active_configs: Dict[str, str]
    config_mismatch: List[str] = Field(
        default_factory=list, description="A2-V4: code config vs log config diff"
    )
    config_mismatch_explained: Optional[str] = None
    config_change_in_window: bool = Field(
        default=False, description="A2-V6: window must contain no config change event"
    )
    fingerprint_mismatch_count: int = Field(
        default=0, description="A2-V1: log rows whose fingerprint does not match"
    )
    replication_delta_pct: Optional[float] = Field(
        default=None, description="A2-V5: second-person re-query delta (allowed <= 1%)"
    )
    queries: List[str] = Field(
        default_factory=list, description="LogQL used, every number must trace back to a query"
    )
    data_gaps: List[str] = Field(default_factory=list)
    brief_id: Optional[str] = Field(
        default=None, description="A1: Optimization Brief đã qua Cổng 1 làm căn cứ cho baseline này"
    )
    created_by: str = "lane_a"
    source_lane: str = "A"
    immutable: bool = True
