from __future__ import annotations

import pandas as pd
import re

HEADER_HINTS = [
    "country", "cardholder", "transaction date", "transaction post date",
    "clean merchant name", "merchant", "purchase category",
    "mcc", "mcc description", "transaction currency", "total transaction amount"
]

def read_excel_noheader(path: str, sheet_name: str | int | None = 0) -> pd.DataFrame:
    """
    Lee Excel SIN asumir que hay headers.
    El resultado tendrá columnas numeradas 0..N-1 y filas tal cual vienen en el archivo.
    """
    return pd.read_excel(path, sheet_name=sheet_name, engine="openpyxl", header=None)

def _norm(x) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s

def detect_header_row(df: pd.DataFrame, max_scan_rows: int = 30) -> int | None:
    """
    Busca en las primeras N filas una fila que 'parezca' header.
    Retorna el índice (0-based) o None si no encuentra algo convincente.
    """
    scan_rows = min(max_scan_rows, len(df))
    best_score = -1.0
    best_idx: int | None = None

    for i in range(scan_rows):
        row = df.iloc[i].tolist()
        texts = [_norm(x) for x in row]

        # si la fila está vacía, skip
        if all(t == "" for t in texts):
            continue

        non_empty = [t for t in texts if t]
        if not non_empty:
            continue

        # hits por hints (keywords típicas de headers del banco)
        hint_hits = 0
        for h in HEADER_HINTS:
            if any(h in t for t in non_empty):
                hint_hits += 1

        # proporción de celdas "textuales" (no puro número)
        texty = sum(not t.replace(".", "", 1).isdigit() for t in non_empty)
        text_ratio = texty / len(non_empty)

        # penalizar si hay demasiado vacío
        empty_ratio = 1 - (len(non_empty) / len(texts))

        # score
        score = (hint_hits * 5) + (text_ratio * 3) - (empty_ratio * 2)

        if score > best_score:
            best_score = score
            best_idx = i

    # umbral mínimo (ajustable)
    if best_score < 6:
        return None

    return best_idx

def apply_detected_header(df_noheader: pd.DataFrame, header_row: int) -> pd.DataFrame:
    """
    Usa la fila detectada como headers reales y retorna df desde header_row+1.
    """
    headers = df_noheader.iloc[header_row].astype(str).tolist()
    out = df_noheader.iloc[header_row + 1:].copy()
    out.columns = headers
    return out.reset_index(drop=True)
