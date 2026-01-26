from __future__ import annotations

import pandas as pd
from PySide6.QtCore import QThread
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QFrame
)

from app.data.io_excel import list_sheets
from app.data.header_detection import read_excel_noheader, detect_header_row, apply_detected_header
from app.data.positional_mapping import build_mapping_from_positions
from app.data.fixed_mapping import fixed_mapping_for_your_headers
from app.data.mapping import apply_column_mapping, missing_required_columns
from app.data.cleaning import validate_and_clean
from app.data.export import export_to_excel, export_to_csv

from app.engine.catalog import load_catalog
from app.engine.validator import validate_generated_catalog
from app.ui.worker import ProcessingWorker
from app.ui.dialogs import info, warn, error
from app.ui.catalog_dialog import CatalogDialog


STYLE = """
QMainWindow { background: #0b1220; }
QLabel { color: #e7eefc; font-size: 12px; }
QPushButton {
    background: #1e3a8a; color: white; border: 1px solid #2b4aa8;
    padding: 10px 14px; border-radius: 10px; font-weight: 600;
}
QPushButton:hover { background: #2547a9; }
QPushButton:disabled { background: #22304a; color: #9fb2d6; border: 1px solid #2a3a5a; }

QComboBox {
    background: #0f1b33; color: #e7eefc; border: 1px solid #223b6a;
    padding: 8px 10px; border-radius: 10px;
}

QProgressBar {
    border: 1px solid #223b6a; border-radius: 10px; background: #0f1b33;
    text-align: center; color: #e7eefc; height: 18px;
}
QProgressBar::chunk { background: #2563eb; border-radius: 10px; }

QTableWidget {
    background: #0f1b33; color: #e7eefc; gridline-color: #1c2e55;
    border: 1px solid #223b6a; border-radius: 10px;
}
QHeaderView::section {
    background: #0b1730; color: #e7eefc; border: 1px solid #1c2e55;
    padding: 6px;
}
"""

