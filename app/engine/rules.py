from __future__ import annotations
import pandas as pd
import numpy as np
from app.core.constants import Flag, FLAG_PRIORITY
from app.core.models import Catalog

def _combine_flags(curr_flag: pd.Series, new_flag: Flag) -> pd.Series:
    # sube el flag si el nuevo es peor
    return np.where(
        curr_flag.map(lambda x: FLAG_PRIORITY[Flag(x)]) < FLAG_PRIORITY[new_flag],
        new_flag.value,
        curr_flag
    )

def apply_rules(df: pd.DataFrame, catalog: Catalog) -> pd.DataFrame:
    out = df.copy()

    out["flag"] = Flag.OK.value
    out["reasons"] = ""

    # allowlist: si match exacto (contains simple), fuerza OK al final.
    allowlist = [s.strip() for s in catalog.allowlist_merchants if s.strip()]
    allow_mask = pd.Series(False, index=out.index)
    if allowlist and "merchant" in out.columns:
        m = out["merchant"].astype(str)
        for a in allowlist:
            allow_mask |= m.str.contains(repr(a)[1:-1], case=False, na=False) if len(a) > 0 else False

    # MCC rules
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

    # Keyword rules (regex)
    if catalog.keyword_rules and "merchant" in out.columns:
        merch = out["merchant"].astype(str)
        for rule in catalog.keyword_rules:
            mask = merch.str.contains(rule.pattern, na=False, regex=True)
            if mask.any():
                out.loc[mask, "flag"] = _combine_flags(out.loc[mask, "flag"], Flag(rule.severity))
                out.loc[mask, "reasons"] = out.loc[mask, "reasons"].where(
                    out.loc[mask, "reasons"].eq(""),
                    out.loc[mask, "reasons"] + " | "
                ) + rule.reason

    # Amount rules
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

    # Aplicar allowlist al final: merchants permitidos se fuerzan OK
    if allow_mask.any():
        out.loc[allow_mask, "flag"] = Flag.OK.value
        out.loc[allow_mask, "reasons"] = "ALLOWLIST"

    return out
