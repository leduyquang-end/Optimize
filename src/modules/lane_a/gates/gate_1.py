from typing import Tuple, List
from src.core.schemas.brief import OptimizationBrief

class Gate1Evaluator:
    """
    Gate 1 Validation (01_LANE_A_DESIGN.md section 5):
    - A1-V1: 1 brief = 1 feature + 1 rule variant
    - A1-V2: Every objective has a numeric target and a measurable data source
    - A1-V3: Has at least 1 hard guardrail
    - A1-V4: keep_if > revert_if, both fixed before seeing numbers
    - A1-V5: Conflicting objectives must carry distinct priorities
    - A1-V6: Business Rule Card confirmed by the domain owner
    """
    VALID_DIRECTIONS = {"decrease", "increase", "down", "up"}

    @classmethod
    def validate(cls, brief: OptimizationBrief) -> Tuple[bool, List[str]]:
        errors = []

        # A1-V1: exactly one feature / rule variant per brief
        if not brief.feature_id or not brief.feature_id.strip():
            errors.append("A1-V1 Failed: Must specify exactly 1 feature and rule variant fingerprint.")

        # A1-V2: numeric target + measurement source for every objective
        if not brief.optimization_targets:
            errors.append("A1-V2 Failed: Must specify at least one optimization target with numeric goal.")
        else:
            for tgt in brief.optimization_targets:
                if tgt.target_value is None or tgt.target_value <= 0:
                    errors.append(
                        f"A1-V2 Failed: Objective '{tgt.metric_name}' is missing a positive numeric target_value."
                    )
                if not tgt.unit:
                    errors.append(f"A1-V2 Failed: Objective '{tgt.metric_name}' has no unit.")
                if tgt.direction not in cls.VALID_DIRECTIONS:
                    errors.append(
                        f"A1-V2 Failed: Objective '{tgt.metric_name}' direction '{tgt.direction}' is not measurable/defined."
                    )
                if not tgt.measurement_source:
                    errors.append(
                        f"A1-V2 Failed: Objective '{tgt.metric_name}' has no measurement source (Loki query / code ref)."
                    )

        # A1-V3: at least one hard guardrail, never traded off
        if not any(g.hard for g in brief.guardrails):
            errors.append("A1-V3 Failed: Brief must specify at least one hard guardrail constraint.")

        # A1-V4: thresholds fixed upfront and consistent
        thr = brief.thresholds
        if thr.keep_improvement_pct is None or thr.revert_improvement_pct is None:
            errors.append("A1-V4 Failed: Brief must specify explicit keep_if and revert_if thresholds.")
        elif thr.revert_improvement_pct <= 0 or thr.keep_improvement_pct <= thr.revert_improvement_pct:
            errors.append(
                f"A1-V4 Failed: keep_if ({thr.keep_improvement_pct}%) must be greater than revert_if "
                f"({thr.revert_improvement_pct}%) and both must be positive."
            )

        # A1-V5: conflicting objectives need distinct priorities
        by_metric = {}
        for tgt in brief.optimization_targets:
            by_metric.setdefault(tgt.metric_name, []).append(tgt)
        for metric, targets in by_metric.items():
            if len(targets) < 2:
                continue
            directions = {t.direction for t in targets}
            if len(directions) > 1:
                priorities = [t.priority for t in targets]
                if len(set(priorities)) != len(priorities):
                    errors.append(
                        f"A1-V5 Failed: Objectives for '{metric}' conflict (opposite directions) and "
                        "priorities are not distinct."
                    )

        # A1-V6: Business Rule Card confirmed by domain owner
        if not brief.business_context:
            errors.append("A1-V6 Failed: Business Rule Card context is missing.")
        if not brief.business_rule_card:
            errors.append("A1-V6 Failed: Business Rule Card path is missing.")
        elif not brief.business_rule_card_confirmed:
            errors.append("A1-V6 Failed: Business Rule Card is not confirmed by the domain owner.")

        is_passed = len(errors) == 0
        return is_passed, errors
