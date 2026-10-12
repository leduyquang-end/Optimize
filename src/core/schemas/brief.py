from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field

class RiskTier(str, Enum):
    CONFIG = "config"
    PROMPT = "prompt"
    CODE = "code"

RISK_TIER_ORDER = {RiskTier.CONFIG: 1, RiskTier.PROMPT: 2, RiskTier.CODE: 3}

class OptimizationTarget(BaseModel):
    metric_name: str
    unit: str
    direction: str = Field(description="decrease|increase (docs: down|up)")
    current_value: Optional[float] = None
    target_value: float
    priority: int = Field(default=1, description="A1-V5: rank when objectives conflict")
    measurement_source: str = Field(
        default="",
        description="A1-V2: query or code reference proving the metric is measurable"
    )

class Guardrail(BaseModel):
    metric_name: str
    max_allowed_change_pct: float
    hard: bool = Field(default=True, description="A1-V3: hard guardrails are never traded off")

class Threshold(BaseModel):
    keep_improvement_pct: float = 25.0
    revert_improvement_pct: float = 10.0

class OptimizationBrief(BaseModel):
    """
    7 Components of A1 Input Brief (01_LANE_A_DESIGN.md section 4.1)
    """
    brief_id: Optional[str] = None
    feature_id: str = Field(..., description="Feature name + fingerprint (e.g. Feature_X_v2_subflow6_prod)")
    optimization_targets: List[OptimizationTarget]
    guardrails: List[Guardrail]
    thresholds: Threshold
    max_risk_tier: RiskTier = RiskTier.PROMPT
    scope_in: List[str]
    scope_out: List[str]
    business_context: str
    business_rule_card: Optional[str] = Field(
        default=None, description="A1-V6: path to the Business Rule Card"
    )
    business_rule_card_confirmed: bool = Field(
        default=False, description="A1-V6: confirmed by domain owner"
    )
    data_gaps: List[str] = Field(
        default_factory=list, description="A1/A2: metrics with no log source"
    )
    status: str = Field(default="draft", description="draft | needs_clarification | validated | closed")
