"""Math / date / currency / line-item checks. Model reads; this file double-checks."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.api.schemas import Extraction

ISO_CURRENCIES = {
    "EUR", "USD", "GBP", "CHF", "CAD", "AUD", "JPY", "SEK", "NOK", "DKK",
    "PLN", "CZK", "HUF", "RON", "BGN", "TRY", "INR", "BRL", "MXN", "ZAR",
    "CNY", "KRW", "NZD", "SGD", "HKD", "AED", "SAR", "ILS", "THB", "MYR",
}


def _dec(value: Optional[float]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: Optional[str]) -> tuple[Optional[date], Optional[str]]:
    if not value:
        return None, None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date(), None
    except ValueError:
        return None, f"issue_date '{value}' is not YYYY-MM-DD"


def validate_extraction(data: Extraction) -> tuple[bool, list[str]]:
    """Return (ok, reasons). ok=False means needs_review."""
    reasons: list[str] = []

    net = _dec(data.net_amount)
    vat = _dec(data.vat_amount)
    gross = _dec(data.gross_amount)
    rate = _dec(data.vat_rate)
    cash = _dec(data.cash_tendered)
    change = _dec(data.change_amount)

    if net is not None and vat is not None and gross is not None:
        if abs((net + vat) - gross) > Decimal("0.05"):
            reasons.append(
                f"net + VAT ≠ gross ({net} + {vat} = {net + vat}, gross={gross})"
            )

    if net is not None and vat is not None and rate is not None and net != 0:
        expected = (vat / net) * Decimal("100")
        if abs(expected - rate) > Decimal("1.5"):
            reasons.append(
                f"VAT rate mismatch: vat/net≈{expected:.2f}%, claimed {rate}%"
            )

    # Product line items should add up to the bill total (skip Total/Cash rows)
    import re

    skip = re.compile(
        r"\b(total|cash|change|gst|vat|rounding|tender|amount due|take\s*out)\b",
        re.I,
    )
    item_amounts = [
        _dec(i.amount)
        for i in data.line_items
        if i.amount is not None and not (i.description and skip.search(i.description))
    ]
    item_amounts = [a for a in item_amounts if a is not None]
    if item_amounts and gross is not None:
        item_sum = sum(item_amounts, start=Decimal("0"))
        tol = Decimal("0.15")
        # Lines are often net (ex-VAT): 100 + 19 VAT = 119 gross — that is fine. this also depends on the country/region.
        matches_gross = abs(item_sum - gross) <= tol
        matches_gross_with_vat = (
            vat is not None and abs((item_sum + vat) - gross) <= tol
        )
        matches_net = net is not None and abs(item_sum - net) <= tol
        if not (matches_gross or matches_gross_with_vat or matches_net):
            if vat is not None:
                reasons.append(
                    f"line items sum ≠ gross "
                    f"({item_sum} vs gross={gross}; with VAT {item_sum + vat})"
                )
            else:
                reasons.append(
                    f"line items sum ≠ gross ({item_sum} vs gross={gross})"
                )

    # Cash tendered is not the bill — flag obvious swaps
    if cash is not None and gross is not None and cash > 0:
        if abs(cash - gross) < Decimal("0.02") and change is not None and change > Decimal("0.05"):
            reasons.append(
                f"gross equals cash_tendered ({cash}) but change is {change} — likely swapped total/cash"
            )
        if change is not None and abs((cash - change) - (gross or Decimal("0"))) > Decimal("0.10"):
            # only warn when all three present and inconsistent
            if gross is not None:
                reasons.append(
                    f"cash − change ≠ gross ({cash} − {change} = {cash - change}, gross={gross})"
                )

    issue, date_err = _parse_date(data.issue_date)
    if date_err:
        reasons.append(date_err)
    elif issue is not None:
        today = date.today()
        if issue > today:
            reasons.append(f"issue_date {issue} is in the future")
        if issue.year < 1990:
            reasons.append(f"issue_date {issue} looks unrealistically old")

    due, due_err = _parse_date(data.due_date)
    if due_err:
        reasons.append(due_err.replace("issue_date", "due_date"))

    if data.currency:
        code = data.currency.strip().upper()
        if len(code) != 3 or code not in ISO_CURRENCIES:
            reasons.append(f"currency '{data.currency}' is not a known ISO code")

    if not data.vendor and data.gross_amount is None:
        reasons.append("no vendor and no gross amount extracted")

    return (len(reasons) == 0), reasons
