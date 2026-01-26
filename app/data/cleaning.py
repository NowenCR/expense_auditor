from __future__ import annotations
import pandas as pd
from dateutil import parser

UNKNOWN_MCC = "9999"

def validate_and_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    issues: list[str] = []
    out = df.copy()

    # merchant
    if "merchant" in out.columns:
        miss = out["merchant"].isna().sum()
        if miss:
            issues.append(f"{miss} filas sin merchant (rellenado como UNKNOWN MERCHANT)")
        out["merchant"] = out["merchant"].fillna("UNKNOWN MERCHANT").astype(str).str.strip()

    # mcc
    if "mcc" in out.columns:
        miss = out["mcc"].isna().sum()
        if miss:
            issues.append(f"{miss} filas sin MCC (rellenado como {UNKNOWN_MCC})")
        out["mcc"] = out["mcc"].fillna(UNKNOWN_MCC).astype(str).str.strip()

    # amount
    if "amount" in out.columns:
        # convierte a numérico y abs
        out["amount"] = pd.to_numeric(out["amount"], errors="coerce")
        miss = out["amount"].isna().sum()
        if miss:
            issues.append(f"{miss} filas con amount inválido (NaN)")
        out["amount"] = out["amount"].fillna(0).abs()

    # date (si viene sucia)
    if "date" in out.columns:
        if not pd.api.types.is_datetime64_any_dtype(out["date"]):
            def _parse(x):
                if pd.isna(x):
                    return pd.NaT
                try:
                    return parser.parse(str(x))
                except Exception:
                    return pd.NaT
            out["date"] = out["date"].apply(_parse)
        miss = out["date"].isna().sum()
        if miss:
            issues.append(f"{miss} filas con date inválida (NaT)")

    # description / employee opcionales
    for col, default in [("description", ""), ("employee", "")]:
        if col in out.columns:
            out[col] = out[col].fillna(default).astype(str)

    return out, issues
    