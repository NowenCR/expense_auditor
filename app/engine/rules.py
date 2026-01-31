from __future__ import annotations
import pandas as pd
import numpy as np
from app.core.constants import Flag, FLAG_PRIORITY
from app.core.models import Catalog

def _combine_flags(curr_flag: pd.Series, new_flag: Flag) -> pd.Series:
    """
    Actualiza el flag solo si la nueva severidad es mayor que la actual.
    (DIRECT_WARN > POSSIBLE_WARN > OK)
    """
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
    
    # =========================================================================
    # PASO 1: CÁLCULO DE INMUNIDAD (ALLOWLIST)
    # =========================================================================
    allow_mask = pd.Series(False, index=out.index)
    
    col_merchant = out["merchant"].astype(str) if "merchant" in out.columns else pd.Series("", index=out.index)
    col_desc = out["description"].astype(str) if "description" in out.columns else pd.Series("", index=out.index)
    col_mcc_desc = out["mcc_description"].astype(str) if "mcc_description" in out.columns else pd.Series("", index=out.index)
    
    # 1.1 Allowlist Simple
    if catalog.allowlist_merchants:
        m = col_merchant.str.lower()
        for a in catalog.allowlist_merchants:
            if a.strip():
                allow_mask |= m.str.contains(a.lower(), regex=False)

    # 1.2 Allowlist Patterns
    if catalog.allowlist_patterns:
        combined_context = (col_merchant + " " + col_desc + " " + col_mcc_desc).str.lower()
        for rule in catalog.allowlist_patterns:
            try:
                mask = combined_context.str.contains(rule.pattern, case=False, na=False, regex=True)
                allow_mask |= mask
            except Exception:
                pass

    # =========================================================================
    # PASO 2: ESTADO INICIAL
    # =========================================================================
    out["flag"] = Flag.OK.value
    out["reasons"] = ""
    out.loc[allow_mask, "reasons"] = "ALLOWLIST"

    content_matched = pd.Series(False, index=out.index)

    # =========================================================================
    # PASO 3: APLICACIÓN DE REGLAS ESTÁNDAR
    # =========================================================================

    # --- 3.1 MCC DESCRIPTION RULES ---
    if catalog.mcc_description_rules:
        for rule in catalog.mcc_description_rules:
            mask_pat = col_mcc_desc.str.contains(rule.pattern, case=False, na=False, regex=True)
            mask_cond = _evaluate_condition(out, rule.condition)
            mask = mask_pat & mask_cond

            if mask.any():
                severity = Flag(rule.severity)
                if severity == Flag.DIRECT_WARN:
                    final_mask = mask
                else:
                    final_mask = mask & (~allow_mask)

                if final_mask.any():
                    out.loc[final_mask, "flag"] = _combine_flags(out.loc[final_mask, "flag"], severity)
                    out.loc[final_mask, "reasons"] = out.loc[final_mask, "reasons"] + " | " + rule.reason
                    content_matched |= final_mask

    # --- 3.2 DISALLOWED KEYWORDS ---
    if catalog.disallowed_keywords:
        for pat in catalog.disallowed_keywords:
            mask = (col_merchant.str.contains(pat, case=False, na=False, regex=True) |
                    col_desc.str.contains(pat, case=False, na=False, regex=True) |
                    col_mcc_desc.str.contains(pat, case=False, na=False, regex=True))
            
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag.DIRECT_WARN)
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"] + " | Prohibido: " + pat
                content_matched |= mask

    # --- 3.3 MCC RULES ---
    if catalog.mcc_rules and "mcc" in out.columns:
        mcc_s = out["mcc"].astype(str)
        for rule in catalog.mcc_rules:
            mask = (mcc_s == str(rule.mcc))
            
            if mask.any():
                severity = Flag(rule.severity)
                if severity == Flag.DIRECT_WARN:
                    final_mask = mask
                else:
                    final_mask = mask & (~allow_mask)

                if final_mask.any():
                    out.loc[final_mask, "flag"] = _combine_flags(out.loc[final_mask, "flag"], severity)
                    out.loc[final_mask, "reasons"] = out.loc[final_mask, "reasons"] + " | " + rule.reason
                    content_matched |= final_mask

    # --- 3.4 KEYWORD RULES ---
    if catalog.keyword_rules:
        for rule in catalog.keyword_rules:
            mask = (col_merchant.str.contains(rule.pattern, case=False, na=False, regex=True) |
                    col_desc.str.contains(rule.pattern, case=False, na=False, regex=True) |
                    col_mcc_desc.str.contains(rule.pattern, case=False, na=False, regex=True))
            
            if mask.any():
                severity = Flag(rule.severity)
                if severity == Flag.DIRECT_WARN:
                    final_mask = mask
                else:
                    final_mask = mask & (~allow_mask)

                if final_mask.any():
                    out.loc[final_mask, "flag"] = _combine_flags(out.loc[final_mask, "flag"], severity)
                    out.loc[final_mask, "reasons"] = out.loc[final_mask, "reasons"] + " | " + rule.reason
                    content_matched |= final_mask

    # --- 3.5 PURCHASE CATEGORY RULES ---
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
                severity = Flag(rule.severity)
                if severity == Flag.DIRECT_WARN:
                    final_mask = mask
                else:
                    final_mask = mask & (~allow_mask)

                if final_mask.any():
                    out.loc[final_mask, "flag"] = _combine_flags(out.loc[final_mask, "flag"], severity)
                    out.loc[final_mask, "reasons"] = out.loc[final_mask, "reasons"] + " | " + rule.reason
                    content_matched |= final_mask

    # --- 3.6 AMOUNT RULES ---
    if catalog.amount_rules and "amount" in out.columns:
        amt = pd.to_numeric(out["amount"], errors="coerce").fillna(0)
        pcat_series = out["purchase_category"].astype(str).str.lower().str.strip() if "purchase_category" in out.columns else pd.Series("", index=out.index)

        for rule in catalog.amount_rules:
            mask_amt = amt >= float(rule.min_amount)
            
            scope_mask = pd.Series(True, index=out.index)
            rule_scope = str(rule.scope).lower().strip()
            if rule_scope.startswith("category:"):
                target_cat = rule_scope.split(":", 1)[1].strip()
                scope_mask = (pcat_series == target_cat)
            
            mask = mask_amt & scope_mask
            
            if mask.any():
                severity = Flag(rule.severity)
                if severity == Flag.DIRECT_WARN:
                    final_mask = mask
                else:
                    final_mask = mask & (~allow_mask)

                if final_mask.any():
                    out.loc[final_mask, "flag"] = _combine_flags(out.loc[final_mask, "flag"], severity)
                    out.loc[final_mask, "reasons"] = out.loc[final_mask, "reasons"] + " | " + rule.reason

    # =========================================================================
    # PASO 4: OVERRIDE ABSOLUTO (MCC DESCRIPTION - FUERZA BRUTA)
    # Requerimiento: BAR, LOUNGE, DISCO, NIGHTCLUB, TAVERN, ALCOHOLIC DRINKS
    # Sea un warn directo, sin excepciones, ignorando allowlist y reglas previas.
    # =========================================================================
    if "mcc_description" in out.columns:
        # Convertimos a mayúsculas para coincidencia insensible a mayúsculas/minúsculas
        mcc_upper = out["mcc_description"].astype(str).str.upper()
        
        # Palabras clave forzadas
        forced_keywords = ["BAR", "LOUNGE", "DISCO", "NIGHTCLUB", "TAVERN", "ALCOHOLIC"]
        
        force_mask = pd.Series(False, index=out.index)
        for kw in forced_keywords:
            # Buscamos la subcadena exacta (literal)
            force_mask |= mcc_upper.str.contains(kw, regex=False, na=False)
            
        if force_mask.any():
            # FORZAMOS EL FLAG Y LA RAZÓN
            # Sobreescribe lo que haya puesto el Allowlist o cualquier regla anterior
            out.loc[force_mask, "flag"] = Flag.DIRECT_WARN.value
            out.loc[force_mask, "reasons"] = out.loc[force_mask, "reasons"].astype(str) + " | BLOQUEO FORZADO MCC"

    # Limpieza final de strings
    out["reasons"] = out["reasons"].str.strip(" |")
    
    return out