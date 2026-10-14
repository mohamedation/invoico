#!/usr/bin/env python3
"""Generate synthetic invoice/receipt PNGs for demos. No real data."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "samples"


def font(size: int):
    for name in (
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


def draw_invoice(
    filename: str,
    vendor: str,
    invoice_no: str,
    issue: str,
    currency: str,
    net: str,
    vat: str,
    rate: str,
    gross: str,
    lines: list[str],
) -> None:
    img = Image.new("RGB", (800, 1100), "white")
    d = ImageDraw.Draw(img)
    title = font(36)
    body = font(22)
    small = font(18)

    y = 40
    d.text((40, y), vendor, fill=(20, 20, 20), font=title)
    y += 55
    d.text((40, y), "INVOICE", fill=(40, 80, 160), font=title)
    y += 60
    d.text((40, y), f"Invoice No: {invoice_no}", fill="black", font=body)
    y += 32
    d.text((40, y), f"Date: {issue}", fill="black", font=body)
    y += 32
    d.text((40, y), "Bill to: Alex Freelancer / Demo Client", fill=(80, 80, 80), font=small)
    y += 50
    d.line([(40, y), (760, y)], fill=(200, 200, 200), width=2)
    y += 20
    for line in lines:
        d.text((40, y), line, fill="black", font=body)
        y += 30
    y += 30
    d.line([(40, y), (760, y)], fill=(200, 200, 200), width=2)
    y += 25
    # Keep label + value on one clear line — small VLMs miss split columns
    for line in (
        f"Net amount: {net} {currency}",
        f"VAT ({rate}%): {vat} {currency}",
        f"Total due (gross): {gross} {currency}",
    ):
        d.text((40, y), line, fill="black", font=body)
        y += 34

    d.text((40, 1040), "SYNTHETIC SAMPLE — not a real invoice", fill=(160, 160, 160), font=small)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    img.save(path)
    print(f"wrote {path}")


def draw_receipt(filename: str) -> None:
    img = Image.new("RGB", (480, 720), (248, 248, 245))
    d = ImageDraw.Draw(img)
    body = font(20)
    small = font(16)
    y = 30
    d.text((120, y), "CAFE NORD", fill="black", font=font(28))
    y += 40
    d.text((90, y), "Receipt (demo)", fill=(100, 100, 100), font=small)
    y += 40
    d.text((40, y), "2026-03-12  12:41", fill="black", font=body)
    y += 40
    for line in ("Espresso ........ 3.50", "Sandwich ........ 8.90", "Water ........... 2.00"):
        d.text((40, y), line, fill="black", font=body)
        y += 28
    y += 20
    d.text((40, y), "Net      14.40 EUR", fill="black", font=body)
    y += 28
    d.text((40, y), "VAT 7%    1.01 EUR", fill="black", font=body)
    y += 28
    d.text((40, y), "TOTAL    15.41 EUR", fill="black", font=font(24))
    y += 50
    d.text((40, y), "Thank you!", fill=(80, 80, 80), font=small)
    d.text((40, 680), "SYNTHETIC SAMPLE", fill=(160, 160, 160), font=small)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    img.save(path)
    print(f"wrote {path}")


def main() -> int:
    draw_invoice(
        "invoice_cloudtools.png",
        vendor="CloudTools GmbH",
        invoice_no="INV-2026-1042",
        issue="2026-02-15",
        currency="EUR",
        net="100.00",
        vat="19.00",
        rate="19",
        gross="119.00",
        lines=["SaaS subscription — Feb 2026     100.00 EUR"],
    )
    draw_invoice(
        "invoice_us_hosting.png",
        vendor="PixelHost Inc.",
        invoice_no="PH-88921",
        issue="2026-01-08",
        currency="USD",
        net="49.00",
        vat="0.00",
        rate="0",
        gross="49.00",
        lines=["VPS Medium — monthly               49.00 USD"],
    )
    draw_receipt("receipt_cafe.png")
    # Intentional arithmetic mismatch for validation demo
    draw_invoice(
        "invoice_bad_math.png",
        vendor="Broken Math Ltd",
        invoice_no="ERR-001",
        issue="2026-04-01",
        currency="GBP",
        net="200.00",
        vat="40.00",
        rate="20",
        gross="250.00",  # should be 240 — flags needs_review if model reads correctly
        lines=["Consulting day rate               200.00 GBP", "(totals intentionally inconsistent)"],
    )
    print(f"\nSamples in {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
