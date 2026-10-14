"""Turn PDFs / photos into PNG bytes the vision model can eat."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from app.core.config import settings

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PDF_EXTS = {".pdf"}


def _to_png_bytes(img: Image.Image) -> bytes:
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    max_w = settings.max_image_width
    if w > max_w:
        ratio = max_w / w
        img = img.resize((max_w, int(h * ratio)), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def file_to_page_images(path: Path) -> list[bytes]:
    """Return up to max_pdf_pages PNG byte blobs for the model."""
    suffix = path.suffix.lower()

    if suffix in IMAGE_EXTS:
        with Image.open(path) as img:
            img.load()
            # Fix EXIF orientation when present
            try:
                from PIL import ImageOps

                img = ImageOps.exif_transpose(img)
            except Exception:
                pass
            return [_to_png_bytes(img)]

    if suffix in PDF_EXTS:
        import fitz  # PyMuPDF

        doc = fitz.open(path)
        pages: list[bytes] = []
        try:
            n = min(len(doc), settings.max_pdf_pages)
            for i in range(n):
                page = doc.load_page(i)
                # ~150 DPI-ish matrix for readable text without huge images
                pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                pages.append(pix.tobytes("png"))
        finally:
            doc.close()
        if not pages:
            raise ValueError("PDF has no pages")
        return pages

    raise ValueError(f"Unsupported file type: {suffix}")
