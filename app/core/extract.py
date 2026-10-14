"""Talk to Ollama, get structured invoice fields back."""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import ollama

from app.api.schemas import CATEGORIES, Extraction
from app.core.config import settings

EXTRACTION_PROMPT = """You are reading a photo/scan of an invoice or till receipt.

CRITICAL — money fields (people mess these up constantly):
- net_amount = Subtotal / Net / Amount before VAT (NOT the final Total).
- gross_amount = the BILL TOTAL after VAT. Labels like: Total, Rounded Total, TakeOut Total,
  Amount Due, Grand Total. On a European invoice: Subtotal 120 + VAT 24 → Total 144.
  Never copy Total into net_amount.
- cash_tendered = only when the slip literally says Cash / Cash Tendered (money handed over).
  Often BIGGER than the total (e.g. total 26.60, cash 100.00). NEVER put this in gross_amount.
  On a normal PDF invoice with Net/VAT/Total and NO cash line → cash_tendered=null, change_amount=null.
  Do NOT copy net_amount into cash_tendered or vat_amount into change_amount.
- change_amount = Change / CHANGE returned only.
- If you see Total 9.00, Cash 10.00, CHANGE 1.00 → gross=9, cash_tendered=10, change=1.

Also extract line_items — PRODUCT rows only (food, goods, services). Do NOT put
Total / Cash / Change / GST summary / TakeOut Total into line_items.
Sum of line amounts should match gross_amount (within rounding).

Ignore as amounts:
- Handwritten circled numbers unless they clearly replace a printed total
- Big store numbers at the top of the slip (e.g. "1950") — those are NOT the total
- Barcodes, phone numbers, GST / company registration IDs
- Extra zeros on unit prices like 9.000 → treat as 9.00

Other rules:
1. doc_type: "invoice" if it says INVOICE / TAX INVOICE; "receipt" for cash bill / till slip.
2. Dates as YYYY-MM-DD (25/12/2018 → 2018-12-25; day-first is common on MY/EU receipts).
3. currency: ISO code. RM / Ringgit → MYR. $ on a Malaysian receipt is usually MYR, not USD.
4. vat_amount / vat_rate from GST/VAT/SST lines when present (rate as percent, e.g. 6).
5. net_amount = pre-tax when shown; if price is tax-inclusive and only total is clear, you may
   leave net null rather than guess.
6. vendor = store / company name (seller), not the cashier or "Bill to".
7. category must be one of: """ + ", ".join(CATEGORIES) + """

Return JSON only. Use null for unknown fields. Prefer null over inventing digits.
"""

OLLAMA_FORMAT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "doc_type": {"type": "string", "enum": ["invoice", "receipt", "other"]},
        "vendor": {"type": ["string", "null"]},
        "invoice_no": {"type": ["string", "null"]},
        "issue_date": {"type": ["string", "null"]},
        "due_date": {"type": ["string", "null"]},
        "currency": {"type": ["string", "null"]},
        "net_amount": {"type": ["number", "null"]},
        "vat_amount": {"type": ["number", "null"]},
        "vat_rate": {"type": ["number", "null"]},
        "gross_amount": {"type": ["number", "null"]},
        "cash_tendered": {"type": ["number", "null"]},
        "change_amount": {"type": ["number", "null"]},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": ["string", "null"]},
                    "qty": {"type": ["number", "null"]},
                    "amount": {"type": ["number", "null"]},
                },
            },
        },
        "category": {"type": "string", "enum": list(CATEGORIES)},
    },
    "required": [
        "doc_type",
        "vendor",
        "invoice_no",
        "issue_date",
        "currency",
        "net_amount",
        "vat_amount",
        "vat_rate",
        "gross_amount",
        "cash_tendered",
        "change_amount",
        "line_items",
        "category",
    ],
}


def _client() -> ollama.Client:
    return ollama.Client(host=settings.ollama_host)


