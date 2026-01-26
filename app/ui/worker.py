from __future__ import annotations
from PySide6.QtCore import QObject, Signal, Slot
import pandas as pd
from app.engine.rules import apply_rules
from app.core.models import Catalog

class ProcessingWorker(QObject):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(pd.DataFrame)
    failed = Signal(str)

    def __init__(self, df: pd.DataFrame, catalog: Catalog, chunk_size: int = 5000):
        super().__init__()
        self.df = df
        self.catalog = catalog
        self.chunk_size = chunk_size
        self._cancel = False

    @Slot()
    def run(self) -> None:
        try:
            n = len(self.df)
            if n == 0:
                self.finished.emit(self.df.copy())
                return

            self.status.emit("Procesando reglas...")
            results = []
            for i in range(0, n, self.chunk_size):
                if self._cancel:
                    self.failed.emit("Proceso cancelado por el usuario.")
                    return
                chunk = self.df.iloc[i:i + self.chunk_size]
                results.append(apply_rules(chunk, self.catalog))

                pct = int(((i + len(chunk)) / n) * 100)
                self.progress.emit(min(pct, 100))

            result_df = pd.concat(results, ignore_index=True)
            self.status.emit("Listo.")
            self.finished.emit(result_df)

        except Exception as e:
            self.failed.emit(str(e))

    def cancel(self) -> None:
        self._cancel = True
