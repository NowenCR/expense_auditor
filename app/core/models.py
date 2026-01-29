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

class MccDescriptionRule(BaseModel):
    pattern: str
    condition: Optional[str] = None
    severity: Severity
    reason: str

class PurchaseCategoryRule(BaseModel):
    category: str
    condition: Optional[str] = None
    severity: Severity
    reason: str
    exclude_patterns: List[str] = Field(default_factory=list)

# --- NUEVO MODELO PARA SOPORTAR REGEX EN ALLOWLIST ---
class AllowlistPattern(BaseModel):
    pattern: str
    reason: str

class Catalog(BaseModel):
    version: str = "1.3.0"
    
    # Listas blancas
    allowlist_merchants: List[str] = Field(default_factory=list) # Exact match
    allowlist_patterns: List[AllowlistPattern] = Field(default_factory=list) # Regex match (Nuevo)
    
    # Listas negras
    disallowed_keywords: List[str] = Field(default_factory=list)

    # Reglas
    mcc_rules: List[MccRule] = Field(default_factory=list)
    keyword_rules: List[KeywordRule] = Field(default_factory=list)
    amount_rules: List[AmountRule] = Field(default_factory=list)
    mcc_description_rules: List[MccDescriptionRule] = Field(default_factory=list)
    purchase_category_rules: List[PurchaseCategoryRule] = Field(default_factory=list)

    def to_dict(self) -> Dict:
        return self.model_dump()    