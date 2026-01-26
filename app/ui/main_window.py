from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QLineEdit, QTextEdit
)
from PySide6.QtCore import QThread
import pandas as pd

from app.data.io_excel import read_excel, list_sheets
from app.data.mapping import apply_column_mapping, missing_required_columns, REQUIRED_CANONICAL
from app.data.cleaning import validate_and_clean
from app.data.export import export_to_excel, export_to_csv
from app.engine.catalog import load_catalog, save_catalog
from app.engine.validator import validate_generated_catalog
from app.ui.worker import ProcessingWorker
from app.ui.dialogs import info, warn, error

class MainWindow(QMainWindow):
    def __init__(self, catalog_path: str):
        super().__init__()
        self.setWindowTitle("Corporate Expense Auditor (Flags)")
        self.resize(1100, 700)

        self.catalog_path = catalog_path
        self.catalog = load_catalog(catalog_path)

        self.df_raw: pd.DataFrame | None = None
        self.df_ready: pd.DataFrame | None = None
        self.df_result: pd.DataFrame | None = None
        self.excel_path: str | None = None

        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # Top actions
        row1 = QHBoxLayout()
        self.btn_load = QPushButton("Cargar Excel")
        self.sheet_combo = QComboBox()
        self.sheet_combo.setEnabled(False)
        self.btn_apply_sheet = QPushButton("Cargar hoja")
        self.btn_apply_sheet.setEnabled(False)

        row1.addWidget(self.btn_load)
        row1.addWidget(QLabel("Hoja:"))
        row1.addWidget(self.sheet_combo, 1)
        row1.addWidget(self.btn_apply_sheet)
        layout.addLayout(row1)

        # Mapping quick inputs
        layout.addWidget(QLabel("Mapeo de columnas (elige columnas del Excel para cada campo requerido):"))
        self.mapping_boxes: dict[str, QComboBox] = {}
        map_row = QHBoxLayout()
        self.columns_combo_source = QComboBox()
        self.columns_combo_source.setEnabled(False)
        map_row.addWidget(QLabel("Columnas disponibles:"))
        map_row.addWidget(self.columns_combo_source, 1)
        layout.addLayout(map_row)

        grid = QHBoxLayout()
        for canonical in REQUIRED_CANONICAL:
            col = QVBoxLayout()
            col.addWidget(QLabel(canonical))
            cb = QComboBox()
            cb.setEnabled(False)
            self.mapping_boxes[canonical] = cb
            col.addWidget(cb)
            grid.addLayout(col)
        layout.addLayout(grid)

        row_map_btn = QHBoxLayout()
        self.btn_prepare = QPushButton("Validar + Preparar datos")
        self.btn_prepare.setEnabled(False)
        self.btn_run = QPushButton("Correr flags")
        self.btn_run.setEnabled(False)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        row_map_btn.addWidget(self.btn_prepare)
        row_map_btn.addWidget(self.btn_run)
        row_map_btn.addWidget(self.btn_cancel)
        layout.addLayout(row_map_btn)

        # Progress
        rowp = QHBoxLayout()
        self.status_lbl = QLabel("Estado: esperando")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        rowp.addWidget(self.status_lbl, 1)
        rowp.addWidget(self.progress, 2)
        layout.addLayout(rowp)

        # Preview table
        self.table = QTableWidget(0, 0)
        layout.addWidget(QLabel("Preview (primeras 50 filas):"))
        layout.addWidget(self.table, 1)

        # Export
        row2 = QHBoxLayout()
        self.btn_export_excel = QPushButton("Exportar Excel")
        self.btn_export_csv = QPushButton("Exportar CSV")
        self.btn_export_excel.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        row2.addWidget(self.btn_export_excel)
        row2.addWidget(self.btn_export_csv)
        layout.addLayout(row2)

        # Catalog quick edit (simple)
        layout.addWidget(QLabel("Catálogo JSON (editable):"))
        self.catalog_editor = QTextEdit()
        self.catalog_editor.setPlainText(self._catalog_text())
        self.btn_save_catalog = QPushButton("Guardar catálogo")
        layout.addWidget(self.catalog_editor, 1)
        layout.addWidget(self.btn_save_catalog)

        # Events
        self.btn_load.clicked.connect(self.on_load_excel)
        self.btn_apply_sheet.clicked.connect(self.on_load_sheet)
        self.btn_prepare.clicked.connect(self.on_prepare)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_export_excel.clicked.connect(self.on_export_excel)
        self.btn_export_csv.clicked.connect(self.on_export_csv)
        self.btn_save_catalog.clicked.connect(self.on_save_catalog)

    def _catalog_text(self) -> str:
        import json
        return json.dumps(self.catalog.to_dict(), ensure_ascii=False, indent=2)

    def on_load_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Selecciona Excel", "", "Excel (*.xlsx *.xls)")
        if not path:
            return
        self.excel_path = path
        sheets = list_sheets(path)
        self.sheet_combo.clear()
        self.sheet_combo.addItems(sheets)
        self.sheet_combo.setEnabled(True)
        self.btn_apply_sheet.setEnabled(True)
        self.status_lbl.setText(f"Estado: Excel cargado ({path})")

    def on_load_sheet(self):
        if not self.excel_path:
            return
        sheet = self.sheet_combo.currentText()
        df = read_excel(self.excel_path, sheet_name=sheet)
        self.df_raw = df

        cols = list(df.columns)
        self.columns_combo_source.clear()
        self.columns_combo_source.addItems(cols)
        self.columns_combo_source.setEnabled(True)

        for cb in self.mapping_boxes.values():
            cb.clear()
            cb.addItem("")  # allow empty
            cb.addItems(cols)
            cb.setEnabled(True)

        self.btn_prepare.setEnabled(True)
        self.status_lbl.setText(f"Estado: hoja cargada ({sheet}) - filas: {len(df)}")
        self._preview(df)

    def on_prepare(self):
        if self.df_raw is None:
            return

        # build mapping canonical->selected column
        mapping = {}
        for canonical, cb in self.mapping_boxes.items():
            src = cb.currentText().strip()
            if src:
                mapping[canonical] = src

        df = apply_column_mapping(self.df_raw, mapping)

        missing = missing_required_columns(df)
        if missing:
            warn(self, "Faltan columnas", "Te faltan por mapear: " + ", ".join(missing))
            return

        cleaned, issues = validate_and_clean(df)
        self.df_ready = cleaned
        if issues:
            warn(self, "Datos limpiados", "\n".join(issues))

        ok, errs = validate_generated_catalog(self.catalog, self.df_ready)
        if not ok:
            warn(self, "Catálogo con problemas", "Tu catálogo tiene issues:\n" + "\n".join(errs))

        self.btn_run.setEnabled(True)
        self.status_lbl.setText("Estado: datos listos para correr reglas")
        self._preview(self.df_ready)

    def on_run(self):
        if self.df_ready is None:
            return

        self.progress.setValue(0)
        self.btn_run.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        self._thread = QThread()
        self._worker = ProcessingWorker(self.df_ready, self.catalog, chunk_size=5000)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.setValue)
        self._worker.status.connect(lambda s: self.status_lbl.setText(f"Estado: {s}"))
        self._worker.finished.connect(self.on_finished)
        self._worker.failed.connect(self.on_failed)

        # cleanup
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
        self.btn_run.setEnabled(True)
        self.status_lbl.setText("Estado: terminado")
        self._preview(result)

    def on_failed(self, msg: str):
        self.btn_cancel.setEnabled(False)
        self.btn_run.setEnabled(True)
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

    def on_save_catalog(self):
        import json
        try:
            data = json.loads(self.catalog_editor.toPlainText())
            from app.core.models import Catalog
            cat = Catalog.model_validate(data)
            self.catalog = cat
            save_catalog(cat, self.catalog_path)
            info(self, "Catálogo", "Catálogo guardado correctamente.")
        except Exception as e:
            error(self, "Catálogo inválido", str(e))

    def _preview(self, df: pd.DataFrame):
        head = df.head(50).copy()
        self.table.setRowCount(len(head))
        self.table.setColumnCount(len(head.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in head.columns])

        for r in range(len(head)):
            for c, col in enumerate(head.columns):
                val = head.iloc[r, c]
                self.table.setItem(r, c, QTableWidgetItem("" if pd.isna(val) else str(val)))

        self.table.resizeColumnsToContents()
