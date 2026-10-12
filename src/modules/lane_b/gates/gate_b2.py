from typing import Tuple, List
from src.core.schemas.solution import SolutionProposal
from src.modules.policy_registry.domain.policy_service import SystemPolicy

class GateB2Evaluator:
    """
    Gate B2: Self-Criticism & Policy Enforcement Check for B2 Proposals
    """
    @staticmethod
    def validate(proposal: SolutionProposal, policy: SystemPolicy) -> Tuple[bool, List[str]]:
        errors = []
        
        # Check verified root cause
        if not proposal.verified_root_cause.statement:
            errors.append("Gate B2 Failed: Missing verified root cause statement.")

        # Risk tier ceiling check
        risk_hierarchy = {"config": 1, "prompt": 2, "code": 3}
        if risk_hierarchy[proposal.risk_tier.value] > risk_hierarchy[policy.max_risk_tier.value]:
            errors.append(f"Gate B2 Failed: Proposal risk tier '{proposal.risk_tier}' exceeds Policy ceiling '{policy.max_risk_tier}'.")

        # Rollback plan check
        if not proposal.rollback_plan:
            errors.append("Gate B2 Failed: Proposal must include an explicit rollback plan.")

        is_passed = len(errors) == 0
        return is_passed, errors
