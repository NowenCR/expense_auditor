from __future__ import annotations
import pandas as pd

def export_to_excel(df: pd.DataFrame, path: str) -> None:
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="results")

def export_to_csv(df: pd.DataFrame, path: str) -> None:
    df.to_csv(path, index=False, encoding="utf-8")
