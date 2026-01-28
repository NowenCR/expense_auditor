from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()
from app.ui.ai_worker import AIWorker

import sys
from PySide6.QtWidgets import QApplication
from app.core.logging_config import setup_logging
from app.ui.main_window import MainWindow

def main():
    setup_logging()
    app = QApplication(sys.argv)
    win = MainWindow(catalog_path="catalog/catalog.json")
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
