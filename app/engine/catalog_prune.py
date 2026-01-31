from __future__ import annotations
import pandas as pd
from app.core.models import Catalog, MccRule, KeywordRule, AmountRule

def prune_catalog_for_dataset(catalog: Catalog, df: pd.DataFrame, min_keyword_matches: int = 0) -> tuple[Catalog, list[str]]:
    """
    MODO COMPLIANCE: Mantiene TODAS las reglas activas.
    No elimina reglas por falta de uso, asegurando que bloqueos (ej. Apuestas)
    permanezcan activos para futuras cargas.
    """
    changes: list[str] = []
    
    # Solo reporte informativo (para que sepas qué se usó), pero SIN BORRAR nada.
    if "mcc" in df.columns:
        dataset_mccs = set(df["mcc"].dropna().astype(str).unique())
        unused_mccs = [r.mcc for r in catalog.mcc_rules if str(r.mcc) not in dataset_mccs]
        if unused_mccs:
            changes.append(f"Info: {len(unused_mccs)} reglas MCC no se dispararon en este dataset (se mantienen activas).")

    if "merchant" in df.columns:
        merch = df["merchant"].astype(str)
        unused_kw = 0
        for r in catalog.keyword_rules:
            try:
                # Chequeo rápido solo para log, no afecta la regla
                if not merch.str.contains(r.pattern, na=False, regex=True).any():
                    unused_kw += 1
            except Exception:
                pass
        if unused_kw > 0:
            changes.append(f"Info: {unused_kw} reglas de Keyword no se dispararon (se mantienen activas).")

    changes.append("Catálogo intacto (Modo Auditoría).")

    # Retornamos el catálogo original EXACTO, preservando todas las reglas
    return catalog, changes