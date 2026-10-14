from app.api.schemas import Extraction
from app.core.validate import validate_extraction


def test_ok_amounts():
    data = Extraction(
        doc_type="invoice",
        vendor="CloudTools GmbH",
        issue_date="2026-02-15",
        currency="EUR",
        net_amount=100.0,
        vat_amount=19.0,
        vat_rate=19.0,
        gross_amount=119.0,
        category="Software & Subscriptions",
    )
    ok, reasons = validate_extraction(data)
    assert ok
    assert reasons == []


def test_flags_net_vat_gross_mismatch():
    data = Extraction(
        doc_type="invoice",
        vendor="Broken Math Ltd",
        issue_date="2026-04-01",
        currency="GBP",
        net_amount=200.0,
        vat_amount=40.0,
        vat_rate=20.0,
        gross_amount=250.0,
        category="Professional Services",
    )
    ok, reasons = validate_extraction(data)
    assert not ok
    assert any("gross" in r for r in reasons)


def test_future_date():
    data = Extraction(
        doc_type="receipt",
        vendor="Cafe",
        issue_date="2099-01-01",
        currency="EUR",
        gross_amount=10.0,
        category="Meals & Entertainment",
    )
    ok, reasons = validate_extraction(data)
    assert not ok
    assert any("future" in r for r in reasons)


def test_bad_currency():
    data = Extraction(
        doc_type="other",
        vendor="X",
        currency="EURO",
        gross_amount=1.0,
        category="Other",
    )
    ok, reasons = validate_extraction(data)
    assert not ok
    assert any("currency" in r for r in reasons)
