from __future__ import annotations

import traceback
from collections import defaultdict
from typing import Any

import pandas as pd
from PySide6.QtCore import QObject, Signal

from app.ai.azure_foundry_client import AzureFoundryClient, AIResult


class AIWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(pd.DataFrame)
    failed = Signal(str)

    def __init__(
        self,
        df_result: pd.DataFrame,
        max_calls: int = 200,
        analyze_only_warnings: bool = True,
    ):
        super().__init__()
        self.df_result = df_result
        self.max_calls = max_calls
        self.analyze_only_warnings = analyze_only_warnings
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.status.emit("IA: inicializando cliente…")
            client = AzureFoundryClient()  # usa .env

            df = self.df_result.copy()

            # Asegurar columnas destino
            for col in ["ai_severity", "ai_reason", "ai_category", "ai_confidence"]:
                if col not in df.columns:
                    df[col] = ""

            # Selección de filas a analizar
            if self.analyze_only_warnings and "flag" in df.columns:
                target_mask = df["flag"].isin(["DIRECT_WARN", "POSSIBLE_WARN"])
            else:
                target_mask = pd.Series([True] * len(df))

            target_idx = df.index[target_mask].tolist()
            if not target_idx:
                self.status.emit("IA: no hay filas para analizar")
                self.progress.emit(100)
                self.finished.emit(df)
                return

            # Cache por merchant (y opcionalmente por mcc)
            groups: dict[tuple[str, str], list[int]] = defaultdict(list)

            def norm(x: Any) -> str:
                if pd.isna(x) or x is None:
                    return ""
                return str(x).strip()

            for i in target_idx:
                merch = norm(df.at[i, "merchant"]) if "merchant" in df.columns else ""
                mcc = norm(df.at[i, "mcc"]) if "mcc" in df.columns else ""
                key = (merch.upper(), mcc)
                groups[key].append(i)

            keys = list(groups.keys())
            total_keys = min(len(keys), self.max_calls)

            self.status.emit(f"IA: analizando {total_keys} merchants únicos…")

            # Procesar merchants únicos (limitar costo)
            for n, key in enumerate(keys[: self.max_calls], start=1):
                if self._cancelled:
                    self.status.emit("IA: cancelado")
                    break

                merch_u, mcc = key
                any_row_idx = groups[key][0]

                row = {
                    "merchant": merch_u,
                    "mcc": mcc,
                    "description": norm(df.at[any_row_idx, "description"]) if "description" in df.columns else "",
                    "amount": norm(df.at[any_row_idx, "amount"]) if "amount" in df.columns else "",
                    "date": norm(df.at[any_row_idx, "date"]) if "date" in df.columns else "",
                    "country": norm(df.at[any_row_idx, "country"]) if "country" in df.columns else "",
                    "purchase_category": norm(df.at[any_row_idx, "purchase_category"]) if "purchase_category" in df.columns else "",
                    "flag": norm(df.at[any_row_idx, "flag"]) if "flag" in df.columns else "",
                    "reasons": norm(df.at[any_row_idx, "reasons"]) if "reasons" in df.columns else "",
                }

                result: AIResult = client.evaluate_transaction(row)

                # Aplicar resultado a todas las filas con ese merchant/mcc
                for ridx in groups[key]:
                    df.at[ridx, "ai_severity"] = result.severity
                    df.at[ridx, "ai_reason"] = result.reason
                    df.at[ridx, "ai_category"] = result.category
                    # “confidence” opcional: si no viene, dejamos vacío
                    df.at[ridx, "ai_confidence"] = getattr(result, "confidence", "")

                pct = int((n / total_keys) * 100)
                self.progress.emit(pct)
                self.status.emit(f"IA: {n}/{total_keys} merchants analizados")

            # Marcar si quedó truncado por max_calls
            if len(keys) > self.max_calls:
                self.status.emit(f"IA: límite alcanzado (max_calls={self.max_calls}). Analiza de nuevo o sube el límite.")
            else:
                self.status.emit("IA: listo")

            self.progress.emit(100)
            self.finished.emit(df)

        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{e}\n\n{tb}")
