from app.core.analyze import build_spend_snapshot


def test_month_over_month_delta_in_eur():
    docs = [
        {
            "status": "confirmed",
            "gross_amount": 100,
            "currency": "EUR",
            "category": "Software & Subscriptions",
            "vendor": "A",
            "issue_date": "2026-01-10",
        },
        {
            "status": "confirmed",
            "gross_amount": 150,
            "currency": "EUR",
            "category": "Software & Subscriptions",
            "vendor": "A",
            "issue_date": "2026-02-10",
        },
    ]
    snap = build_spend_snapshot(docs)
    assert snap["document_count"] == 2
    assert snap["totals"]["by_month_eur"]["2026-01"] == 100
    assert snap["totals"]["by_month_eur"]["2026-02"] == 150
    assert snap["fx"]["base"] == "EUR"
    assert "demo" in snap["fx"]["disclaimer"].lower() or "static" in snap["fx"]["disclaimer"].lower()


def test_clear_all(tmp_path, monkeypatch):
    from app.core import db
    from app.core.config import settings

    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    db.init_db()
    db.insert_document(
        {
            "file_path": "x.png",
            "sha256": "abc",
            "status": "confirmed",
            "invoice_no": "1",
        }
    )
    assert db.clear_all() == 1
    assert db.list_documents() == []
