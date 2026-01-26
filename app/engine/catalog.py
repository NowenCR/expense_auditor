from __future__ import annotations
import json
from pathlib import Path
from app.core.models import Catalog

def load_catalog(path: str) -> Catalog:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Catalog.model_validate(data)

def save_catalog(catalog: Catalog, path: str) -> None:
    Path(path).write_text(
        json.dumps(catalog.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
