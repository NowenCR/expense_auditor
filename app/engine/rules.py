from __future__ import annotations
import pandas as pd
import numpy as np
from app.core.constants import Flag, FLAG_PRIORITY
from app.core.models import Catalog

def _combine_flags(curr_flag: pd.Series, new_flag: Flag) -> pd.Series:
    """Sube la severidad si la nueva es mayor (OK < POSSIBLE < DIRECT)."""
    return np.where(
        curr_flag.map(lambda x: FLAG_PRIORITY[Flag(x)]) < FLAG_PRIORITY[new_flag],
        new_flag.value,
        curr_flag
    )

def _evaluate_condition(df: pd.DataFrame, condition: str) -> pd.Series:
    """
    Evalúa condiciones complejas. Ej: "amount > 500 and purchase_category != 'Lodging'"
    Retorna máscara booleana.
    """
    if not condition:
        return pd.Series(True, index=df.index)
    try:
        indices = df.query(condition).index
        mask = pd.Series(False, index=df.index)
        mask.loc[indices] = True
        return mask
    except Exception:
        return pd.Series(False, index=df.index)

def apply_rules(df: pd.DataFrame, catalog: Catalog) -> pd.DataFrame:
    out = df.copy()

    out["flag"] = Flag.OK.value
    out["reasons"] = ""
    
    # --- CONTROL DE PRIORIDAD ---
    # content_matched: True si alguna regla de contenido (Keyword, MCC, Category)
    # ya clasificó la transacción. Usaremos esto para filtrar la regla de monto.
    content_matched = pd.Series(False, index=out.index)

    # 1. ALLOWLIST (Pre-cálculo)
    allow_mask = pd.Series(False, index=out.index)
    if catalog.allowlist_merchants and "merchant" in out.columns:
        m = out["merchant"].str.lower()
        for a in catalog.allowlist_merchants:
            if a.strip():
                allow_mask |= m.str.contains(a.lower(), regex=False)

    # 2. DISALLOWED KEYWORDS (Lista simple -> DIRECT_WARN)
    if catalog.disallowed_keywords and "merchant" in out.columns:
        m = out["merchant"].astype(str)
        for pat in catalog.disallowed_keywords:
            mask = m.str.contains(pat, case=False, na=False, regex=True)
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag.DIRECT_WARN)
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | Prohibido: " + pat
                content_matched |= mask

    # 3. MCC RULES
    if catalog.mcc_rules and "mcc" in out.columns:
        mcc_s = out["mcc"].astype(str)
        for rule in catalog.mcc_rules:
            mask = (mcc_s == str(rule.mcc))
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 4. KEYWORD RULES (Objetos complejos)
    if catalog.keyword_rules and "merchant" in out.columns:
        m = out["merchant"].astype(str)
        for rule in catalog.keyword_rules:
            mask = m.str.contains(rule.pattern, case=False, na=False, regex=True)
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 5. MCC DESCRIPTION RULES (Regex + Condition)
    if catalog.mcc_description_rules and "mcc_description" in out.columns:
        desc = out["mcc_description"].astype(str)
        for rule in catalog.mcc_description_rules:
            mask_pat = desc.str.contains(rule.pattern, case=False, na=False, regex=True)
            mask_cond = _evaluate_condition(out, rule.condition)
            mask = mask_pat & mask_cond
            
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 6. PURCHASE CATEGORY RULES (Exact Match + Condition + Excludes)
    if catalog.purchase_category_rules and "purchase_category" in out.columns:
        pcat = out["purchase_category"].astype(str)
        merchant = out["merchant"].astype(str)
        for rule in catalog.purchase_category_rules:
            # Coincidencia de categoría
            mask_cat = pcat.str.lower() == rule.category.lower()
            # Condición extra
            mask_cond = _evaluate_condition(out, rule.condition)
            # Exclusiones (ej. florist en Entertainment)
            mask_excl = pd.Series(False, index=out.index)
            if rule.exclude_patterns:
                for pat in rule.exclude_patterns:
                    mask_excl |= merchant.str.contains(pat, case=False, na=False, regex=True)
            
            mask = (mask_cat & mask_cond) & (~mask_excl)
            
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 7. AMOUNT RULES (MENOR PRIORIDAD)
    # Solo aplicamos si content_matched es False
    if catalog.amount_rules and "amount" in out.columns:
        amt = pd.to_numeric(out["amount"], errors="coerce").fillna(0)
        for rule in catalog.amount_rules:
            mask_amt = amt >= float(rule.min_amount)
            # AQUI ESTA LA MAGIA: Solo si NO hay match de contenido previo
            mask = mask_amt & (~content_matched)
            
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason

    # 8. Limpieza final
    out["reasons"] = out["reasons"].str.strip(" |")

    # 9. Allowlist override (Máxima prioridad)
    if allow_mask.any():
        out.loc[allow_mask, "flag"] = Flag.OK.value
        out.loc[allow_mask, "reasons"] = "ALLOWLIST"

    return out