import pandas as pd
from app.core.models import Catalog
from app.engine.validator import validate_generated_catalog

def test_validator_rejects_unknown_mcc():
    df = pd.DataFrame({"merchant":["A"],"mcc":["1111"],"amount":[100]})
    cat = Catalog(mcc_rules=[{"mcc":"9999","severity":"DIRECT_WARN","reason":"x"}])
    ok, errs = validate_generated_catalog(cat, df)
    assert not ok
    assert any("no existe" in e for e in errs)
