from __future__ import annotations
import pandas as pd
import numpy as np
from app.core.constants import Flag, FLAG_PRIORITY
from app.core.models import Catalog

def _combine_flags(curr_flag: pd.Series, new_flag: Flag) -> pd.Series:
    # sube el flag si el nuevo es peor (OK < POSSIBLE < DIRECT)
    return np.where(
        curr_flag.map(lambda x: FLAG_PRIORITY[Flag(x)]) < FLAG_PRIORITY[new_flag],
        new_flag.value,
        curr_flag
    )

def apply_rules(df: pd.DataFrame, catalog: Catalog) -> pd.DataFrame:
    out = df.copy()

    out["flag"] = Flag.OK.value
    out["reasons"] = ""

    # 1. ALLOWLIST (String exacto/parcial simple)
    # Se calcula al inicio pero se aplica al final para sobreescribir todo
    allow_mask = pd.Series(False, index=out.index)
    if catalog.allowlist_merchants and "merchant" in out.columns:
        m = out["merchant"].astype(str)
        for a in catalog.allowlist_merchants:
            if a.strip():
                allow_mask |= m.str.contains(repr(a)[1:-1], case=False, na=False, regex=False)

    # 2. ALLOWLIST PATTERNS (Nuevo: Regex)
    # Ej: "^american\\s+\\d{6,}"
    if catalog.allowlist_patterns and "merchant" in out.columns:
        m = out["merchant"].astype(str)
        for pat in catalog.allowlist_patterns:
            try:
                # regex=True por defecto en contains, pero lo explicitamos
                mask_pat = m.str.contains(pat.pattern, case=False, na=False, regex=True)
                allow_mask |= mask_pat
            except Exception:
                pass # ignorar regex malformado

    # 3. MCC RULES
    if catalog.mcc_rules and "mcc" in out.columns:
        mcc_series = out["mcc"].astype(str)
        for rule in catalog.mcc_rules:
            mask = (mcc_series == str(rule.mcc))
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"].where(
                    out.loc[mask, "reasons"].eq(""),
                    out.loc[mask, "reasons"] + " | "
                ) + rule.reason

    # 4. KEYWORD RULES (Regex)
    if catalog.keyword_rules and "merchant" in out.columns:
        merch = out["merchant"].astype(str)
        for rule in catalog.keyword_rules:
            mask = merch.str.contains(rule.pattern, na=False, regex=True)
            
            # 4.1 EXCEPCIONES A KEYWORDS (Nuevo)
            # Si hace match con regla (ej: "Casino"), verificamos si NO cae en excepcion (ej: "Casino Hotel")
            if catalog.keyword_exceptions and mask.any():
                for exc in catalog.keyword_exceptions:
                    # Si cumple la excepción, lo sacamos de la máscara de "culpables"
                    # o forzamos su severidad a OK (override)
                    exc_mask = merch.str.contains(exc.pattern, na=False, regex=True)
                    # A las filas que cumplen la Regla Y TAMBIÉN la Excepción
                    common = mask & exc_mask
                    if common.any():
                        # Opción A: Simplemente no aplicar la regla (mask = mask & ~exc_mask)
                        # Opción B: Aplicar override explícito. El usuario puso override_severity="OK"
                        # Vamos con Opción A simplificada: Si es excepción, la regla de keyword NO aplica.
                        mask = mask & (~exc_mask)
            
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"].where(
                    out.loc[mask, "reasons"].eq(""),
                    out.loc[mask, "reasons"] + " | "
                ) + rule.reason

    # 5. AMOUNT RULES
    if catalog.amount_rules and "amount" in out.columns:
        amount = pd.to_numeric(out["amount"], errors="coerce").fillna(0)
        for rule in catalog.amount_rules:
            mask = amount >= float(rule.min_amount)
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"].where(
                    out.loc[mask, "reasons"].eq(""),
                    out.loc[mask, "reasons"] + " | "
                ) + rule.reason

    # 6. APLICAR ALLOWLIST FINAL
    # Fuerza OK y borra razones anteriores si estaba en lista blanca
    if allow_mask.any():
        out.loc[allow_mask, "flag"] = Flag.OK.value
        out.loc[allow_mask, "reasons"] = "ALLOWLIST"

    return out