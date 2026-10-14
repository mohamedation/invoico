"""Ask the local model to read spend stats and call out weird month-to-month stuff."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import ollama

from app.core.config import settings
from app.core.fx import convert_docs_to_eur, load_fx


def _client() -> ollama.Client:
    return ollama.Client(host=settings.ollama_host)


def build_spend_snapshot(docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll invoices into EUR (static ECB demo rates) for the model to reason over."""
    usable = [d for d in docs if d.get("status") in ("auto_ok", "needs_review", "confirmed")]
    fx_bundle = convert_docs_to_eur(usable)
    fx = load_fx()

    by_month: dict[str, float] = defaultdict(float)
    by_category: dict[str, float] = defaultdict(float)
    by_vendor: dict[str, float] = defaultdict(float)
    notes = []
    currencies: set[str] = set()
    skipped = 0

    for d in usable:
        cur = (d.get("currency") or "?").strip().upper()
        currencies.add(cur)
        native = float(d.get("gross_amount") or 0)
        eur = fx.to_eur(native, cur if cur != "?" else None)
        if eur is None:
            skipped += 1
            continue
        cat = d.get("category") or "Other"
        vendor = d.get("vendor") or "Unknown"
        by_category[cat] += eur
        by_vendor[vendor] += eur
        date = (d.get("issue_date") or "")[:7]
        if date:
            by_month[date] += eur
        note = d.get("note") or d.get("review_reason")
        if note:
            notes.append(
                {
                    "invoice_no": d.get("invoice_no"),
                    "vendor": vendor,
                    "note": note,
                    "gross_native": native,
                    "currency": cur,
                    "gross_eur": round(eur, 2),
                }
            )

    months = sorted(by_month.keys())
    month_deltas = []
    for i in range(1, len(months)):
        prev, cur_m = months[i - 1], months[i]
        a, b = by_month[prev], by_month[cur_m]
        pct = None if a == 0 else round((b - a) / a * 100, 1)
        month_deltas.append(
            {
                "from": prev,
                "to": cur_m,
                "prev_total_eur": round(a, 2),
                "curr_total_eur": round(b, 2),
                "change_pct": pct,
            }
        )

    return {
        "document_count": len(usable),
        "currencies": sorted(currencies),
        "fx": {
            "base": "EUR",
            "as_of": fx_bundle["as_of"],
            "source": fx_bundle["source"],
            "disclaimer": fx_bundle["disclaimer"],
            "skipped_rows": skipped,
            "native_by_currency": {
                k: round(v, 2) for k, v in fx_bundle["native_by_currency"].items()
            },
        },
        "totals": {
            "gross_eur": round(sum(by_category.values()), 2),
            "by_category_eur": {
                k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])
            },
            "by_vendor_eur": {
                k: round(v, 2) for k, v in sorted(by_vendor.items(), key=lambda x: -x[1])[:12]
            },
            "by_month_eur": {k: round(v, 2) for k, v in sorted(by_month.items())},
        },
        "month_over_month": month_deltas,
        "flagged_notes": notes[:20],
    }


ANALYZE_PROMPT = """You are a practical bookkeeping co-pilot for a freelancer.

Given the JSON spend snapshot below, write a short plain-language briefing:
1. What they spent the most on (categories / vendors) — amounts are already in EUR
2. Month-to-month changes that look interesting or worrying (spikes, drops, new vendors)
3. VAT / notes / mismatches worth a second look
4. 2–4 concrete recommendations (cut a subscription, ask vendor for credit note, etc.)

Be specific with numbers from the JSON. If data is thin, say so — do not invent invoices.
Mention once that EUR totals use a static ECB demo FX snapshot (see fx.disclaimer), not live rates.

Snapshot:
"""


def analyze_documents(docs: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = build_spend_snapshot(docs)
    if snapshot["document_count"] == 0:
        return {
            "ok": False,
            "model": settings.model,
            "snapshot": snapshot,
            "analysis": "No invoices to analyze yet. Upload and confirm a few first.",
        }

    client = _client()
    resp = client.chat(
        model=settings.model,
        messages=[
            {
                "role": "user",
                "content": ANALYZE_PROMPT + json.dumps(snapshot, indent=2),
            }
        ],
        think=False,
        options={"temperature": 0.2, "num_predict": 1200},
    )
    text = (resp.message.content or "").strip()
    if not text and getattr(resp.message, "thinking", None):
        text = str(resp.message.thinking).strip()
    return {
        "ok": bool(text),
        "model": settings.model,
        "snapshot": snapshot,
        "analysis": text or "Model returned an empty analysis. Try again or switch MODEL in .env.",
    }