def _badge(text: str, bg: str, fg: str = "white") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        QLabel {{
            background: {bg};
            color: {fg};
            padding: 6px 10px;
            border-radius: 999px;
            font-weight: 700;
        }}
    """)
    return lbl


class MainWindow(QMainWindow):
    def __init__(self, catalog_path: str):
        super().__init__()
        self.setWindowTitle("Corporate Expense Auditor (Flags)")
        self.resize(1150, 750)
        self.setStyleSheet(STYLE)

        self.catalog_path = catalog_path
        self.catalog = load_catalog(catalog_path)

        self.df_raw: pd.DataFrame | None = None
        self.df_ready: pd.DataFrame | None = None
        self.df_result: pd.DataFrame | None = None
        self.excel_path: str | None = None

        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

        self._build_menu()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(12)

        # Top row: load + sheet + analyze
        row1 = QHBoxLayout()
        self.btn_load = QPushButton("Cargar Excel")
        self.sheet_combo = QComboBox()
        self.sheet_combo.setEnabled(False)
        self.btn_load_sheet = QPushButton("Cargar hoja")
        self.btn_load_sheet.setEnabled(False)

        self.btn_analyze = QPushButton("Analizar documento")
        self.btn_analyze.setEnabled(False)

        row1.addWidget(self.btn_load)
        row1.addWidget(QLabel("Hoja:"))
        row1.addWidget(self.sheet_combo, 1)
        row1.addWidget(self.btn_load_sheet)
        row1.addStretch(1)
        row1.addWidget(self.btn_analyze)
        layout.addLayout(row1)

        # Status + progress
        rowp = QHBoxLayout()
        self.status_lbl = QLabel("Estado: esperando archivo")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        rowp.addWidget(self.status_lbl, 2)
        rowp.addWidget(self.progress, 3)
        layout.addLayout(rowp)

        # Summary badges
        sum_row = QHBoxLayout()
        self.badge_ok = _badge("OK: 0", "#14532d")
        self.badge_possible = _badge("POSSIBLE_WARN: 0", "#7c2d12")
        self.badge_direct = _badge("DIRECT_WARN: 0", "#7f1d1d")
        sum_row.addWidget(self.badge_ok)
        sum_row.addWidget(self.badge_possible)
        sum_row.addWidget(self.badge_direct)
        sum_row.addStretch(1)

        # Export + cancel
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_export_excel = QPushButton("Exportar Excel")
        self.btn_export_csv = QPushButton("Exportar CSV")
        self.btn_export_excel.setEnabled(False)
        self.btn_export_csv.setEnabled(False)

        sum_row.addWidget(self.btn_cancel)
        sum_row.addWidget(self.btn_export_excel)
        sum_row.addWidget(self.btn_export_csv)
        layout.addLayout(sum_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #223b6a;")
        layout.addWidget(div)

        # Table preview
        layout.addWidget(QLabel("Resultados (primeras 60 filas):"))
        self.table = QTableWidget(0, 0)
        layout.addWidget(self.table, 1)

        # Events
        self.btn_load.clicked.connect(self.on_load_excel)
        self.btn_load_sheet.clicked.connect(self.on_load_sheet)
        self.btn_analyze.clicked.connect(self.on_analyze)

        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_export_excel.clicked.connect(self.on_export_excel)
        self.btn_export_csv.clicked.connect(self.on_export_csv)

    def _build_menu(self):
        menubar = self.menuBar()
        tools = menubar.addMenu("Herramientas")

        act_catalog = QAction("Catálogo de reglas…", self)
        act_catalog.triggered.connect(self.open_catalog_dialog)
        tools.addAction(act_catalog)

    def open_catalog_dialog(self):
        dlg = CatalogDialog(self, self.catalog, self.catalog_path)
        dlg.exec()

        if dlg.saved_ok:
            self.catalog = dlg.get_catalog()
            info(self, "Catálogo", "Catálogo guardado y recargado.")
        elif dlg.error_msg:
            error(self, "Catálogo inválido", dlg.error_msg)

    def on_load_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona Excel", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        self.excel_path = path
        sheets = list_sheets(path)
        self.sheet_combo.clear()
        self.sheet_combo.addItems(sheets)
        self.sheet_combo.setEnabled(True)
        self.btn_load_sheet.setEnabled(True)
        self.status_lbl.setText("Estado: Excel cargado. Selecciona hoja.")
        self.progress.setValue(0)

    def on_load_sheet(self):
        if not self.excel_path:
            return

        sheet = self.sheet_combo.currentText()

        # ✅ A) Leer sin headers
        df0 = read_excel_noheader(self.excel_path, sheet_name=sheet)

        # ✅ A) Detectar fila header escondida
        hdr = detect_header_row(df0, max_scan_rows=30)

        if hdr is not None:
            df_raw = apply_detected_header(df0, hdr)
            self.status_lbl.setText(f"Estado: headers detectados en fila {hdr + 1} | filas: {len(df_raw)}")
        else:
            # ✅ B) No hay headers: crear columnas genéricas
            df_raw = df0.copy()
            df_raw.columns = [f"COL_{i}" for i in range(df_raw.shape[1])]
            self.status_lbl.setText(f"Estado: sin headers (posicional) | filas: {len(df_raw)}")

        self.df_raw = df_raw
        self.df_ready = None
        self.df_result = None

        self._reset_counts()
        self._preview(df_raw.head(60))

        self.btn_analyze.setEnabled(True)
        self.btn_export_excel.setEnabled(False)
        self.btn_export_csv.setEnabled(False)

    def on_analyze(self):
        if self.df_raw is None:
            return

        df_raw = self.df_raw

        # ✅ C) Decide mapping: por nombres (ideal) o por posiciones (fallback)
        expected = {"Transaction Date", "Clean Merchant Name", "Total Transaction Amount", "MCC", "Purchase Category"}

        if expected.issubset(set(df_raw.columns)):
            # Caso ideal: headers reales
            mapping = fixed_mapping_for_your_headers()
            df = apply_column_mapping(df_raw, mapping)
        else:
            # Fallback posicional
            pos_map = build_mapping_from_positions(list(df_raw.columns))

            mapping = {
                "date": pos_map["date"],
                "merchant": pos_map["merchant"],
                "amount": pos_map["amount"],
                "mcc": pos_map["mcc"],
                "description": pos_map["description"],
            }

            # Renombrar first/last para que cleaning arme employee
            df = df_raw.rename(columns={
                pos_map.get("first_name", ""): "first_name",
                pos_map.get("last_name", ""): "last_name",
            }).copy()

            df = apply_column_mapping(df, mapping)

        # Validar columnas canónicas
        miss = missing_required_columns(df)
        if miss:
            warn(self, "Archivo no compatible", "No pude mapear columnas necesarias:\n" + ", ".join(miss))
            return

        # Limpiar datos
        cleaned, issues = validate_and_clean(df)
        self.df_ready = cleaned

        if issues:
            warn(self, "Datos limpiados", "\n".join(issues))

        # Validar catálogo (avisar pero permitir)
        ok, errs = validate_generated_catalog(self.catalog, self.df_ready)
        if not ok:
            warn(self, "Catálogo con problemas", "Se detectaron issues:\n" + "\n".join(errs))

        # Ejecutar worker
        self.progress.setValue(0)
        self.btn_analyze.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.status_lbl.setText("Estado: procesando...")

        self._thread = QThread()
        self._worker = ProcessingWorker(self.df_ready, self.catalog, chunk_size=5000)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.status.connect(lambda s: self.status_lbl.setText(f"Estado: {s}"))
        self._worker.finished.connect(self.on_finished)
        self._worker.failed.connect(self.on_failed)

        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self.status_lbl.setText("Estado: cancelando...")

    def on_finished(self, result: pd.DataFrame):
        self.df_result = result
        self.btn_export_excel.setEnabled(True)
        self.btn_export_csv.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_analyze.setEnabled(True)

        self.status_lbl.setText("Estado: terminado")
        self._update_counts(result)
        self._preview(result.head(60))

    def on_failed(self, msg: str):
        self.btn_cancel.setEnabled(False)
        self.btn_analyze.setEnabled(True)
        error(self, "Error", msg)
        self.status_lbl.setText("Estado: error")

    def on_export_excel(self):
        if self.df_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Excel", "results.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        export_to_excel(self.df_result, path)
        info(self, "Exportado", f"Archivo generado:\n{path}")

    def on_export_csv(self):
        if self.df_result is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar CSV", "results.csv", "CSV (*.csv)")
        if not path:
            return
        export_to_csv(self.df_result, path)
        info(self, "Exportado", f"Archivo generado:\n{path}")

    def _reset_counts(self):
        self.badge_ok.setText("OK: 0")
        self.badge_possible.setText("POSSIBLE_WARN: 0")
        self.badge_direct.setText("DIRECT_WARN: 0")

    def _update_counts(self, df: pd.DataFrame):
        counts = df["flag"].value_counts(dropna=False).to_dict()
        ok = int(counts.get("OK", 0))
        poss = int(counts.get("POSSIBLE_WARN", 0))
        direct = int(counts.get("DIRECT_WARN", 0))

        self.badge_ok.setText(f"OK: {ok}")
        self.badge_possible.setText(f"POSSIBLE_WARN: {poss}")
        self.badge_direct.setText(f"DIRECT_WARN: {direct}")

    def _preview(self, df: pd.DataFrame):
        self.table.setRowCount(len(df))
        self.table.setColumnCount(len(df.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in df.columns])

        for r in range(len(df)):
            for c, col in enumerate(df.columns):
                val = df.iloc[r, c]
                item = QTableWidgetItem("" if pd.isna(val) else str(val))

                # Colorear columna flag si existe
                if str(col).lower() == "flag":
                    v = str(val)
                    if v == "DIRECT_WARN":
                        item.setBackground("#7f1d1d")
                    elif v == "POSSIBLE_WARN":
                        item.setBackground("#7c2d12")
                    elif v == "OK":
                        item.setBackground("#14532d")

                self.table.setItem(r, c, item)

        self.table.resizeColumnsToContents()
