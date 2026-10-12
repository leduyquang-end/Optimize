import re
from typing import List, Optional, Sequence, Tuple
from src.core.schemas.solution import SolutionProposal
from src.core.schemas.brief import RiskTier, RISK_TIER_ORDER
from src.core.schemas.policy import SystemPolicy

class SelfCriticismEngine:
    """
    Lane B Self-Criticism Engine (02_LANE_B_DESIGN.md section 6.3):
    - B2-C1: Does not violate guardrails in Policy or Business Rule Card
    - B2-C2: Verified root cause matches evidence without data contradiction
    - B2-C3: Does not duplicate reverted direction in Lessons Store
    - B2-C4: Modifies exactly 1 variable and has explicit rollback
    - B2-C5: Expected impact is a range with reasonable lower bound
    - B2-C6: Does not target steps marked mandatory in Business Rule Card
    """
    NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")

    @classmethod
    def audit_proposal(
        cls,
        proposal: SolutionProposal,
        policy: SystemPolicy,
        past_reverted_changes: Optional[Sequence[str]] = None,
        must_keep_steps: Optional[Sequence[str]] = None,
    ) -> Tuple[bool, List[str]]:
        rejections = []

        # B2-C1: declared trade-off against a hard guardrail metric
        hard_guardrails = {g.metric for g in policy.default_guardrails if g.hard}
        for tradeoff in proposal.guardrail_tradeoffs:
            if any(metric in tradeoff for metric in hard_guardrails):
                rejections.append(
                    f"B2-C1 Rejected: Proposal trades off hard guardrail '{tradeoff}' from policy."
                )

        # B2-C2: verified root cause must carry direct evidence
        if proposal.is_unverified_hypothesis or not proposal.verified_root_cause.statement:
            rejections.append("B2-C2 Rejected: Proposal root cause lacks verified evidence.")
        elif not (
            proposal.verified_root_cause.evidence_log_lines
            or proposal.verified_root_cause.kg_nodes
            or proposal.verified_root_cause.code_references
        ):
            rejections.append(
                "B2-C2 Rejected: Root cause has no direct evidence (log, KG or code reference)."
            )

        # B2-C3: never re-propose a direction already reverted (no new condition)
        if past_reverted_changes:
            changed = " ".join(proposal.change.variables) + " " + proposal.proposed_change
            for reverted in past_reverted_changes:
                if reverted and reverted in changed:
                    rejections.append(
                        f"B2-C3 Rejected: Direction already reverted in lessons store: '{reverted}'."
                    )
                    break

        # B2-C4: exactly one variable and an explicit rollback
        if len(proposal.change.variables) != 1:
            rejections.append(
                f"B2-C4 Rejected: Proposal must change exactly 1 variable, got {len(proposal.change.variables)}."
            )
        if not proposal.rollback_action:
            rejections.append("B2-C4 Rejected: Proposal missing explicit rollback plan.")

        # B2-C5: expected impact must be a range with numeric bound(s)
        if not proposal.expected_impact_range or len(cls.NUMBER_PATTERN.findall(proposal.expected_impact_range)) < 2:
            rejections.append(
                "B2-C5 Rejected: Expected impact must be a range with lower and upper bound."
            )

        # B2-C6: Business Rule Card mandatory-keep steps are out of scope
        if must_keep_steps:
            target = " ".join(proposal.change.variables) + " " + proposal.change.blast_radius + " " + proposal.proposed_change
            for step in must_keep_steps:
                if step and step in target:
                    rejections.append(
                        f"B2-C6 Rejected: Proposal targets step '{step}' which the Business Rule Card "
                        "marks as mandatory to keep."
                    )

        # Risk ceiling (B2-R5)
        if RISK_TIER_ORDER[proposal.risk_tier] > RISK_TIER_ORDER[policy.max_risk_tier]:
            proposal.over_ceiling = True
            rejections.append(
                f"Policy Ceiling Violation: Proposal risk tier '{proposal.risk_tier}' exceeds "
                f"Policy ceiling '{policy.max_risk_tier}'."
            )

        is_passed = len(rejections) == 0
        return is_passed, rejections
