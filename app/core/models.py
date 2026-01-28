from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Optional

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

# --- NUEVOS MODELOS PARA SOPORTAR EL JSON V1.1.0 ---

class AllowlistPattern(BaseModel):
    pattern: str
    reason: str

class KeywordException(BaseModel):
    pattern: str
    override_severity: Severity
    reason: str

class Catalog(BaseModel):
    version: str = "1.0.0"
    allowlist_merchants: List[str] = Field(default_factory=list)
    
    # Nuevos campos
    allowlist_patterns: List[AllowlistPattern] = Field(default_factory=list)
    keyword_exceptions: List[KeywordException] = Field(default_factory=list)
    
    mcc_rules: List[MccRule] = Field(default_factory=list)
    keyword_rules: List[KeywordRule] = Field(default_factory=list)
    amount_rules: List[AmountRule] = Field(default_factory=list)
    
    # Campos informativos o para uso futuro (metadatos)
    category_lists: Dict[str, List[str]] = Field(default_factory=dict)
    sources: Dict[str, str] = Field(default_factory=dict)

    def to_dict(self) -> Dict:
        return self.model_dump()