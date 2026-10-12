import hashlib
import json
from pydantic import BaseModel, Field

class Fingerprint(BaseModel):
    """
    Fingerprint schema for identifying identical execution contexts (FP-1 to FP-4)
    """
    feature: str = Field(..., description="Feature identifier")
    rule_set: str = Field(..., description="Rule-set version")
    rule_variant: str = Field(..., description="Variant affecting business complexity")
    subflow_steps: int = Field(default=6, description="Number of subflow steps")
    env: str = Field(default="prod", description="Environment")

    def compute_hash(self) -> str:
        data = {
            "feature": self.feature,
            "rule_set": self.rule_set,
            "rule_variant": self.rule_variant,
            "subflow_steps": self.subflow_steps,
            "env": self.env
        }
        encoded = json.dumps(data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]
