from __future__ import annotations

import pandas as pd
from app.ui.ai_worker import AIWorker

from PySide6.QtCore import QThread, Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QComboBox, QProgressBar,
    QTableWidget, QTableWidgetItem, QFrame, QLineEdit
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
from app.engine.catalog_prune import prune_catalog_for_dataset

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

QLineEdit {
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

def _pill_button(text: str, bg: str, fg: str = "white") -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {bg};
            color: {fg};
            padding: 7px 12px;
            border-radius: 999px;
            font-weight: 800;
            border: 1px solid rgba(255,255,255,0.10);
        }}
        QPushButton:hover {{
            border: 1px solid rgba(255,255,255,0.28);
        }}
    """)
    return btn

def _small_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet("""
        QPushButton {
            background: #0f1b33; color: #e7eefc;
            border: 1px solid #223b6a;
            padding: 8px 10px; border-radius: 10px; font-weight: 700;
        }
        QPushButton:hover { background: #13264a; }
        QPushButton:disabled { background: #22304a; color: #9fb2d6; }
    """)
    return btn


class MainWindow(QMainWindow):
    def __init__(self, catalog_path: str):
        super().__init__()
        self.setWindowTitle("Corporate Expense Auditor (Flags)")
        self.resize(1200, 800)
        self.setStyleSheet(STYLE)

        self.catalog_path = catalog_path
        self.catalog = load_catalog(catalog_path)

        self.df_raw: pd.DataFrame | None = None
        self.df_ready: pd.DataFrame | None = None
        self.df_result: pd.DataFrame | None = None

        # dataset actualmente mostrado (resultado + filtros)
        self._view_df: pd.DataFrame | None = None

        # filtros
        self._active_flag_filter: str | None = None  # "OK" | "POSSIBLE_WARN" | "DIRECT_WARN" | "WARNINGS" | "ALL"
        self._search_text: str = ""

        # paginación
        self.page_size = 60
        self.page_index = 0  # 0-based

        # IA
        self._ai_thread: QThread | None = None
        self._ai_worker: AIWorker | None = None

        self.excel_path: str | None = None
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

        self._build_menu()

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setSpacing(12)

        # --- Row 1: load + sheet + analyze
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

        # --- Row 2: status + progress
        row2 = QHBoxLayout()
        self.status_lbl = QLabel("Estado: esperando archivo")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        row2.addWidget(self.status_lbl, 2)
        row2.addWidget(self.progress, 3)
        layout.addLayout(row2)

        # --- Row 3: filter buttons + export/cancel + IA
        row3 = QHBoxLayout()
        self.btn_ok = _pill_button("OK: 0", "#14532d")
        self.btn_possible = _pill_button("POSSIBLE_WARN: 0", "#7c2d12")
        self.btn_direct = _pill_button("DIRECT_WARN: 0", "#7f1d1d")
        self.btn_warnings = _pill_button("SOLO WARNINGS", "#b45309")   # amber
        self.btn_all = _pill_button("VER TODO", "#1e3a8a")             # blue

        row3.addWidget(self.btn_ok)
        row3.addWidget(self.btn_possible)
        row3.addWidget(self.btn_direct)
        row3.addWidget(self.btn_warnings)
        row3.addWidget(self.btn_all)
        row3.addStretch(1)

        self.btn_ai = QPushButton("IA: Explicar y reducir ruido")
        self.btn_ai.setEnabled(False)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_export_excel = QPushButton("Exportar Excel")
        self.btn_export_csv = QPushButton("Exportar CSV")
        self.btn_export_excel.setEnabled(False)
        self.btn_export_csv.setEnabled(False)

        row3.addWidget(self.btn_ai)
        row3.addWidget(self.btn_cancel)
        row3.addWidget(self.btn_export_excel)
        row3.addWidget(self.btn_export_csv)
        layout.addLayout(row3)

        # --- Row 4: search + pagination controls
        row4 = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Buscar… (merchant, employee, mcc, amount, date, description)")
        self.btn_clear_search = _small_button("Limpiar")

        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["60", "200", "500", "1000"])
        self.page_size_combo.setCurrentText("60")

        self.btn_prev = _small_button("◀ Anterior")
        self.btn_next = _small_button("Siguiente ▶")
        self.page_lbl = QLabel("Página: -")

        row4.addWidget(QLabel("Buscar:"))
        row4.addWidget(self.search_box, 2)
        row4.addWidget(self.btn_clear_search)
        row4.addStretch(1)
        row4.addWidget(QLabel("Page size:"))
        row4.addWidget(self.page_size_combo)
        row4.addWidget(self.btn_prev)
        row4.addWidget(self.btn_next)
        row4.addWidget(self.page_lbl)
        layout.addLayout(row4)

        # filter label
        self.filter_lbl = QLabel("Filtro: (ninguno) — mostrando preview")
        layout.addWidget(self.filter_lbl)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("color: #223b6a;")
        layout.addWidget(div)

        layout.addWidget(QLabel("Tabla: usa filtros + búsqueda + paginación para navegar el dataset."))
        self.table = QTableWidget(0, 0)
        layout.addWidget(self.table, 1)

        # --- events
        self.btn_load.clicked.connect(self.on_load_excel)
        self.btn_load_sheet.clicked.connect(self.on_load_sheet)
        self.btn_analyze.clicked.connect(self.on_analyze)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_export_excel.clicked.connect(self.on_export_excel)
        self.btn_export_csv.clicked.connect(self.on_export_csv)
        self.btn_ai.clicked.connect(self.on_ai_explain)

        # filtros
        self.btn_ok.clicked.connect(lambda: self.on_flag_filter("OK"))
        self.btn_possible.clicked.connect(lambda: self.on_flag_filter("POSSIBLE_WARN"))
        self.btn_direct.clicked.connect(lambda: self.on_flag_filter("DIRECT_WARN"))
        self.btn_warnings.clicked.connect(lambda: self.on_flag_filter("WARNINGS"))
        self.btn_all.clicked.connect(lambda: self.on_flag_filter("ALL"))

        # search + pagination
        self.search_box.textChanged.connect(self.on_search_changed)
        self.btn_clear_search.clicked.connect(self.on_clear_search)
        self.page_size_combo.currentTextChanged.connect(self.on_page_size_changed)
        self.btn_prev.clicked.connect(self.on_prev_page)
        self.btn_next.clicked.connect(self.on_next_page)

        self._enable_table_controls(False)

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

    # ---------------------------
    # Load / Analyze
    # ---------------------------

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

        df0 = read_excel_noheader(self.excel_path, sheet_name=sheet)
        hdr = detect_header_row(df0, max_scan_rows=30)

        if hdr is not None:
            df_raw = apply_detected_header(df0, hdr)
            self.status_lbl.setText(f"Estado: headers detectados en fila {hdr + 1} | filas: {len(df_raw)}")
        else:
            df_raw = df0.copy()
            df_raw.columns = [f"COL_{i}" for i in range(df_raw.shape[1])]
            self.status_lbl.setText(f"Estado: sin headers (posicional) | filas: {len(df_raw)}")

        self.df_raw = df_raw
        self.df_ready = None
        self.df_result = None
        self._view_df = None

        self.btn_ai.setEnabled(False)

        self._reset_counts()
        self._reset_filters_and_paging()

        # preview antes de analizar
        self.filter_lbl.setText("Filtro: (ninguno) — preview del archivo (sin flags)")
        self._render_table(df_raw, show_flag_colors=False)

        self.btn_analyze.setEnabled(True)
        self.btn_export_excel.setEnabled(False)
        self.btn_export_csv.setEnabled(False)
        self._enable_table_controls(False)

    def on_analyze(self):
        if self.df_raw is None:
            return

        df_raw = self.df_raw

        expected = {"Transaction Date", "Clean Merchant Name", "Total Transaction Amount", "MCC", "Purchase Category"}

        if expected.issubset(set(df_raw.columns)):
            mapping = fixed_mapping_for_your_headers()
            df = apply_column_mapping(df_raw, mapping)
        else:
            pos_map = build_mapping_from_positions(list(df_raw.columns))
            mapping = {
                "date": pos_map["date"],
                "merchant": pos_map["merchant"],
                "amount": pos_map["amount"],
                "mcc": pos_map["mcc"],
                "description": pos_map["description"],
            }
            df = df_raw.rename(columns={
                pos_map.get("first_name", ""): "first_name",
                pos_map.get("last_name", ""): "last_name",
            }).copy()
            df = apply_column_mapping(df, mapping)

        miss = missing_required_columns(df)
        if miss:
            warn(self, "Archivo no compatible", "No pude mapear columnas necesarias:\n" + ", ".join(miss))
            return

        cleaned, issues = validate_and_clean(df)
        self.df_ready = cleaned

        # Podar catálogo (evita MCC inexistentes / keywords sin matches)
        pruned, changes = prune_catalog_for_dataset(self.catalog, self.df_ready, min_keyword_matches=3)
        catalog_to_use = pruned

        # Puedes silenciar esto luego si lo prefieres
        if changes and not (len(changes) == 1 and "no hubo cambios" in changes[0].lower()):
            warn(
                self,
                "Catálogo ajustado para este archivo",
                "\n".join(changes[:20]) + ("\n..." if len(changes) > 20 else "")
            )

        if issues:
            warn(self, "Datos limpiados", "\n".join(issues))

        ok, errs = validate_generated_catalog(catalog_to_use, self.df_ready)
        if not ok and errs:
            warn(self, "Catálogo con warnings", "Se detectaron issues:\n" + "\n".join(errs))

        # Worker
        self.progress.setValue(0)
        self.btn_analyze.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_ai.setEnabled(False)
        self.status_lbl.setText("Estado: procesando...")

        self._thread = QThread()
        self._worker = ProcessingWorker(self.df_ready, catalog_to_use, chunk_size=5000)
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
        self.btn_ai.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_analyze.setEnabled(True)
        self.status_lbl.setText("Estado: terminado")

        self._update_counts(result)
        self._reset_filters_and_paging()
        self._enable_table_controls(True)

        # Por defecto: SOLO WARNINGS (mejor UX)
        self._active_flag_filter = "WARNINGS"
        self.filter_lbl.setText("Filtro: SOLO WARNINGS — usa búsqueda/paginación")
        self._recompute_view_and_render()

    def on_failed(self, msg: str):
        self.btn_cancel.setEnabled(False)
        self.btn_analyze.setEnabled(True)
        self.btn_ai.setEnabled(True)
        error(self, "Error", msg)
        self.status_lbl.setText("Estado: error")

    # ---------------------------
    # IA
    # ---------------------------

    def on_ai_explain(self):
        if self.df_result is None:
            warn(self, "IA", "Primero analiza el documento.")
            return

        self.progress.setValue(0)
        self.btn_ai.setEnabled(False)
        self.status_lbl.setText("Estado: IA procesando...")

        self._ai_thread = QThread()
        self._ai_worker = AIWorker(self.df_result, max_calls=200)
        self._ai_worker.moveToThread(self._ai_thread)

        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.progress.connect(self.progress.setValue)
        self._ai_worker.status.connect(lambda s: self.status_lbl.setText(f"Estado: {s}"))
        self._ai_worker.finished.connect(self.on_ai_finished)
        self._ai_worker.failed.connect(self.on_ai_failed)

        self._ai_worker.finished.connect(self._ai_thread.quit)
        self._ai_worker.failed.connect(self._ai_thread.quit)
        self._ai_thread.finished.connect(self._ai_thread.deleteLater)

        self._ai_thread.start()

    def on_ai_finished(self, df_with_ai: pd.DataFrame):
        self.df_result = df_with_ai
        self.status_lbl.setText("Estado: IA listo (explicaciones añadidas)")
        self.btn_ai.setEnabled(True)

        # Re-render con tu vista actual (filtro/paginación)
        self._recompute_view_and_render()

    def on_ai_failed(self, msg: str):
        self.btn_ai.setEnabled(True)
        error(self, "IA error", msg)
        self.status_lbl.setText("Estado: IA error")

    # ---------------------------
    # Filters + Search + Paging
    # ---------------------------

    def _enable_table_controls(self, enabled: bool):
        self.search_box.setEnabled(enabled)
        self.btn_clear_search.setEnabled(enabled)
        self.page_size_combo.setEnabled(enabled)
        self.btn_prev.setEnabled(enabled)
        self.btn_next.setEnabled(enabled)
        self.btn_ok.setEnabled(enabled)
        self.btn_possible.setEnabled(enabled)
        self.btn_direct.setEnabled(enabled)
        self.btn_warnings.setEnabled(enabled)
        self.btn_all.setEnabled(enabled)

    def _reset_filters_and_paging(self):
        self._active_flag_filter = None
        self._search_text = ""
        self.search_box.blockSignals(True)
        self.search_box.setText("")
        self.search_box.blockSignals(False)
        self.page_size = int(self.page_size_combo.currentText())
        self.page_index = 0

    def on_flag_filter(self, flag: str):
        if self.df_result is None:
            warn(self, "Aún no hay resultados", "Primero analiza el documento.")
            return

        # toggle: si clickeas el mismo, lo quita
        if self._active_flag_filter == flag:
            self._active_flag_filter = None
            self.filter_lbl.setText("Filtro: (ninguno) — mostrando TODO (sin filtro de flag)")
        else:
            self._active_flag_filter = flag
            if flag == "ALL":
                self.filter_lbl.setText("Filtro: VER TODO (sin filtro de flag)")
            elif flag == "WARNINGS":
                self.filter_lbl.setText("Filtro: SOLO WARNINGS (DIRECT+POSSIBLE)")
            else:
                self.filter_lbl.setText(f"Filtro: {flag}")

        self.page_index = 0
        self._recompute_view_and_render()

    def on_search_changed(self, text: str):
        self._search_text = (text or "").strip()
        self.page_index = 0
        self._recompute_view_and_render()

    def on_clear_search(self):
        self.search_box.setText("")
        # on_search_changed se dispara

    def on_page_size_changed(self, text: str):
        try:
            self.page_size = int(text)
        except Exception:
            self.page_size = 60
        self.page_index = 0
        self._recompute_view_and_render()

    def on_prev_page(self):
        if self.page_index > 0:
            self.page_index -= 1
            self._render_current_page()

    def on_next_page(self):
        total_pages = self._total_pages()
        if self.page_index + 1 < total_pages:
            self.page_index += 1
            self._render_current_page()

    def _total_pages(self) -> int:
        if self._view_df is None:
            return 1
        n = len(self._view_df)
        if n == 0:
            return 1
        return (n + self.page_size - 1) // self.page_size

    def _recompute_view_and_render(self):
        """
        Aplica:
        1) filtro por flag
        2) búsqueda por texto
        y luego renderiza página 0.
        """
        if self.df_result is None:
            return

        base = self.df_result

        # 1) filtro flag
        f = self._active_flag_filter
        if f == "OK":
            base = base[base["flag"] == "OK"]
        elif f == "POSSIBLE_WARN":
            base = base[base["flag"] == "POSSIBLE_WARN"]
        elif f == "DIRECT_WARN":
            base = base[base["flag"] == "DIRECT_WARN"]
        elif f == "WARNINGS":
            base = base[base["flag"].isin(["DIRECT_WARN", "POSSIBLE_WARN"])]
        elif f == "ALL" or f is None:
            base = base

        # 2) búsqueda
        q = self._search_text.lower().strip()
        if q:
            cols_to_search = []
            # si IA añadió columnas, también las buscamos
            for c in ["merchant", "employee", "description", "mcc", "amount", "date", "ai_category", "ai_reason", "ai_web_evidence"]:
                if c in base.columns:
                    cols_to_search.append(c)

            if cols_to_search:
                hay = base[cols_to_search].astype(str).agg(" | ".join, axis=1).str.lower()
                base = base[hay.str.contains(q, na=False)]

        self._view_df = base.reset_index(drop=True)
        self.page_index = min(self.page_index, max(0, self._total_pages() - 1))
        self._render_current_page()

    def _render_current_page(self):
        if self._view_df is None:
            return

        total = len(self._view_df)
        total_pages = self._total_pages()

        if total == 0:
            self.page_lbl.setText("Página: 0/0 (0 filas)")
            self._render_table(self._view_df, show_flag_colors=True, page_slice=(0, 0))
            return

        start = self.page_index * self.page_size
        end = min(start + self.page_size, total)

        self.page_lbl.setText(f"Página: {self.page_index + 1}/{total_pages}  (filas {start+1}-{end} de {total})")
        self._render_table(self._view_df, show_flag_colors=True, page_slice=(start, end))

        # habilitar/deshabilitar botones prev/next
        self.btn_prev.setEnabled(self.page_index > 0)
        self.btn_next.setEnabled(self.page_index + 1 < total_pages)

    # ---------------------------
    # Export
    # ---------------------------

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

    # ---------------------------
    # Counters + Rendering
    # ---------------------------

    def _reset_counts(self):
        self.btn_ok.setText("OK: 0")
        self.btn_possible.setText("POSSIBLE_WARN: 0")
        self.btn_direct.setText("DIRECT_WARN: 0")

    def _update_counts(self, df: pd.DataFrame):
        counts = df["flag"].value_counts(dropna=False).to_dict()
        ok = int(counts.get("OK", 0))
        poss = int(counts.get("POSSIBLE_WARN", 0))
        direct = int(counts.get("DIRECT_WARN", 0))

        self.btn_ok.setText(f"OK: {ok}")
        self.btn_possible.setText(f"POSSIBLE_WARN: {poss}")
        self.btn_direct.setText(f"DIRECT_WARN: {direct}")

    def _render_table(self, df: pd.DataFrame, show_flag_colors: bool, page_slice: tuple[int, int] | None = None):
        """
        Renderiza:
        - si page_slice = (start,end) => muestra esa página
        - si no => muestra df completo (usar con df pequeño)
        """
        if page_slice is not None:
            start, end = page_slice
            view = df.iloc[start:end].copy()
        else:
            view = df.copy()

        self.table.setSortingEnabled(False)
        self.table.setUpdatesEnabled(False)
        self.table.clear()

        self.table.setRowCount(len(view))
        self.table.setColumnCount(len(view.columns))
        self.table.setHorizontalHeaderLabels([str(c) for c in view.columns])

        flag_col_idx = None
        if show_flag_colors:
            for idx, col in enumerate(view.columns):
                if str(col).lower() == "flag":
                    flag_col_idx = idx
                    break

        def row_color(flag: str | None) -> QColor | None:
            if flag == "DIRECT_WARN":
                return QColor("#7f1d1d")
            if flag == "POSSIBLE_WARN":
                return QColor("#7c2d12")
            if flag == "OK":
                return QColor("#14532d")
            return None

        for r in range(len(view)):
            flag_val = None
            if show_flag_colors and flag_col_idx is not None:
                flag_val = str(view.iloc[r, flag_col_idx])
            bg = row_color(flag_val)

            for c in range(len(view.columns)):
                val = view.iat[r, c]
                item = QTableWidgetItem("" if pd.isna(val) else str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if bg is not None:
                    item.setBackground(bg)
                self.table.setItem(r, c, item)

        self.table.resizeColumnsToContents()
        self.table.setUpdatesEnabled(True)
