from __future__ import annotations
import pandas as pd

def read_excel(path: str, sheet_name: str | int | None = 0) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl")

def list_sheets(path: str) -> list[str]:
    xl = pd.ExcelFile(path, engine="openpyxl")
    return xl.sheet_names
