from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict

Severity = Literal["OK", "POSSIBLE_WARN", "DIRECT_WARN"]

class MccRule(BaseModel):
    mcc: str
    severity: Severity
    reason: str

class KeywordRule(BaseModel):
    pattern: str
    severity: Severity
    reason: str

class AmountRule(BaseModel):
    scope: Literal["global"] = "global"
    min_amount: float
    severity: Severity
    reason: str

class Catalog(BaseModel):
    version: str = "1.0.0"
    allowlist_merchants: List[str] = Field(default_factory=list)
    mcc_rules: List[MccRule] = Field(default_factory=list)
    keyword_rules: List[KeywordRule] = Field(default_factory=list)
    amount_rules: List[AmountRule] = Field(default_factory=list)

    def to_dict(self) -> Dict:
        return self.model_dump()
