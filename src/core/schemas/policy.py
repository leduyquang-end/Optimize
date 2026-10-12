from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.schemas.brief import RiskTier

class FeatureMode(str, Enum):
    OBSERVE = "observe"
    PROPOSE = "propose"

class FeatureVariant(BaseModel):
    fingerprint: str
    rule_set: str
    subflow_steps: int = 6
    env: str = "prod"

class FeatureRegistryEntry(BaseModel):
    feature: str
    variants: List[FeatureVariant] = Field(default_factory=list)
    steps: List[str] = Field(default_factory=list)
    business_rule_card: str = Field(..., description="Path to Business Rule Card")
    domain_owner: str
    lane_b_enabled: bool = False
    mode: FeatureMode = FeatureMode.OBSERVE

class ScanPolicy(BaseModel):
    schedule: str = "weekly"
    budget_queries_per_run: int = 100
    top_k: int = 3

class DefaultObjective(BaseModel):
    metric: str
    direction: str = "down"

class DefaultGuardrail(BaseModel):
    metric: str
    rule: str
    hard: bool = True

class PersistencePolicy(BaseModel):
    min_periods: int = 2
    share_threshold: float = 0.25

class AlertTrigger(BaseModel):
    metric: str
    condition: str

class SystemPolicy(BaseModel):
    policy_id: str = "POL-001"
    version: int = 1
    effective_from: str
    expires_at: Optional[str] = Field(
        default=None, description="B0: Lane B stops when the policy is expired"
    )
    approved_by: str
    scan: ScanPolicy = Field(default_factory=ScanPolicy)
    default_objectives: List[DefaultObjective] = Field(default_factory=list)
    default_guardrails: List[DefaultGuardrail] = Field(default_factory=list)
    max_risk_tier: RiskTier = RiskTier.CONFIG
    persistence: PersistencePolicy = Field(default_factory=PersistencePolicy)
    min_runs: int = 30
    alert_triggers: List[AlertTrigger] = Field(default_factory=list)
