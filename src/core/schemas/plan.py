from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.schemas.brief import RiskTier

class PhasePlanItem(BaseModel):
    phase_id: str
    change_variable: str = Field(description="Exactly one variable modified in this phase")
    risk_tier: RiskTier
    done_criteria: str = Field(description="Numeric expression for phase completion")
    tests: List[str] = Field(default_factory=list, description="Unit tests & guardrail checks")
    remeasure_compare_to: str = Field(description="Snapshot ID to compare against")
    remeasure_window_days: int = 7
    remeasure_min_runs: int = 30
    rollback_action: str = Field(description="Explicit rollback procedure")
    rollback_owner: str
    depends_on: List[str] = Field(default_factory=list)
    owner: str

class FullSolutionPlan(BaseModel):
    solution_id: str
    revision: int = 1
    phases: List[PhasePlanItem]
