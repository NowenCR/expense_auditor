from __future__ import annotations
from PySide6.QtWidgets import QMessageBox, QWidget

def info(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.information(parent, title, text)

def warn(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.warning(parent, title, text)

def error(parent: QWidget, title: str, text: str) -> None:
    QMessageBox.critical(parent, title, text)
