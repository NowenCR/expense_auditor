from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

from openai import AzureOpenAI


@dataclass
class AIResult:
    category: str
    severity: str  # "OK" | "POSSIBLE_WARN" | "DIRECT_WARN"
    reason: str
    web_evidence: Optional[str] = None


class AzureFoundryClient:
    """
    Cliente optimizado para análisis profundo de texto (Merchant + Description + MCC Desc).
    Incluye lógica avanzada de desambiguación de entidades deportivas.
    """

    def __init__(self):
        self.endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").strip()
        self.api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "").strip()
        self.model = os.getenv("AZURE_FOUNDRY_MODEL", "gpt-4.0").strip()
        self.api_version = os.getenv("AZURE_FOUNDRY_API_VERSION", "2024-10-21").strip()

        if not self.endpoint or not self.api_key:
            raise RuntimeError(
                "Faltan env vars: AZURE_FOUNDRY_ENDPOINT / AZURE_FOUNDRY_API_KEY."
            )

        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

    def evaluate_transaction(self, row: dict[str, Any]) -> AIResult:
        """
        Analiza transacción cruzando datos de Merchant, Description y MCC Description.
        """
        # 1. Extracción de datos
        merchant = (row.get("merchant") or "").strip()
        mcc = str(row.get("mcc") or "").strip()
        description = (row.get("description") or "").strip()
        mcc_description = (row.get("mcc_description") or "").strip()
        amount = row.get("amount")

        # 2. PROMPT OPTIMIZADO PARA ANÁLISIS CRUZADO Y DESAMBIGUACIÓN DE DEPORTES
        system = (
            f"Eres el Auditor Principal de Gastos ({self.model}).\n"
            "Tus objetivos:\n"
            "1. ANÁLISIS CRUZADO: Compara el 'Merchant' con 'Description' y 'MCC Description'.\n"
            "2. DESAMBIGUACIÓN DE DEPORTES (CRÍTICO): Muchos restaurantes se llaman como equipos (ej. 'Real Madrid Cafe', 'Cowboys Saloon', 'Manchester Diner'). "
            "Usa tu conocimiento global para determinar si el merchant es realmente una entidad deportiva (Entradas, Merchandising, Estadio) "
            "o simplemente un bar/restaurante temático o ubicado en esa ciudad. "
            "Si es comida/restaurante -> OK (Categoría: Alimentación). Si son tickets/jerseys -> DIRECT_WARN (Categoría: Deportes).\n"
            "3. DETECCIÓN DE RIESGOS: Streaming, Apuestas, Bienes Digitales -> DIRECT_WARN.\n"
            "4. VALIDACIÓN DE REGLAS: Si el flag previo dice 'Deportes' pero tú ves que es un restaurante, CORRIGELO a 'OK'.\n"
            "\n"
            "Salida JSON estricta: { category, severity, reason }"
        )

        payload = {
            "merchant": merchant,
            "description": description,
            "mcc_description": mcc_description,
            "mcc": mcc,
            "amount": amount,
            "pre_flag": row.get("flag", "OK"),
            "pre_reason": row.get("reasons", "")
        }

        user_msg = (
            f"Analiza este gasto.\n"
            f"Merchant: '{merchant}'\n"
            f"Desc: '{description}'\n"
            f"MCC Desc: '{mcc_description}'\n"
            f"Reglas previas: {row.get('flag')} ({row.get('reasons')}).\n"
            "Verifica si es un falso positivo de deportes."
            f"\nDATA: {json.dumps(payload, ensure_ascii=False)}"
        )

        # 3. Llamada
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,  # Bajo para mayor determinismo
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        )

        # 4. Parsing
        text = (resp.choices[0].message.content or "").strip()
        data = self._safe_parse_json(text)

        # Validación de severidad segura
        severity = str(data.get("severity", "POSSIBLE_WARN")).strip().upper()
        if severity not in ("OK", "POSSIBLE_WARN", "DIRECT_WARN"):
            severity = "POSSIBLE_WARN"

        return AIResult(
            category=str(data.get("category", "Uncategorized")).strip(),
            severity=severity,
            reason=str(data.get("reason", "Revisión manual requerida.")).strip()[:500],
            web_evidence=None
        )

    def _safe_parse_json(self, text: str) -> dict[str, Any]:
        if not text: return {}
        try: return json.loads(text)
        except: pass
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m: return {}
        try: return json.loads(m.group(0))
        except: return {}