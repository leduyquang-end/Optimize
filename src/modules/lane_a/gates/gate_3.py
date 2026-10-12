import re
from typing import Tuple, List
from src.core.schemas.solution import SolutionProposal

class Gate3Evaluator:
    """
    Gate 3 Validation (01_LANE_A_DESIGN.md section 5):
    - A3-V1: 100% main solutions have evidence & verified status
    - A3-V2: Every solution has pros_cons for objectives & guardrails
    - A3-V3: Has remeasure_plan and rollback
    - A3-V4: expected_impact is a range (low/high)
    - A3-V5: Solution modifies exactly 1 variable
    - A3-V6: Hypothesis solutions stay out of the main list
    """
    RANGE_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

    @classmethod
    def validate(cls, proposal: SolutionProposal) -> Tuple[bool, List[str]]:
        errors = []

        # A3-V1 / A3-V6
        if proposal.is_unverified_hypothesis:
            errors.append("A3-V1 Failed: Hypothesis solutions cannot be in the main solution list (A3-V6).")
        elif not proposal.verified_root_cause.statement:
            errors.append("A3-V1 Failed: Solution missing verified root cause statement.")
        elif not (
            proposal.verified_root_cause.evidence_log_lines
            or proposal.verified_root_cause.kg_nodes
            or proposal.verified_root_cause.code_references
        ):
            errors.append(
                "A3-V1 Failed: Verified root cause needs direct evidence (log line, KG node or code reference)."
            )

        # A3-V2: pros AND cons, and per-criterion matrix covering objectives/guardrails
        if not proposal.pros or not proposal.cons:
            errors.append("A3-V2 Failed: Solution must specify pros and cons for objectives and guardrails.")
        if not proposal.pros_cons:
            errors.append(
                "A3-V2 Failed: Solution must fill pros_cons for every objective and guardrail criterion."
            )

        # A3-V3
        if not proposal.retest_plan or not proposal.rollback_action:
            errors.append("A3-V3 Failed: Solution must have explicit remeasure plan and rollback.")

        # A3-V4: numeric range with lower and upper bound
        numbers = cls.RANGE_PATTERN.findall(proposal.expected_impact_range)
        if len(numbers) < 2:
            errors.append(
                f"A3-V4 Failed: expected_impact '{proposal.expected_impact_range}' must be a range "
                "with a lower and an upper bound (e.g. -10% to -20%)."
            )

        # A3-V5: exactly one variable per solution
        if len(proposal.change.variables) != 1:
            errors.append(
                f"A3-V5 Failed: Solution must change exactly 1 variable, got {len(proposal.change.variables)}."
            )

        is_passed = len(errors) == 0
        return is_passed, errors
