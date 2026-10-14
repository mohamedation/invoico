"""Glue: save upload → extract → validate → upsert into SQLite."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from app.api.schemas import Extraction
from app.core import categorize, db
from app.core.config import settings
from app.core.extract import extract_from_images
from app.core.pdf import file_to_page_images
from app.core.validate import validate_extraction


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_replace_id(
    sha: str,
    *,
    force: bool,
    invoice_no: str | None = None,
    vendor: str | None = None,
) -> tuple[int | None, dict[str, Any] | None]:
    """Same file hash or same invoice # → reuse that row id instead of duplicating."""
    by_sha = db.get_by_sha(sha)
    if by_sha:
        if force:
            return by_sha["id"], by_sha
        return None, by_sha  # caller treats as duplicate skip

    if invoice_no:
        by_inv = db.get_by_invoice_no(invoice_no, vendor)
        if by_inv:
            return by_inv["id"], by_inv
    return None, None


def process_upload(
    source: Path,
    original_name: str | None = None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Save the file, run extraction, write/replace the DB row."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    name = original_name or source.name
    sha = _sha256(source)

    replace_id, existing = _resolve_replace_id(sha, force=force)
    if existing and replace_id is None and not force:
        # identical file already stored — skip unless force
        existing["duplicate"] = True
        return existing

    dest = settings.upload_dir / f"{sha[:16]}_{Path(name).name}"
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)

    try:
        pages = file_to_page_images(dest)
    except Exception as exc:
        doc_id = db.save_document(
            {
                "file_path": str(dest),
                "sha256": sha,
                "status": "failed",
                "review_reason": f"could not read file: {exc}",
                "note": f"could not read file: {exc}",
                "model_used": settings.model,
            },
            replace_id=replace_id,
        )
        return db.get_document(doc_id)  # type: ignore[return-value]

    extraction, raw, err = extract_from_images(pages)
    if extraction is None:
        doc_id = db.save_document(
            {
                "file_path": str(dest),
                "sha256": sha,
                "status": "failed",
                "review_reason": err or "model returned unparseable output",
                "note": err or "model returned unparseable output",
                "model_used": settings.model,
                "raw_json": raw or None,
            },
            replace_id=replace_id,
        )
        return db.get_document(doc_id)  # type: ignore[return-value]

    # If we only matched by hash so far, also fold into an existing invoice_no row
    if replace_id is None and extraction.invoice_no:
        by_inv = db.get_by_invoice_no(extraction.invoice_no, extraction.vendor)
        if by_inv:
            replace_id = by_inv["id"]

    ok, reasons = validate_extraction(extraction)
    category = categorize.resolve_category(extraction.vendor, extraction.category)
    note = "; ".join(reasons) if reasons else None

    status = "auto_ok" if ok else "needs_review"

    doc_id = db.save_document(
        {
            "file_path": str(dest),
            "sha256": sha,
            "doc_type": extraction.doc_type,
            "vendor": extraction.vendor,
            "invoice_no": extraction.invoice_no,
            "issue_date": extraction.issue_date,
            "due_date": extraction.due_date,
            "currency": extraction.currency.upper() if extraction.currency else None,
            "net_amount": extraction.net_amount,
            "vat_amount": extraction.vat_amount,
            "vat_rate": extraction.vat_rate,
            "gross_amount": extraction.gross_amount,
            "category": category,
            "status": status,
            "review_reason": note,
            "note": note,
            "model_used": settings.model,
            "raw_json": raw,
        },
        replace_id=replace_id,
    )
    return db.get_document(doc_id)  # type: ignore[return-value]


def confirm_document(doc_id: int, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Save edits + mark confirmed. If the math is still wrong, keep the note."""
    fields = {k: v for k, v in updates.items() if k != "confirm"}
    # Allow clearing optional text fields with empty string → None
    for key in ("vendor", "invoice_no", "issue_date", "due_date", "currency", "note"):
        if key in fields and fields[key] == "":
            fields[key] = None

    # Re-validate the values being saved
    extraction = Extraction(
        doc_type=fields.get("doc_type") or "other",
        vendor=fields.get("vendor"),
        invoice_no=fields.get("invoice_no"),
        issue_date=fields.get("issue_date"),
        due_date=fields.get("due_date"),
        currency=fields.get("currency"),
        net_amount=fields.get("net_amount"),
        vat_amount=fields.get("vat_amount"),
        vat_rate=fields.get("vat_rate"),
        gross_amount=fields.get("gross_amount"),
        category=fields.get("category") or "Other",
    )
    ok, reasons = validate_extraction(extraction)
    auto_note = "; ".join(reasons) if reasons else None

    # Prefer an explicit user note; otherwise keep auto validation note when as-is
    user_note = fields.pop("note", None)
    if user_note is not None and str(user_note).strip():
        note = str(user_note).strip()
    else:
        note = auto_note

    fields["status"] = "confirmed"
    fields["note"] = note
    fields["review_reason"] = note

    # Same invoice number → replace that row instead of orphaning duplicates
    invoice_no = fields.get("invoice_no")
    if invoice_no:
        other = db.get_by_invoice_no(invoice_no, fields.get("vendor"))
        if other and other["id"] != doc_id:
            # Merge into the older/existing invoice id
            target_id = other["id"]
            db.update_document(target_id, fields)
            # Drop the temporary row we were editing
            with db.connect() as conn:
                conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            doc = db.get_document(target_id)
        else:
            doc = db.update_document(doc_id, fields)
    else:
        doc = db.update_document(doc_id, fields)

    if doc:
        categorize.remember_vendor_category(doc.get("vendor"), doc.get("category") or "Other")
    return doc