def check_ollama() -> tuple[bool, str]:
    try:
        client = _client()
        models = client.list()
        names = []
        for m in getattr(models, "models", None) or models.get("models", []):
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if name is None and isinstance(m, dict):
                name = m.get("model") or m.get("name")
            if name:
                names.append(name)
        wanted = settings.model
        found = any(
            n == wanted or n.startswith(wanted + "-") or n.startswith(wanted + ":")
            for n in names
        )
        found = found or any(wanted in n for n in names)
        if not found:
            return False, f"model '{wanted}' not found. Pulled: {names or 'none'}"
        return True, f"ok ({wanted})"
    except Exception as exc:
        return False, str(exc)


def _dec(value: float | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()[:16]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            from datetime import datetime

            return datetime.strptime(v[:11].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 03 Mar 2018 18:22
    try:
        from datetime import datetime

        return datetime.strptime(v[:11].strip(), "%d %b %Y").strftime("%Y-%m-%d")
    except ValueError:
        return v if re.match(r"\d{4}-\d{2}-\d{2}", v) else None


def _product_item_sum(data: Extraction) -> Decimal | None:
    """Sum line amounts, skipping totals/cash rows and a lone GST amount line."""
    skip = re.compile(
        r"\b(total|cash|change|gst|vat|rounding|tender|amount due|take\s*out)\b",
        re.I,
    )
    vat = _dec(data.vat_amount)
    amounts: list[Decimal] = []
    for i in data.line_items:
        if i.amount is None:
            continue
        amt = _dec(i.amount) or Decimal("0")
        if i.description and skip.search(i.description):
            continue
        # McD-style: model appends the GST figure as a fake last line
        if vat is not None and abs(amt - vat) < Decimal("0.021"):
            desc = (i.description or "").lower()
            if not desc or "gst" in desc or "vat" in desc or "tax" in desc:
                continue
        amounts.append(amt)
    if not amounts:
        return None
    return sum(amounts, start=Decimal("0"))


def enrich_extraction(data: Extraction) -> Extraction:
    """Fix currency/date aliases; recover total from items or cash−change when the model slips."""
    patch: dict[str, Any] = {}

    if data.currency:
        cur = data.currency.strip().upper().replace(".", "")
        aliases = {"RM": "MYR", "RINGGIT": "MYR", "€": "EUR", "£": "GBP"}
        if cur in aliases:
            patch["currency"] = aliases[cur]
        elif cur == "$":
            patch["currency"] = "MYR"
    elif data.vendor and re.search(r"\b(sdn\.?\s*bhd|malaysia|johor|selangor)\b", data.vendor, re.I):
        patch["currency"] = "MYR"

    norm_date = _normalize_date(data.issue_date)
    if norm_date and norm_date != data.issue_date:
        patch["issue_date"] = norm_date

    if data.doc_type == "other":
        if data.invoice_no:
            patch["doc_type"] = "invoice"
        elif data.vendor and re.search(r"\b(ltd|gmbh|inc|llc|sdn|bhd|sarl|bv)\b", data.vendor, re.I):
            patch["doc_type"] = "invoice"

    net = _dec(data.net_amount)
    vat = _dec(data.vat_amount)
    gross = _dec(data.gross_amount)
    rate = _dec(data.vat_rate)
    cash = _dec(data.cash_tendered)
    change = _dec(data.change_amount)
    item_sum = _product_item_sum(data)

    # Classic mistake: gross copied from cash tendered
    if cash is not None and change is not None and gross is not None:
        if abs(gross - cash) < Decimal("0.02") and cash > change:
            recovered = cash - change
            patch["gross_amount"] = float(recovered)
            gross = recovered

    # Till slips / store IDs: trust product lines (or cash−change) when gross is wild
    if item_sum is not None and item_sum > 0:
        if gross is None:
            patch["gross_amount"] = float(item_sum)
            gross = item_sum
        elif abs(gross - item_sum) > max(Decimal("1.0"), item_sum * Decimal("0.25")):
            if cash is not None and change is not None:
                recovered = cash - change
                if abs(recovered - item_sum) <= Decimal("0.15"):
                    patch["gross_amount"] = float(recovered)
                    gross = recovered
                else:
                    target = item_sum + vat if (vat and vat > 0) else item_sum
                    patch["gross_amount"] = float(target)
                    gross = target
                    if vat and vat > 0:
                        patch["net_amount"] = float(item_sum)
                        net = item_sum
            else:
                target = item_sum + vat if (vat and vat > 0) else item_sum
                patch["gross_amount"] = float(target)
                gross = target
                if vat and vat > 0:
                    patch["net_amount"] = float(item_sum)
                    net = item_sum

    # ACME-style: lines = Subtotal, model pasted Total into net.
    # Do NOT rewrite gross when net matches the lines but net+VAT≠gross —
    # that is often a real document error (our bad-math sample) and must stay flagged.
    if item_sum is not None and item_sum > 0 and vat is not None and vat > 0:
        implied_gross = item_sum + vat
        rate_from_items = (vat / item_sum) * Decimal("100")
        # Total pasted into net (net ≈ gross, both disagree with line subtotal)
        net_looks_like_total = (
            net is not None
            and gross is not None
            and abs(net - gross) <= Decimal("0.05")
            and abs(net - item_sum) > Decimal("0.15")
        )
        # VAT% only makes sense on the line sum (e.g. 24/144=16.7% but lines=120 → 20%)
        rate_clashes_net = (
            net is not None
            and net != 0
            and abs(net - item_sum) > Decimal("0.15")
            and abs((vat / net) * Decimal("100") - rate_from_items) > Decimal("2.0")
        )
        if net_looks_like_total or rate_clashes_net:
            patch["net_amount"] = float(item_sum)
            patch["gross_amount"] = float(implied_gross)
            net, gross = item_sum, implied_gross
            patch["vat_rate"] = float(round(rate_from_items, 2))
            rate = rate_from_items
        elif gross is not None and abs(gross - item_sum) <= Decimal("0.05"):
            # gross was set to subtotal; add VAT
            patch["gross_amount"] = float(implied_gross)
            gross = implied_gross
            if net is None or abs(net - item_sum) > Decimal("0.15"):
                patch["net_amount"] = float(item_sum)
                net = item_sum

    if gross is None and net is not None and vat is not None:
        patch["gross_amount"] = float(net + vat)
        gross = net + vat

    if net is not None and vat is not None and net != 0:
        derived = (vat / net) * Decimal("100")
        if rate is None:
            patch["vat_rate"] = float(round(derived, 2))
        elif rate == 0 and vat != 0:
            patch["vat_rate"] = float(round(derived, 2))

    if (
        "vat_rate" not in patch
        and data.vat_rate is None
        and net is not None
        and gross is not None
        and vat is not None
        and vat == 0
        and net == gross
    ):
        patch["vat_rate"] = 0.0

    if not patch:
        return data
    return data.model_copy(update=patch)


def extract_from_images(page_pngs: list[bytes]) -> tuple[Extraction | None, str, str | None]:
    client = _client()
    last_raw = ""
    last_err: str | None = None

    images = page_pngs[:1]
    if len(page_pngs) > 1:
        images.append(page_pngs[-1])

    for attempt in range(2):
        try:
            resp = client.chat(
                model=settings.model,
                messages=[
                    {
                        "role": "user",
                        "content": EXTRACTION_PROMPT
                        + (
                            "\nRetry: gross_amount must be the bill total, not cash. Include line_items."
                            if attempt
                            else ""
                        ),
                        "images": images,
                    }
                ],
                format=OLLAMA_FORMAT,
                think=False,
                options={"temperature": 0, "num_predict": 1536},
            )
            content = (resp.message.content or "").strip()
            last_raw = content
            if not content:
                last_err = "model returned empty content"
                continue
            data = Extraction.model_validate_json(content)
            if data.vendor is None and data.gross_amount is None and data.invoice_no is None:
                last_err = "model returned no usable fields"
                continue
            return enrich_extraction(data), last_raw, None
        except Exception as exc:
            last_err = str(exc)
            try:
                if not last_raw.strip():
                    continue
                parsed: dict[str, Any] = json.loads(last_raw)
                data = Extraction.model_validate(parsed)
                if data.vendor is None and data.gross_amount is None and data.invoice_no is None:
                    continue
                return enrich_extraction(data), last_raw, None
            except Exception:
                continue

    return None, last_raw, last_err or "extraction failed"
