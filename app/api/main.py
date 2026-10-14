"""FastAPI side — stays on 127.0.0.1, talks to Ollama + SQLite."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.api.schemas import AnalyzeOut, ClearOut, DocumentOut, DocumentUpdate, HealthOut
from app.core import db
from app.core.analyze import analyze_documents
from app.core.config import settings
from app.core.extract import check_ollama
from app.core.pipeline import confirm_document, process_upload

app = FastAPI(title="Invoico", version="0.1.0")


@app.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    ok, detail = check_ollama()
    return HealthOut(ok=ok, ollama=ok, model=settings.model, detail=detail)


@app.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    force: bool = Query(False, description="Re-run extraction even if we already have this file"),
) -> dict:
    suffix = Path(file.filename or "upload.bin").suffix.lower()
    if suffix not in {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        raise HTTPException(400, f"Unsupported type: {suffix}")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        doc = process_upload(
            tmp_path,
            original_name=file.filename or tmp_path.name,
            force=force,
        )
    finally:
        tmp_path.unlink(missing_ok=True)

    return doc


@app.get("/documents", response_model=list[DocumentOut])
def list_docs(
    status: Optional[str] = None,
    category: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
) -> list[dict]:
    return db.list_documents(status=status, category=category, date_from=date_from, date_to=date_to)


@app.get("/documents/{doc_id}", response_model=DocumentOut)
def get_doc(doc_id: int) -> dict:
    doc = db.get_document(doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@app.patch("/documents/{doc_id}", response_model=DocumentOut)
def patch_doc(doc_id: int, body: DocumentUpdate) -> dict:
    if not db.get_document(doc_id):
        raise HTTPException(404, "Not found")
    payload = body.model_dump(exclude_unset=True)
    confirm = payload.pop("confirm", False)
    if confirm:
        doc = confirm_document(doc_id, payload)
    else:
        doc = db.update_document(doc_id, payload)
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@app.delete("/documents/{doc_id}")
def delete_doc(doc_id: int) -> dict:
    if not db.delete_document(doc_id):
        raise HTTPException(404, "Not found")
    return {"ok": True, "id": doc_id}


@app.delete("/documents", response_model=ClearOut)
def clear_documents() -> ClearOut:
    return ClearOut(deleted=db.clear_all())


@app.post("/analyze", response_model=AnalyzeOut)
def analyze() -> AnalyzeOut:
    try:
        result = analyze_documents(db.list_documents())
    except Exception as exc:
        raise HTTPException(502, f"analyze failed: {exc}") from exc
    return AnalyzeOut(**result)


@app.get("/export.csv")
def export_csv() -> StreamingResponse:
    rows = db.list_documents()
    buf = io.StringIO()
    fields = [
        "id", "vendor", "invoice_no", "issue_date", "due_date", "currency",
        "net_amount", "vat_amount", "vat_rate", "gross_amount", "category",
        "doc_type", "status", "note", "review_reason", "created_at",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k) for k in fields})
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoices.csv"},
    )
