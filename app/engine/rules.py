from __future__ import annotations
import pandas as pd
import numpy as np
from app.core.constants import Flag, FLAG_PRIORITY
from app.core.models import Catalog

def _combine_flags(curr_flag: pd.Series, new_flag: Flag) -> pd.Series:
    return np.where(
        curr_flag.map(lambda x: FLAG_PRIORITY[Flag(x)]) < FLAG_PRIORITY[new_flag],
        new_flag.value,
        curr_flag
    )

def _evaluate_condition(df: pd.DataFrame, condition: str) -> pd.Series:
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
    
    content_matched = pd.Series(False, index=out.index)
    allow_mask = pd.Series(False, index=out.index)

    # Preparar columnas de texto
    col_merchant = out["merchant"].astype(str) if "merchant" in out.columns else pd.Series("", index=out.index)
    col_desc = out["description"].astype(str) if "description" in out.columns else pd.Series("", index=out.index)
    col_mcc_desc = out["mcc_description"].astype(str) if "mcc_description" in out.columns else pd.Series("", index=out.index)

    # 1. ALLOWLIST SIMPLE (Strings) - Solo Merchant
    if catalog.allowlist_merchants:
        m = col_merchant.str.lower()
        for a in catalog.allowlist_merchants:
            if a.strip():
                allow_mask |= m.str.contains(a.lower(), regex=False)

    # 2. ALLOWLIST PATTERNS (Regex Contextual - MEJORADO)
    # Fusionamos todo el texto para que el Regex pueda validar el contexto completo
    # Esto permite detectar "Eating Places" PERO bloquear si dice "Topgolf" en el merchant
    if catalog.allowlist_patterns:
        combined_context = (col_merchant + " " + col_desc + " " + col_mcc_desc).str.lower()
        
        for rule in catalog.allowlist_patterns:
            try:
                # Aplicamos el patrón al contexto completo
                mask = combined_context.str.contains(rule.pattern, case=False, na=False, regex=True)
                allow_mask |= mask
            except Exception:
                pass

    # 3. DISALLOWED KEYWORDS (Multicolumna)
    if catalog.disallowed_keywords:
        for pat in catalog.disallowed_keywords:
            mask_merch = col_merchant.str.contains(pat, case=False, na=False, regex=True)
            mask_desc = col_desc.str.contains(pat, case=False, na=False, regex=True)
            mask_mcc = col_mcc_desc.str.contains(pat, case=False, na=False, regex=True)
            
            mask = mask_merch | mask_desc | mask_mcc
            
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag.DIRECT_WARN)
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | Prohibido: " + pat
                content_matched |= mask

    # 4. MCC RULES
    if catalog.mcc_rules and "mcc" in out.columns:
        mcc_s = out["mcc"].astype(str)
        for rule in catalog.mcc_rules:
            mask = (mcc_s == str(rule.mcc))
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 5. KEYWORD RULES (Multicolumna)
    if catalog.keyword_rules:
        for rule in catalog.keyword_rules:
            mask_merch = col_merchant.str.contains(rule.pattern, case=False, na=False, regex=True)
            mask_desc = col_desc.str.contains(rule.pattern, case=False, na=False, regex=True)
            mask_mcc = col_mcc_desc.str.contains(rule.pattern, case=False, na=False, regex=True)
            mask = mask_merch | mask_desc | mask_mcc

            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 6. MCC DESCRIPTION RULES
    if catalog.mcc_description_rules:
        for rule in catalog.mcc_description_rules:
            mask_pat = col_mcc_desc.str.contains(rule.pattern, case=False, na=False, regex=True)
            mask_cond = _evaluate_condition(out, rule.condition)
            mask = mask_pat & mask_cond
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 7. PURCHASE CATEGORY RULES
    if catalog.purchase_category_rules and "purchase_category" in out.columns:
        pcat = out["purchase_category"].astype(str)
        for rule in catalog.purchase_category_rules:
            mask_cat = pcat.str.lower() == rule.category.lower()
            mask_cond = _evaluate_condition(out, rule.condition)
            
            mask_excl = pd.Series(False, index=out.index)
            if rule.exclude_patterns:
                for pat in rule.exclude_patterns:
                    mask_excl |= col_merchant.str.contains(pat, case=False, na=False, regex=True)
            
            mask = (mask_cat & mask_cond) & (~mask_excl)
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason
                content_matched |= mask

    # 8. AMOUNT RULES
    if catalog.amount_rules and "amount" in out.columns:
        amt = pd.to_numeric(out["amount"], errors="coerce").fillna(0)
        for rule in catalog.amount_rules:
            mask_amt = amt >= float(rule.min_amount)
            mask = mask_amt & (~content_matched)
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | " + rule.reason

    # 9. Limpieza y Aplicación de Allowlist
    out["reasons"] = out["reasons"].str.strip(" |")
    
    if allow_mask.any():
        out.loc[allow_mask, "flag"] = Flag.OK.value
        out.loc[allow_mask, "reasons"] = "ALLOWLIST"

    return out