from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Optional

import requests
from openai import AzureOpenAI


@dataclass
class AIResult:
    category: str
    severity: str  # "OK" | "POSSIBLE_WARN" | "DIRECT_WARN"
    reason: str
    web_evidence: Optional[str] = None  # snippet corto (si hubo web search)


class AzureFoundryClient:
    """
    Cliente real para evaluar merchants usando Azure (Foundry Models) vía OpenAI SDK estable.

    Env vars requeridas:
      - AZURE_FOUNDRY_ENDPOINT   (ej: https://<resource>.services.ai.azure.com)
      - AZURE_FOUNDRY_API_KEY
      - AZURE_FOUNDRY_MODEL      (deployment name)
      - AZURE_FOUNDRY_API_VERSION (ej: 2024-10-21)

    Opcional (para web search):
      - BING_SEARCH_KEY
      - BING_SEARCH_ENDPOINT (default: https://api.bing.microsoft.com/v7.0/search)
    """

    def __init__(self):
        self.endpoint = os.getenv("AZURE_FOUNDRY_ENDPOINT", "").strip()
        self.api_key = os.getenv("AZURE_FOUNDRY_API_KEY", "").strip()
        self.model = os.getenv("AZURE_FOUNDRY_MODEL", "gpt-4.1").strip()
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

        # Web Search opcional (Bing)
        self.bing_key = os.getenv("BING_SEARCH_KEY", "").strip()
        self.bing_endpoint = os.getenv("BING_SEARCH_ENDPOINT", "https://api.bing.microsoft.com/v7.0/search").strip()

    # -----------------------------
    # Public API
    # -----------------------------
    def evaluate_transaction(self, row: dict[str, Any]) -> AIResult:
        """
        Devuelve AIResult con:
          - severity: OK/POSSIBLE_WARN/DIRECT_WARN
          - reason: explicación corta y clara para usuario
          - web_evidence: 1-2 snippets si se usó búsqueda web
        """

        merchant = (row.get("merchant") or "").strip()
        mcc = str(row.get("mcc") or "").strip()
        description = (row.get("description") or "").strip()
        amount = row.get("amount")
        date = str(row.get("date") or "")
        country = (row.get("country") or "").strip()

        # Heurística: ¿vale la pena buscar web?
        # Solo si merchant es raro / poco informativo
        needs_web = self._should_use_web_search(merchant)

        evidence_text = None
        if needs_web and self.bing_key:
            evidence_text = self._bing_search_snippets(merchant, max_results=3)

        system = (
            "Eres un analista de gastos corporativos. Tu meta es REDUCIR falsos positivos y explicar decisiones.\n"
            "Reglas:\n"
            "- Hoteles/hospedaje, comida rápida, transporte (Uber/taxi/limousine), restaurantes y bares pueden ser válidos.\n"
            "- Solo marca DIRECT_WARN si la evidencia es fuerte (gaming/apuestas reales, gift cards, contenido adulto, fraude, etc.).\n"
            "- Si el merchant contiene palabra sensible (casino/bar/alcohol) pero el contexto indica hotel/restaurante legítimo, "
            "baja a POSSIBLE_WARN y pide documentación.\n"
            "- Si no estás seguro: usa POSSIBLE_WARN.\n"
            "Salida OBLIGATORIA en JSON estricto con claves: category, severity, reason, web_evidence (opcional).\n"
            "severity solo puede ser: OK, POSSIBLE_WARN, DIRECT_WARN."
        )

        payload = {
            "merchant": merchant,
            "mcc": mcc,
            "description": description,
            "amount": amount,
            "date": date,
            "country": country,
            "web_evidence": evidence_text,
        }

        user_msg = (
            "Clasifica esta transacción y explica por qué.\n"
            "Devuelve JSON.\n\n"
            f"DATA:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        # Llamada al modelo (chat completions)
        # Nota: usamos temperatura baja para consistencia
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
        )

        text = (resp.choices[0].message.content or "").strip()

        # Parse robusto: intenta extraer JSON aunque venga con texto extra
        data = self._safe_parse_json(text)

        severity = str(data.get("severity", "POSSIBLE_WARN")).strip()
        if severity not in ("OK", "POSSIBLE_WARN", "DIRECT_WARN"):
            severity = "POSSIBLE_WARN"

        return AIResult(
            category=str(data.get("category", "unknown")).strip(),
            severity=severity,
            reason=str(data.get("reason", "Sin razón provista.")).strip()[:500],
            web_evidence=(data.get("web_evidence") or evidence_text),
        )

    # -----------------------------
    # Helpers
    # -----------------------------
    def _should_use_web_search(self, merchant: str) -> bool:
        m = (merchant or "").strip().lower()
        if not m:
            return False

        # Si es muy corto o parece "procesador" raro => ayuda buscar
        if len(m) <= 5:
            return True

        # Palabras que suelen ser "ruido" / nombres crípticos
        suspicious_tokens = ["*","-","/","xsolla","payu","adyen","stripe","dlocal","ebanx","paddle","cleverbridge"]
        if any(t in m for t in suspicious_tokens):
            return True

        # Si parece un nombre normal, no gastar búsqueda
        return False

    def _bing_search_snippets(self, query: str, max_results: int = 3) -> str:
        """
        Busca en Bing y devuelve texto corto con 2-3 snippets.
        Si falla, retorna "".
        """
        try:
            headers = {"Ocp-Apim-Subscription-Key": self.bing_key}
            params = {"q": query, "mkt": "en-US", "count": max_results}
            r = requests.get(self.bing_endpoint, headers=headers, params=params, timeout=10)
            r.raise_for_status()
            j = r.json()

            web_pages = (j.get("webPages") or {}).get("value") or []
            chunks = []
            for it in web_pages[:max_results]:
                name = (it.get("name") or "").strip()
                snippet = (it.get("snippet") or "").strip()
                url = (it.get("url") or "").strip()
                if snippet:
                    chunks.append(f"- {name}: {snippet} ({url})")

            return "\n".join(chunks)[:1200]
        except Exception:
            return ""

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