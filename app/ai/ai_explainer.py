from __future__ import annotations

import pandas as pd
from typing import Any
from app.ai.azure_foundry_client import AzureFoundryClient, AIResult

DEFAULT_MAX_CALLS = 200  # para no gastar de más: solo IA sobre sospechosos

def should_send_to_ai(row: pd.Series) -> bool:
    # Solo enviar a IA si ya es warning o si merchant es “raro” (sin matches allowlist)
    flag = str(row.get("flag", ""))
    if flag in ("DIRECT_WARN", "POSSIBLE_WARN"):
        return True
    # Heurística simple: merchant muy corto o genérico
    m = str(row.get("merchant", "")).strip()
    if len(m) <= 4:
        return True
    if m.lower() in ("bar", "alcohol", "casino"):
        return True
    return False

def apply_ai_explanations(df: pd.DataFrame, max_calls: int = DEFAULT_MAX_CALLS) -> pd.DataFrame:
    """
    Agrega columnas:
      - ai_category
      - ai_reason
      - ai_severity (recomendación IA)
      - ai_web_evidence
    """
    client = AzureFoundryClient()

    out = df.copy()
    out["ai_category"] = ""
    out["ai_reason"] = ""
    out["ai_severity"] = ""
    out["ai_web_evidence"] = ""

    calls = 0
    for idx, row in out.iterrows():
        if calls >= max_calls:
            break
        if not should_send_to_ai(row):
            continue

        payload: dict[str, Any] = {
            "merchant": row.get("merchant"),
            "mcc": row.get("mcc"),
            "description": row.get("description"),
            "amount": row.get("amount"),
            "date": row.get("date"),
            "country": row.get("country") if "country" in out.columns else None,
        }

        res: AIResult = client.evaluate_transaction(payload)
        out.at[idx, "ai_category"] = res.category
        out.at[idx, "ai_reason"] = res.reason
        out.at[idx, "ai_severity"] = res.severity
        out.at[idx, "ai_web_evidence"] = res.web_evidence or ""
        calls += 1

    return out
