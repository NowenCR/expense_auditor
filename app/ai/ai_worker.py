from __future__ import annotations

import traceback
from typing import Any
import pandas as pd
from PySide6.QtCore import QObject, Signal

# Importamos la lógica necesaria desde ai_explainer
from app.ai.ai_explainer import should_send_to_ai
from app.ai.azure_foundry_client import AzureFoundryClient, AIResult

class AIWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(pd.DataFrame)
    failed = Signal(str)

    def __init__(self, df: pd.DataFrame, max_calls: int = 200):
        super().__init__()
        self.df = df
        self.max_calls = max_calls
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.status.emit("IA: inicializando cliente...")
            client = AzureFoundryClient()

            out = self.df.copy()
            # Asegurar columnas
            for col in ["ai_category", "ai_reason", "ai_severity", "ai_web_evidence"]:
                if col not in out.columns:
                    out[col] = ""

            total_rows = len(out)
            calls = 0
            
            # --- LOOP DENTRO DEL WORKER PARA PERMITIR CANCELACIÓN ---
            for idx, row in out.iterrows():
                # 1. Chequeo de cancelación en cada iteración
                if self._cancel:
                    self.status.emit("IA: operación cancelada por el usuario.")
                    break

                if calls >= self.max_calls:
                    self.status.emit(f"IA: límite de llamadas alcanzado ({self.max_calls})")
                    break

                # 2. Filtrado (solo analizar lo necesario)
                if not should_send_to_ai(row):
                    continue

                # 3. Preparar payload (pasando el contexto de reglas previas)
                payload: dict[str, Any] = {
                    "merchant": row.get("merchant"),
                    "mcc": row.get("mcc"),
                    "description": row.get("description"),
                    "amount": row.get("amount"),
                    "date": row.get("date"),
                    "country": row.get("country") if "country" in out.columns else None,
                    "flag": row.get("flag"),
                    "mcc_description": row.get("mcc_description"), # <--- AGREGAR ESTA LÍNEA     
                    "reasons": row.get("reasons") 
                }

                # 4. Llamada a la IA
                res: AIResult = client.evaluate_transaction(payload)
                
                out.at[idx, "ai_category"] = res.category
                out.at[idx, "ai_reason"] = res.reason
                out.at[idx, "ai_severity"] = res.severity
                out.at[idx, "ai_web_evidence"] = res.web_evidence or ""
                
                calls += 1
                
                # 5. Emitir progreso real
                # (idx + 1) para que llegue a 100% al final
                pct = int(((idx + 1) / total_rows) * 100)
                self.progress.emit(pct)

            self.progress.emit(100)
            self.finished.emit(out)

        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{str(e)}\n\n{tb}")from __future__ import annotations

import traceback
from typing import Any
import pandas as pd
from PySide6.QtCore import QObject, Signal

# Importamos la lógica necesaria
from app.ai.ai_explainer import should_send_to_ai
from app.ai.azure_foundry_client import AzureFoundryClient, AIResult

class AIWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(pd.DataFrame)
    failed = Signal(str)

    def __init__(self, df: pd.DataFrame, max_calls: int = 200):
        super().__init__()
        self.df = df
        self.max_calls = max_calls
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            self.status.emit("IA: inicializando cliente...")
            client = AzureFoundryClient()

            out = self.df.copy()
            # Asegurar columnas de salida
            for col in ["ai_category", "ai_reason", "ai_severity", "ai_web_evidence"]:
                if col not in out.columns:
                    out[col] = ""

            total_rows = len(out)
            calls = 0
            
            # PROCESAMIENTO FILA POR FILA
            for idx, row in out.iterrows():
                if self._cancel:
                    self.status.emit("IA: operación cancelada.")
                    break

                if calls >= self.max_calls:
                    self.status.emit(f"IA: límite de llamadas alcanzado ({self.max_calls})")
                    break

                # Filtro: solo enviamos lo sospechoso
                if not should_send_to_ai(row):
                    continue

                # PAYLOAD COMPLETO (Incluyendo mcc_description)
                payload: dict[str, Any] = {
                    "merchant": row.get("merchant"),
                    "mcc": row.get("mcc"),
                    "description": row.get("description"),
                    "mcc_description": row.get("mcc_description"), # <--- CLAVE
                    "amount": row.get("amount"),
                    "date": row.get("date"),
                    "flag": row.get("flag"),     
                    "reasons": row.get("reasons") 
                }

                # Llamada a IA
                res: AIResult = client.evaluate_transaction(payload)
                
                out.at[idx, "ai_category"] = res.category
                out.at[idx, "ai_reason"] = res.reason
                out.at[idx, "ai_severity"] = res.severity
                out.at[idx, "ai_web_evidence"] = res.web_evidence or ""
                
                calls += 1
                
                # Progreso
                pct = int(((idx + 1) / total_rows) * 100)
                self.progress.emit(pct)

            self.progress.emit(100)
            self.finished.emit(out)

        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{str(e)}\n\n{tb}")