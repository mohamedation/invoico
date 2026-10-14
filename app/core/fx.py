"""Static ECB euro reference rates for demo totals (EUR as base).

The CSV is a snapshot (not live). Rates are "1 EUR = X currency", so
foreign → EUR is amount / rate.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CSV = ROOT / "fx" / "eurofxref.csv"


@dataclass(frozen=True)
class FxTable:
    as_of: str
    # currency → units of that currency per 1 EUR
    rates: dict[str, float]
    path: Path

    def to_eur(self, amount: float | None, currency: str | None) -> Optional[float]:
        if amount is None:
            return None
        code = (currency or "").strip().upper()
        if not code:
            return None
        if code == "EUR":
            return float(amount)
        rate = self.rates.get(code)
        if rate is None or rate == 0:
            return None
        return float(amount) / rate

    def supported(self) -> list[str]:
        return sorted(["EUR", *self.rates.keys()])


@lru_cache(maxsize=4)
def load_fx(path: str | None = None) -> FxTable:
    csv_path = Path(path) if path else DEFAULT_CSV
    if not csv_path.exists():
        raise FileNotFoundError(f"FX file missing: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise ValueError("eurofxref.csv looks empty")

    header = [h.strip().upper() for h in rows[0]]
    data = [c.strip() for c in rows[1]]
    if header[0] != "DATE":
        raise ValueError("expected Date as first column in eurofxref.csv")

    as_of = data[0]
    rates: dict[str, float] = {}
    for name, raw in zip(header[1:], data[1:]):
        if not name or not raw:
            continue
        try:
            rates[name] = float(raw)
        except ValueError:
            continue
    return FxTable(as_of=as_of, rates=rates, path=csv_path)


def convert_docs_to_eur(
    docs: list[dict[str, Any]],
    *,
    amount_key: str = "gross_amount",
) -> dict[str, Any]:
    """Return EUR totals plus per-row conversion notes for the Overview."""
    fx = load_fx()
    converted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    by_currency_native: dict[str, float] = {}

    for d in docs:
        cur = (d.get("currency") or "").strip().upper() or "?"
        amt = d.get(amount_key)
        try:
            native = float(amt) if amt is not None else 0.0
        except (TypeError, ValueError):
            native = 0.0
        by_currency_native[cur] = by_currency_native.get(cur, 0.0) + native

        eur = fx.to_eur(native if amt is not None else None, cur if cur != "?" else None)
        row = {**d, "amount_native": native, "amount_eur": eur}
        if eur is None:
            skipped.append({"id": d.get("id"), "currency": cur, "amount": native})
        else:
            converted.append(row)

    def _sum_field(key: str) -> float:
        total = 0.0
        for d in docs:
            cur = (d.get("currency") or "").strip().upper()
            try:
                native = float(d.get(key) or 0)
            except (TypeError, ValueError):
                continue
            eur = fx.to_eur(native, cur)
            if eur is not None:
                total += eur
        return total

    return {
        "base": "EUR",
        "as_of": fx.as_of,
        "source": str(fx.path.relative_to(ROOT)) if fx.path.is_relative_to(ROOT) else str(fx.path),
        "disclaimer": (
            "FX rates are a static ECB euro reference snapshot for demo only — "
            f"not live market data (file dated {fx.as_of})."
        ),
        "gross_eur": sum(r["amount_eur"] or 0 for r in converted),
        "net_eur": _sum_field("net_amount"),
        "vat_eur": _sum_field("vat_amount"),
        "converted_rows": converted,
        "skipped": skipped,
        "native_by_currency": by_currency_native,
        "supported": fx.supported(),
    }
