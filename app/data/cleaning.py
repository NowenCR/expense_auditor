from __future__ import annotations

import pandas as pd
from dateutil import parser

UNKNOWN_MCC = "9999"

def validate_and_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    issues: list[str] = []
    out = df.copy()

    # --- REQUIRED ---
    if "merchant" in out.columns:
        miss = out["merchant"].isna().sum()
        if miss:
            issues.append(f"{miss} filas sin merchant (rellenado)")
        out["merchant"] = out["merchant"].fillna("UNKNOWN MERCHANT").astype(str).str.strip()

    if "mcc" in out.columns:
        out["mcc"] = out["mcc"].fillna(UNKNOWN_MCC).astype(str).str.strip()

    if "amount" in out.columns:
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce").fillna(0).abs()

    if "date" in out.columns:
        if not pd.api.types.is_datetime64_any_dtype(out["date"]):
            def _parse(x):
                try: return parser.parse(str(x))
                except: return pd.NaT
            out["date"] = out["date"].apply(_parse)

    # --- OPTIONAL COLUMNS (v1.2.0) ---
    # Aseguramos que existan description, purchase_category, etc.
    optional_cols = ["description", "employee", "purchase_category", "mcc_description"]
    for col in optional_cols:
        if col not in out.columns:
            out[col] = ""
        else:
            out[col] = out[col].fillna("").astype(str).str.strip()

    # Fallback: Si purchase_category viene vacío, intentar usar description
    if "purchase_category" in out.columns and "description" in out.columns:
        mask_empty = out["purchase_category"] == ""
        # Solo copiamos si description tiene algo
        out.loc[mask_empty, "purchase_category"] = out.loc[mask_empty, "description"]

    return out, issues