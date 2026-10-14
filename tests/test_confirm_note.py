from app.core import db
from app.core.config import settings
from app.core.pipeline import confirm_document


def test_bad_math_stays_in_note_when_confirmed_as_is(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "upload_dir", tmp_path / "uploads")
    db.init_db()

    doc_id = db.insert_document(
        {
            "file_path": str(tmp_path / "x.png"),
            "sha256": "abc",
            "doc_type": "invoice",
            "vendor": "Broken Math Ltd",
            "invoice_no": "ERR-001",
            "currency": "GBP",
            "net_amount": 200.0,
            "vat_amount": 40.0,
            "vat_rate": 20.0,
            "gross_amount": 250.0,
            "category": "Professional Services",
            "status": "needs_review",
            "review_reason": "net + VAT ≠ gross",
            "note": "net + VAT ≠ gross",
        }
    )

    updated = confirm_document(
        doc_id,
        {
            "vendor": "Broken Math Ltd",
            "invoice_no": "ERR-001",
            "currency": "GBP",
            "net_amount": 200.0,
            "vat_amount": 40.0,
            "vat_rate": 20.0,
            "gross_amount": 250.0,
            "category": "Professional Services",
            "doc_type": "invoice",
            "note": "net + VAT ≠ gross (200.0 + 40.0 = 240.0, gross=250.0)",
            "confirm": True,
        },
    )
    assert updated is not None
    assert updated["status"] == "confirmed"
    assert updated["note"]
    assert "gross" in updated["note"].lower() or "≠" in updated["note"] or "VAT" in updated["note"]
    assert updated["invoice_no"] == "ERR-001"


def test_save_document_replaces_same_id(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "db_path", tmp_path / "t.db")
    db.init_db()
    doc_id = db.insert_document(
        {
            "file_path": "a.png",
            "sha256": "sha1",
            "invoice_no": "PH-88921",
            "vendor": "PixelHost Inc.",
            "status": "needs_review",
            "gross_amount": 10.0,
        }
    )
    new_id = db.save_document(
        {
            "file_path": "b.png",
            "sha256": "sha2",
            "invoice_no": "PH-88921",
            "vendor": "PixelHost Inc.",
            "status": "auto_ok",
            "gross_amount": 49.0,
            "note": None,
        },
        replace_id=doc_id,
    )
    assert new_id == doc_id
    row = db.get_document(doc_id)
    assert row["gross_amount"] == 49.0
    assert row["sha256"] == "sha2"
    assert db.get_by_invoice_no("PH-88921")["id"] == doc_id
