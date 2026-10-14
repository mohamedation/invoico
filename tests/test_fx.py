from app.core.fx import convert_docs_to_eur, load_fx


def test_eur_passthrough():
    fx = load_fx()
    assert fx.to_eur(100.0, "EUR") == 100.0


def test_usd_to_eur():
    fx = load_fx()
    # 1 EUR = rate USD → 1 USD = 1/rate EUR
    expected = 1.0 / fx.rates["USD"]
    got = fx.to_eur(1.0, "USD")
    assert got is not None
    assert abs(got - expected) < 1e-9


def test_myr_supported():
    fx = load_fx()
    assert "MYR" in fx.rates
    assert fx.to_eur(4.5714, "MYR") == 1.0  # approx 1 EUR at snapshot rate


def test_convert_docs_bundle():
    docs = [
        {"id": 1, "currency": "EUR", "gross_amount": 100, "net_amount": 80, "vat_amount": 20},
        {"id": 2, "currency": "USD", "gross_amount": 111.88, "net_amount": 0, "vat_amount": 0},
    ]
    bundle = convert_docs_to_eur(docs)
    assert bundle["base"] == "EUR"
    assert "static" in bundle["disclaimer"].lower() or "demo" in bundle["disclaimer"].lower()
    assert abs(bundle["gross_eur"] - 200.0) < 0.05  # 100 EUR + ~100 EUR from USD
    assert not bundle["skipped"]
