from __future__ import annotations
import json
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel
from app.engine.catalog import save_catalog
from app.core.models import Catalog


class CatalogDialog(QDialog):
    def __init__(self, parent, catalog: Catalog, catalog_path: str):
        super().__init__(parent)
        self.setWindowTitle("Catálogo de reglas (JSON)")
        self.resize(900, 650)

        self._catalog = catalog
        self._catalog_path = catalog_path

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Edita con cuidado. Cambios aquí afectan el comportamiento de los flags.\n"
            "Tip: Si algo falla, revisa el JSON (comas, llaves, strings)."
        ))

        self.editor = QTextEdit()
        self.editor.setPlainText(json.dumps(self._catalog.to_dict(), ensure_ascii=False, indent=2))
        layout.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Cerrar")
        self.btn_save = QPushButton("Guardar")
        self.btn_save.setDefault(True)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_save)
        layout.addLayout(btn_row)

        self.btn_cancel.clicked.connect(self.close)
        self.btn_save.clicked.connect(self.on_save)

        self.saved_ok = False
        self.error_msg = ""

    def on_save(self):
        try:
            data = json.loads(self.editor.toPlainText())
            cat = Catalog.model_validate(data)
            save_catalog(cat, self._catalog_path)
            self._catalog = cat
            self.saved_ok = True
            self.close()
        except Exception as e:
            self.saved_ok = False
            self.error_msg = str(e)

    def get_catalog(self) -> Catalog:
        return self._catalog
