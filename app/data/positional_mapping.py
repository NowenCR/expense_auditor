from __future__ import annotations

# Orden basado en tu lista de columnas:
# 0  Country
# 1  Cardholder First Name
# 2  Cardholder Last Name
# 5  Transaction Date
# 7  Clean Merchant Name
# 12 Purchase Category
# 13 MCC
# 25 Total Transaction Amount

POSITIONAL = {
    "date": 5,
    "merchant": 7,
    "amount": 25,
    "mcc": 13,
    "description": 12,
    "first_name": 1,
    "last_name": 2,
}

def build_mapping_from_positions(df_columns: list[str]) -> dict[str, str]:
    """
    Devuelve un dict canonical->colname basado en índices.
    df_columns aquí serán los nombres reales del df (COL_0, COL_1, ... o 0,1,...)
    """
    mapping: dict[str, str] = {}
    for key, idx in POSITIONAL.items():
        if 0 <= idx < len(df_columns):
            mapping[key] = df_columns[idx]
    return mapping
