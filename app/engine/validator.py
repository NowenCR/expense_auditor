from __future__ import annotations
import pandas as pd
from app.core.models import Catalog

def validate_generated_catalog(catalog: Catalog, dataset: pd.DataFrame) -> tuple[bool, list[str]]:
    errors: list[str] = []

    # columnas mínimas
    for col in ["mcc", "merchant", "amount"]:
        if col not in dataset.columns:
            errors.append(f"Dataset no contiene columna requerida: {col}")

    if errors:
        return False, errors

    dataset_mccs = set(dataset["mcc"].dropna().astype(str).unique())

    # MCCs existen
    for r in catalog.mcc_rules:
        if str(r.mcc) not in dataset_mccs:
            errors.append(f"MCC {r.mcc} no existe en dataset")

    # Keywords con matches >= 3
    for kw in catalog.keyword_rules:
        try:
            matches = dataset["merchant"].astype(str).str.contains(kw.pattern, na=False, regex=True).sum()
        except Exception as e:
            errors.append(f"Pattern inválido '{kw.pattern}': {e}")
            continue
        if matches < 3:
            errors.append(f"Pattern '{kw.pattern}' tiene solo {matches} matches (<3)")

    # Umbrales razonables: P50-P99
    if len(dataset) > 0:
        amounts = pd.to_numeric(dataset["amount"], errors="coerce").dropna()
        if len(amounts) > 10:
            p50 = float(amounts.quantile(0.50))
            p99 = float(amounts.quantile(0.99))
            for ar in catalog.amount_rules:
                if not (p50 <= ar.min_amount <= p99):
                    errors.append(
                        f"Umbral {ar.min_amount} fuera de rango razonable [P50={p50:.2f}, P99={p99:.2f}]"
                    )

    return len(errors) == 0, errors
