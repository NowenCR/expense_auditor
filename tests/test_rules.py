import pandas as pd
from app.core.models import Catalog
from app.engine.rules import apply_rules

def test_keyword_rule_flags():
    cat = Catalog(
        keyword_rules=[{"pattern":"(?i)casino","severity":"DIRECT_WARN","reason":"casino"}]
    )
    df = pd.DataFrame({"merchant":["Nice Casino"],"mcc":["1234"],"amount":[10]})
    out = apply_rules(df, cat)
    assert out.loc[0, "flag"] == "DIRECT_WARN"
    assert "casino" in out.loc[0, "reasons"]
