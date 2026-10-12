from typing import List, Optional
from pydantic import BaseModel, Field
from src.core.schemas.brief import RiskTier

class ChangeDescription(BaseModel):
    description: str
    variables: List[str] = Field(default_factory=lambda: ["STEP3_SUBFLOW_MAX_STEPS"])
    risk_tier: RiskTier = RiskTier.CONFIG
    blast_radius: str = "step3"

class VerifiedRootCause(BaseModel):
    statement: str
    evidence_log_lines: List[str] = Field(default_factory=list)
    kg_nodes: List[str] = Field(default_factory=list)
    code_references: List[str] = Field(default_factory=list)

class ProsCons(BaseModel):
    criterion: str
    pros: str = ""
    cons: str = ""

class RemeasurePlan(BaseModel):
    compare_to: str = "S-0012"
    same_fingerprint: bool = True
    window_days: int = 7
    min_runs: int = 30

class RollbackPlan(BaseModel):
    action: str = ""
    owner: str = "unassigned"

class SolutionProposal(BaseModel):
    """
    SolutionCard (03_SHARED_AND_SECTION_2_DESIGN.md section 4)
    """
    solution_id: str
    feature_id: str
    source_lane: str = Field(default="A", description="A or B")
    snapshot_id: str = "S-0012"
    verified_root_cause: VerifiedRootCause
    proposed_change: str
    change: ChangeDescription = Field(default_factory=lambda: ChangeDescription(description="STEP3_SUBFLOW_MAX_STEPS 6 -> 3"))
    risk_tier: RiskTier = RiskTier.CONFIG
    blast_radius: str = "step3"
    pros: List[str] = Field(default_factory=list)
    cons: List[str] = Field(default_factory=list)
    pros_cons: List[ProsCons] = Field(
        default_factory=list, description="A3-V2: per objective and guardrail"
    )
    expected_impact_range: str = Field(default="-10% to -20%")
    effort_estimate: str = Field(default="Small")
    retest_plan: str = "Compare to S-0012"
    remeasure_plan: Optional[RemeasurePlan] = None
    rollback_plan: str = "Revert to 6"
    rollback: Optional[RollbackPlan] = None
    dependencies: List[str] = Field(default_factory=list)
    conflicts_with: List[str] = Field(default_factory=list)
    guardrail_tradeoffs: List[str] = Field(
        default_factory=list,
        description="B2-C1: explicit trade-off declared against a guardrail metric",
    )
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence_level: Optional[str] = Field(
        default=None, description="B2-R4: high | medium | low"
    )
    is_unverified_hypothesis: bool = False
    over_ceiling: bool = False

    @property
    def rollback_action(self) -> str:
        return self.rollback.action if self.rollback else self.rollback_plan
