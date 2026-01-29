from __future__ import annotations
import pandas as pd

# Definimos las columnas canónicas que el sistema espera
REQUIRED_CANONICAL = ["date", "merchant", "amount", "mcc"]
# Agregamos description, purchase_category y mcc_description como opcionales
OPTIONAL_CANONICAL = ["employee", "description", "purchase_category", "mcc_description"]

def apply_column_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    # Invierte el mapping para renombrar: {nombre_original: nombre_canonico}
    rename_map = {mapping[k]: k for k in mapping if mapping[k] in df.columns}
    out = df.rename(columns=rename_map).copy()
    return out

def missing_required_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in REQUIRED_CANONICAL if c not in df.columns]