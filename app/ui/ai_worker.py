from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QObject, Signal

from app.ai.ai_explainer import apply_ai_explanations

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
            self.status.emit("IA: generando explicaciones...")
            # (Para progreso real, habría que instrumentar loop; aquí simple)
            out = apply_ai_explanations(self.df, max_calls=self.max_calls)
            self.progress.emit(100)
            self.finished.emit(out)
        except Exception as e:
            self.failed.emit(str(e))
