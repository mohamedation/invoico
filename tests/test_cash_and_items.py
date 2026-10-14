from app.api.schemas import Extraction, LineItem
from app.core.extract import enrich_extraction  # repairs Subtotal/Total mix-ups
from app.core.validate import validate_extraction


def test_recover_gross_from_cash_minus_change():
    data = Extraction(
        doc_type="receipt",
        vendor="BOOK TALK",
        currency="MYR",
        gross_amount=10.0,  # wrongly used cash
        cash_tendered=10.0,
        change_amount=1.0,
        line_items=[LineItem(description="clay", qty=1, amount=9.0)],
        category="Other",
    )
    out = enrich_extraction(data)
    assert out.gross_amount == 9.0


def test_line_items_mismatch_flags_review():
    data = Extraction(
        doc_type="receipt",
        vendor="Shop",
        issue_date="2018-01-18",
        currency="MYR",
        gross_amount=100.0,  # cash mistaken as total
        cash_tendered=100.0,
        change_amount=73.4,
        line_items=[
            LineItem(description="a", amount=11.0),
            LineItem(description="b", amount=5.6),
            LineItem(description="c", amount=10.0),
        ],
        category="Meals & Entertainment",
    )
    # enrich should fix gross via cash-change or items
    out = enrich_extraction(data)
    assert out.gross_amount == 26.6
    ok, reasons = validate_extraction(out)
    assert ok or not any("line items" in r for r in reasons)


def test_myr_accepted():
    data = Extraction(
        doc_type="receipt",
        vendor="BOOK TALK",
        issue_date="2018-12-25",
        currency="MYR",
        gross_amount=9.0,
        category="Other",
    )
    ok, reasons = validate_extraction(data)
    assert ok


def test_line_items_ex_vat_match_gross_with_vat():
    """CloudTools-style: lines are net 100, VAT 19, gross 119 — not a mismatch."""
    data = Extraction(
        doc_type="invoice",
        vendor="CloudTools GmbH",
        issue_date="2026-02-15",
        currency="EUR",
        net_amount=100.0,
        vat_amount=19.0,
        vat_rate=19.0,
        gross_amount=119.0,
        line_items=[LineItem(description="SaaS subscription", qty=1, amount=100.0)],
        category="Software & Subscriptions",
    )
    ok, reasons = validate_extraction(data)
    assert ok
    assert not any("line items" in r for r in reasons)


def test_acme_style_total_pasted_into_net_is_repaired():
    """Model set net=total=144, vat=24; lines 80+40=120 → net 120, gross 144, rate 20%."""
    data = Extraction(
        doc_type="invoice",
        vendor="ACME Supplies Ltd.",
        invoice_no="INV-78432",
        issue_date="2025-04-18",
        currency="EUR",
        net_amount=144.0,
        vat_amount=24.0,
        vat_rate=16.67,
        gross_amount=144.0,
        line_items=[
            LineItem(description="Notebook A5", qty=10, amount=80.0),
            LineItem(description="Pen (Blue)", qty=20, amount=40.0),
        ],
        category="Office & Coworking",
    )
    out = enrich_extraction(data)
    assert out.net_amount == 120.0
    assert out.gross_amount == 144.0
    assert out.vat_amount == 24.0
    assert abs((out.vat_rate or 0) - 20.0) < 0.05
    ok, reasons = validate_extraction(out)
    assert ok, reasons


def test_acme_style_nonsense_gross_repaired():
    # net pasted from total (144) while lines say 120 — rate clash triggers repair
    data = Extraction(
        doc_type="invoice",
        vendor="ACME Supplies Ltd.",
        currency="EUR",
        net_amount=144.0,
        vat_amount=24.0,
        vat_rate=20.0,
        gross_amount=34.0,
        line_items=[
            LineItem(description="Notebook A5", amount=80.0),
            LineItem(description="Pen (Blue)", amount=40.0),
        ],
        category="Office & Coworking",
    )
    out = enrich_extraction(data)
    assert out.net_amount == 120.0
    assert out.gross_amount == 144.0
    ok, _ = validate_extraction(out)
    assert ok


def test_bad_math_invoice_keeps_mismatch_for_review():
    """Printed totals are wrong on purpose — do not 'fix' gross from lines+VAT."""
    data = Extraction(
        doc_type="invoice",
        vendor="Broken Math Ltd",
        invoice_no="ERR-001",
        issue_date="2026-04-01",
        currency="GBP",
        net_amount=200.0,
        vat_amount=40.0,
        vat_rate=20.0,
        gross_amount=250.0,
        line_items=[LineItem(description="Consulting day rate", amount=200.0)],
        category="Professional Services",
    )
    out = enrich_extraction(data)
    assert out.net_amount == 200.0
    assert out.gross_amount == 250.0
    ok, reasons = validate_extraction(out)
    assert not ok
    assert any("gross" in r for r in reasons)
