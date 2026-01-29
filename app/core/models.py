from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Optional

Severity = Literal["OK", "POSSIBLE_WARN", "DIRECT_WARN"]

# --- Reglas Básicas ---
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

# --- Reglas Nuevas (v1.2.0) ---
class MccDescriptionRule(BaseModel):
    pattern: str
    condition: Optional[str] = None  # Ej: "amount > 500"
    severity: Severity
    reason: str

class PurchaseCategoryRule(BaseModel):
    category: str
    condition: Optional[str] = None
    severity: Severity
    reason: str
    exclude_patterns: List[str] = Field(default_factory=list)

class Catalog(BaseModel):
    version: str = "1.2.0"
    
    allowlist_merchants: List[str] = Field(default_factory=list)
    disallowed_keywords: List[str] = Field(default_factory=list)  # Lista simple
    
    mcc_rules: List[MccRule] = Field(default_factory=list)
    keyword_rules: List[KeywordRule] = Field(default_factory=list)
    amount_rules: List[AmountRule] = Field(default_factory=list)
    
    # Nuevas secciones
    mcc_description_rules: List[MccDescriptionRule] = Field(default_factory=list)
    purchase_category_rules: List[PurchaseCategoryRule] = Field(default_factory=list)

    def to_dict(self) -> Dict:
        return self.model_dump()