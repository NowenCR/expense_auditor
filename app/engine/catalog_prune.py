from __future__ import annotations
import pandas as pd
from app.core.models import Catalog, MccRule, KeywordRule, AmountRule

def prune_catalog_for_dataset(catalog: Catalog, df: pd.DataFrame, min_keyword_matches: int = 3) -> tuple[Catalog, list[str]]:
    """
    Quita reglas que no aplican a este dataset:
      - mcc_rules cuyo MCC no exista en df['mcc']
      - keyword_rules con menos de min_keyword_matches matches
    Retorna (nuevo_catalogo, cambios)
    """
    changes: list[str] = []

    # MCC existentes
    mccs = set(df["mcc"].dropna().astype(str).unique()) if "mcc" in df.columns else set()

    new_mcc_rules: list[MccRule] = []
    removed_mcc = 0
    for r in catalog.mcc_rules:
        if str(r.mcc) in mccs:
            new_mcc_rules.append(r)
        else:
            removed_mcc += 1
            changes.append(f"Removida regla MCC {r.mcc} (no existe en dataset)")

    # Keywords con matches
    new_kw_rules: list[KeywordRule] = []
    removed_kw = 0
    if "merchant" in df.columns:
        merch = df["merchant"].astype(str)
        for r in catalog.keyword_rules:
            try:
                matches = merch.str.contains(r.pattern, na=False, regex=True).sum()
            except Exception:
                matches = 0
            if matches >= min_keyword_matches:
                new_kw_rules.append(r)
            else:
                removed_kw += 1
                changes.append(f"Removida keyword '{r.pattern}' (matches={matches} < {min_keyword_matches})")
    else:
        # si no hay merchant, quitamos todas las keywords
        removed_kw = len(catalog.keyword_rules)
        if removed_kw:
            changes.append("Removidas keyword rules (no existe columna merchant)")

    # Amount rules se mantienen (no dependen de matches directos)
    new_catalog = Catalog(
        version=catalog.version,
        allowlist_merchants=catalog.allowlist_merchants,
        mcc_rules=new_mcc_rules,
        keyword_rules=new_kw_rules,
        amount_rules=catalog.amount_rules,
    )

    if removed_mcc == 0 and removed_kw == 0:
        changes.append("Catálogo OK: no hubo cambios.")

    return new_catalog, changes
