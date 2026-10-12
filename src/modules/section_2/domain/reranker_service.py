import re
from typing import Dict, List, Tuple
from src.core.schemas.solution import SolutionProposal
from src.core.schemas.brief import RiskTier, RISK_TIER_ORDER

class RerankerService:
    """
    Step 01 Re-ranker (03_SHARED_AND_SECTION_2_DESIGN.md section 8):
    - decision mode: auto_rerank_notify (config, narrow blast, instant rollback)
                     auto_rerank_human_pick (prompt)
                     human_decides (code / important feature / low confidence)
    - S01-R1: rank by the conservative bound of expected impact on priority 1,
      then next criterion, then lower risk tier, then smaller effort
    - S01-R2: guardrail violation or over ceiling is excluded, never down-weighted
    - S01-R3: every select/exclude carries a reason
    - S01-R4: conflicting solutions are not selected together
    """
    WIDE_MARKERS = ("global", "wide", "entire", "all traffic", "whole system")
    NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")
    EFFORT_ORDER = {"s": 0, "small": 0, "m": 1, "medium": 1, "l": 2, "large": 2}

    @classmethod
    def determine_decision_mode(cls, proposal: SolutionProposal) -> str:
        blast = str(proposal.change.blast_radius).lower()
        narrow = not any(marker in blast for marker in cls.WIDE_MARKERS)
        instant_rollback = bool(proposal.rollback_action)

        if proposal.confidence_score < 0.6:
            return "human_decides"
        if proposal.risk_tier == RiskTier.CONFIG and narrow and instant_rollback:
            return "auto_rerank_notify"
        if proposal.risk_tier == RiskTier.PROMPT:
            return "auto_rerank_human_pick"
        return "human_decides"

    @classmethod
    def _conservative_impact(cls, proposal: SolutionProposal) -> float:
        numbers = cls.NUMBER_PATTERN.findall(proposal.expected_impact_range)
        return abs(float(numbers[0])) if numbers else 0.0

    @classmethod
    def _sort_key(cls, proposal: SolutionProposal):
        effort = cls.EFFORT_ORDER.get(str(proposal.effort_estimate).strip().lower(), 9)
        return (-cls._conservative_impact(proposal), RISK_TIER_ORDER[proposal.risk_tier], effort)

    @classmethod
    def rerank_solutions(cls, proposals: List[SolutionProposal]) -> Tuple[List[SolutionProposal], List[Dict[str, str]]]:
        ranked: List[SolutionProposal] = []
        excluded: List[Dict[str, str]] = []
        selected_ids = set()

        for p in sorted(proposals, key=cls._sort_key):
            if p.over_ceiling:
                excluded.append({
                    "id": p.solution_id,
                    "reason": "S01-R2: over risk ceiling and not lifted yet - excluded, not down-weighted.",
                })
                continue
            if p.is_unverified_hypothesis:
                excluded.append({
                    "id": p.solution_id,
                    "reason": "S01-R2: unverified hypothesis cannot enter the main list (A3-V6).",
                })
                continue
            if p.guardrail_tradeoffs:
                excluded.append({
                    "id": p.solution_id,
                    "reason": f"S01-R2: trades off guardrail {p.guardrail_tradeoffs} - excluded.",
                })
                continue
            conflicts = any(c in selected_ids for c in p.conflicts_with) or any(
                p.solution_id in chosen.conflicts_with for chosen in ranked
            )
            if conflicts:
                excluded.append({
                    "id": p.solution_id,
                    "reason": "S01-R4: conflicts with an already selected solution.",
                })
                continue

            ranked.append(p)
            selected_ids.add(p.solution_id)

        return ranked, excluded
