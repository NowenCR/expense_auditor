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
    Cliente real para evaluar merchants usando Azure (Foundry Models) vía OpenAI SDK estable.

    Env vars requeridas:
      - AZURE_FOUNDRY_ENDPOINT
      - AZURE_FOUNDRY_API_KEY
      - AZURE_FOUNDRY_MODEL      (Recomendado: gpt-5.2-preview o similar)
      - AZURE_FOUNDRY_API_VERSION
    """

    def __init__(self):
        self.endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").strip()
        self.api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "").strip()
        # Configura el modelo en tu .env con: AZURE_FOUNDRY_MODEL=gpt-5.2-preview
        self.model = os.getenv("AZURE_FOUNDRY_MODEL", "gpt-4.0").strip()
        self.api_version = os.getenv("AZURE_FOUNDRY_API_VERSION", "2024-10-21").strip()

        if not self.endpoint or not self.api_key:
            raise RuntimeError(
                "Faltan env vars: AZURE_FOUNDRY_ENDPOINT / AZURE_FOUNDRY_API_KEY. "
                "Crea el archivo .env en la raíz del proyecto."
            )

        # Cliente AzureOpenAI (OpenAI SDK estable)
        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            api_key=self.api_key,
            api_version=self.api_version,
        )

    # -----------------------------
    # Public API
    # -----------------------------
    def evaluate_transaction(self, row: dict[str, Any]) -> AIResult:
        """
        Versión optimizada para Modelos Avanzados (GPT-5.2+).
        Conocimiento Paramétrico Puro: No usa búsqueda web, confía en el entrenamiento del modelo.
        """
        # 1. Extracción de datos
        merchant = (row.get("merchant") or "").strip()
        mcc = str(row.get("mcc") or "").strip()
        description = (row.get("description") or "").strip()
        amount = row.get("amount")

        # 2. PROMPT OPTIMIZADO
        system = (
            f"Eres el Auditor Principal de Gastos ({self.model}). Tu conocimiento sobre marcas y comercios es vasto.\n"
            "Tus objetivos:\n"
            "1. IDENTIFICACIÓN PROFUNDA: Usa tu base de conocimiento para identificar si el comercio es un Casino, Club Nocturno, "
            "Spa, Joyería o un sitio de riesgo, incluso si el nombre es abreviado.\n"
            "2. LIMPIEZA DE INTERMEDIARIOS: Si ves 'SQ *', 'TST *', 'PAYPAL *', analiza el texto que sigue.\n"
            "3. JUICIO BASADO EN CONOCIMIENTO: Si no conoces el comercio, juzga basándote estrictamente en el MCC y la descripción.\n"
            "4. VALIDACIÓN DE REGLAS: Se te da un 'pre-flag' de reglas estáticas. Confírmalo o corrígelo con argumentos lógicos.\n"
            "\n"
            "Salida JSON estricta: { category, severity, reason }"
        )

        payload = {
            "merchant": merchant,
            "mcc": mcc,
            "description": description,
            "amount": amount,
            "pre_flag": row.get("flag", "OK"),
            "pre_reason": row.get("reasons", "")
        }

        user_msg = (
            f"Analiza: '{merchant}'.\n"
            f"Reglas previas indican: {row.get('flag')} ({row.get('reasons')}).\n"
            "¿Es correcto? Usa tu conocimiento interno para validar."
            f"\nDATA: {json.dumps(payload, ensure_ascii=False)}"
        )

        # 3. Llamada Directa usando self.model (controlado por .env)
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        )

        # 4. Procesamiento de la respuesta (Parsing)
        text = (resp.choices[0].message.content or "").strip()
        data = self._safe_parse_json(text)

        # Validación de seguridad de la respuesta
        severity = str(data.get("severity", "POSSIBLE_WARN")).strip()
        if severity not in ("OK", "POSSIBLE_WARN", "DIRECT_WARN"):
            severity = "POSSIBLE_WARN"

        # 5. Retorno
        return AIResult(
            category=str(data.get("category", "Uncategorized")).strip(),
            severity=severity,
            reason=str(data.get("reason", "Revisión manual requerida.")).strip()[:500],
            web_evidence=None
        )

    # -----------------------------
    # Helpers
    # -----------------------------
    def _safe_parse_json(self, text: str) -> dict[str, Any]:
        """
        Intenta parsear JSON.
        Si viene con basura alrededor, intenta extraer el primer bloque {...}.
        """
        if not text:
            return {}

        # Caso ideal: puro JSON
        try:
            return json.loads(text)
        except Exception:
            pass

        # Extraer bloque {...}
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}