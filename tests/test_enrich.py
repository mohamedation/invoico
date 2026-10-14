from app.api.schemas import Extraction
from app.core.extract import enrich_extraction


def test_infers_invoice_from_invoice_no():
    data = Extraction(
        doc_type="other",
        vendor="PixelHost Inc.",
        invoice_no="PH-88921",
        currency="USD",
        gross_amount=49.0,
        category="Software & Subscriptions",
    )
    out = enrich_extraction(data)
    assert out.doc_type == "invoice"


def test_does_not_invent_net_from_gross_minus_vat():
    """Preserve bad-math docs: missing net must stay missing, not become gross−vat."""
    data = Extraction(
        doc_type="other",
        vendor="Broken Math Ltd",
        invoice_no="ERR-001",
        currency="GBP",
        vat_amount=40.0,
        gross_amount=250.0,
        category="Professional Services",
    )
    out = enrich_extraction(data)
    assert out.doc_type == "invoice"
    assert out.net_amount is None


def test_derives_rate_when_net_and_vat_present():
    data = Extraction(
        doc_type="invoice",
        vendor="CloudTools GmbH",
        invoice_no="INV-1",
        currency="EUR",
        net_amount=100.0,
        vat_amount=19.0,
        gross_amount=119.0,
        category="Software & Subscriptions",
    )
    out = enrich_extraction(data)
    assert out.vat_rate == 19.0


def test_zero_vat_fills_rate():
    data = Extraction(
        doc_type="invoice",
        vendor="PixelHost Inc.",
        invoice_no="PH-1",
        currency="USD",
        net_amount=49.0,
        vat_amount=0.0,
        gross_amount=49.0,
        category="Software & Subscriptions",
    )
    out = enrich_extraction(data)
    assert out.vat_rate == 0.0
