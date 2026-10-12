import json
import os
from typing import List, Optional
from src.core.schemas.policy import SystemPolicy, FeatureRegistryEntry, FeatureMode

__all__ = ["SystemPolicy", "FeatureRegistryEntry", "FeatureMode", "PolicyService", "RegistryService"]

class PolicyService:
    """
    B0 (02_LANE_B_DESIGN.md section 4): Lane B may not run without a valid policy.
    Policy file is owned by the program owner; this service only reads it.
    """
    def __init__(self, base_dir: str = "optimization_data", policy_filename: str = "policy.json"):
        self.filepath = os.path.join(base_dir, "policy", policy_filename)
        self._policy: Optional[SystemPolicy] = None

    def get_policy(self) -> SystemPolicy:
        if self._policy is None:
            if not os.path.exists(self.filepath):
                raise FileNotFoundError(
                    f"B0-R1: Policy not found at '{self.filepath}'. Lane B must not run without a policy."
                )
            with open(self.filepath, "r", encoding="utf-8") as f:
                self._policy = SystemPolicy(**json.load(f))
        return self._policy

    @staticmethod
    def is_feature_registered(feature_id: str, registry: Optional[List[FeatureRegistryEntry]] = None) -> bool:
        if registry is None:
            return True
        return any(feature_id.startswith(entry.feature) for entry in registry)


class RegistryService:
    """
    Feature registry (02_LANE_B_DESIGN.md section 4.2): feature without a registry
    entry or Business Rule Card may not be scanned or proposed.
    """
    def __init__(self, base_dir: str = "optimization_data", registry_filename: str = "features.json"):
        self.filepath = os.path.join(base_dir, "registry", registry_filename)

    def load(self) -> List[FeatureRegistryEntry]:
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(
                f"B0-R1: Feature registry not found at '{self.filepath}'. Lane B must not run."
            )
        with open(self.filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [FeatureRegistryEntry(**entry) for entry in raw.get("features", raw if isinstance(raw, list) else [])]

    @staticmethod
    def entry_for(registry: List[FeatureRegistryEntry], feature_id: str) -> Optional[FeatureRegistryEntry]:
        for entry in registry:
            if feature_id.startswith(entry.feature):
                return entry
        return None
