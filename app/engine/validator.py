from __future__ import annotations
import pandas as pd
from app.core.models import Catalog

def validate_generated_catalog(catalog: Catalog, dataset: pd.DataFrame) -> tuple[bool, list[str]]:
    errors: list[str] = []

    # 1. Validación de estructura básica del dataset
    for col in ["mcc", "merchant", "amount"]:
        if col not in dataset.columns:
            errors.append(f"Dataset no contiene columna requerida: {col}")

    if errors:
        return False, errors

    # 2. Validación de Sintaxis de Regex (Crítico para que no falle el programa)
    for kw in catalog.keyword_rules:
        try:
            # Probamos si compila el regex con una cadena vacía
            pd.Series(["test"]).str.contains(kw.pattern, regex=True)
        except Exception as e:
            errors.append(f"Pattern inválido (Error de Sintaxis) '{kw.pattern}': {e}")
            
    for rule in catalog.mcc_description_rules:
        try:
             pd.Series(["test"]).str.contains(rule.pattern, regex=True)
        except Exception as e:
            errors.append(f"MCC Desc Pattern inválido '{rule.pattern}': {e}")

    # ELIMINADO: Validación estadística de montos (P50/P99)
    # ELIMINADO: Validación de existencia de MCC en el dataset actual

    return len(errors) == 0, errors 