from __future__ import annotations
import json
import pandas as pd
from app.core.models import Catalog
from app.ai.azure_client import get_azure_client

SYSTEM = """Eres un asistente que genera reglas conservadoras para auditoría de gastos.
Devuelve SOLO JSON válido con schema:
{version, allowlist_merchants, mcc_rules[], keyword_rules[], amount_rules[]}.
No inventes MCCs: usa solo los MCCs presentes en el dataset.
Keywords deben ser conservadoras y útiles."""

def generate_catalog_from_data(df: pd.DataFrame, deployment: str) -> Catalog:
    # muestra MCCs y top merchants para limitar al modelo
    mccs = sorted(set(df["mcc"].astype(str).dropna().unique().tolist()))[:2000]
    top_merchants = df["merchant"].astype(str).value_counts().head(50).index.tolist()
    amounts = pd.to_numeric(df["amount"], errors="coerce").dropna()
    stats = {
        "rows": int(len(df)),
        "mccs_sample": mccs[:200],
        "top_merchants": top_merchants,
        "amount_p50": float(amounts.quantile(0.5)) if len(amounts) else 0,
        "amount_p90": float(amounts.quantile(0.9)) if len(amounts) else 0,
        "amount_p99": float(amounts.quantile(0.99)) if len(amounts) else 0,
    }

    client = get_azure_client()
    prompt = {
        "dataset_stats": stats,
        "instruction": "Genera reglas conservadoras: prioriza POSSIBLE_WARN. DIRECT_WARN solo si es muy obvio.",
    }

    resp = client.chat.completions.create(
        model=deployment,
        temperature=0.2,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )

    content = resp.choices[0].message.content
    data = json.loads(content)
    return Catalog.model_validate(data)
    