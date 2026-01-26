from __future__ import annotations
import pandas as pd

# SOLO lo mínimo para flaguear:
# employee y description son opcionales (employee se genera en cleaning.py)
REQUIRED_CANONICAL = ["date", "merchant", "amount", "mcc"]
OPTIONAL_CANONICAL = ["employee", "description"]

def apply_column_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """
    mapping: {canonical_name: source_column_name}
    Ej: {"date":"Transaction Date","merchant":"Clean Merchant Name",...}
    """
    rename_map = {mapping[k]: k for k in mapping if mapping[k] in df.columns}
    out = df.rename(columns=rename_map).copy()
    return out

def missing_required_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in REQUIRED_CANONICAL if c not in df.columns]
