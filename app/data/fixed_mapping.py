from __future__ import annotations

def fixed_mapping_for_your_headers() -> dict[str, str]:
    # Mapeo exacto a tus headers
    return {
        "date": "Transaction Date",
        "merchant": "Clean Merchant Name",
        "amount": "Total Transaction Amount",
        "mcc": "MCC",
        "description": "Purchase Category",
        # employee lo construimos en cleaning.py con First+Last
    }
