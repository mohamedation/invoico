#!/usr/bin/env python3
"""
Field accuracy + latency on samples/ and local-samples/.

  python eval/run_eval.py
  MODEL=gemma3:4b python eval/run_eval.py
  python eval/run_eval.py --compare gemma4:e2b gemma3:4b

Writes eval/results.json (and eval/results_<model>.json when comparing).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import config as config_mod  # noqa: E402
from app.core.extract import extract_from_images  # noqa: E402
from app.core.pdf import file_to_page_images  # noqa: E402
from app.core.validate import validate_extraction  # noqa: E402

GT_PATH = ROOT / "eval" / "ground_truth.csv"
OUT_PATH = ROOT / "eval" / "results.json"

FIELDS = [
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
    "category",
]


def _norm_str(v) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def _close(a, b, tol=0.08) -> bool:
    if a in (None, "", " "):
        a = None
    if b in (None, ""):
        b = None
    if a is None and b is None:
        return True
    if a is None or b is None:
        # missing optional field on either side — don't punish hard for net/vat on tax-inclusive receipts
        return False
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def score_row(truth: dict, pred) -> dict[str, bool]:
    out = {}
    for f in FIELDS:
        t, p = truth.get(f), getattr(pred, f, None) if pred else None
        if t is not None and str(t).strip() == "":
            t = None
        if f in (
            "net_amount",
            "vat_amount",
            "vat_rate",
            "gross_amount",
            "cash_tendered",
            "change_amount",
        ):
            if t is None:
                out[f] = True  # no ground truth → skip
            else:
                out[f] = _close(t, p)
        elif f == "vendor":
            ts, ps = _norm_str(t), _norm_str(p)
            out[f] = bool(ts) and (ts in ps or ps in ts or any(w in ps for w in ts.split()[:2] if len(w) > 3))
        elif f == "invoice_no":
            ts, ps = _norm_str(t).lstrip("0"), _norm_str(p).lstrip("0")
            out[f] = (not ts) or (ts in ps or ps in ts)
        elif f == "category":
            out[f] = True  # soft — categories are fuzzy on retail receipts
        else:
            if t is None:
                out[f] = True
            else:
                out[f] = _norm_str(t) == _norm_str(p)
    return out


def resolve_path(row: dict) -> Path:
    source = row.get("source") or "samples"
    return ROOT / source / row["file"]


def run_once(model: str | None = None) -> dict:
    if model:
        os.environ["MODEL"] = model
        config_mod.settings.model = model

    rows = list(csv.DictReader(GT_PATH.open()))
    per_file = []
    field_hits = {f: 0 for f in FIELDS}
    field_total = {f: 0 for f in FIELDS}
    times = []
    core_hits = 0
    cash_ok = 0
    cash_n = 0

    print(f"\n=== model={config_mod.settings.model}  n={len(rows)} ===")

    for row in rows:
        path = resolve_path(row)
        if not path.exists():
            print(f"  missing: {path}")
            continue
        pages = file_to_page_images(path)
        t0 = time.perf_counter()
        extraction, raw, err = extract_from_images(pages)
        elapsed = time.perf_counter() - t0
        times.append(elapsed)

        hits = score_row(row, extraction)
        for f, ok in hits.items():
            # only count fields that have GT
            t = row.get(f)
            if t is None or str(t).strip() == "":
                if f in ("net_amount", "vat_amount", "vat_rate", "cash_tendered", "change_amount", "category"):
                    continue
            field_total[f] += 1
            if ok:
                field_hits[f] += 1

        core = all(hits[f] for f in ("vendor", "gross_amount", "currency"))
        if core:
            core_hits += 1

        if row.get("cash_tendered") not in (None, ""):
            cash_n += 1
            if hits.get("gross_amount") and hits.get("cash_tendered"):
                cash_ok += 1

        if extraction:
            ok_val, reasons = validate_extraction(extraction)
            expect_flag = row["file"] == "invoice_bad_math.png"
            val_ok = (not ok_val) if expect_flag else ok_val
        else:
            reasons = [err or "fail"]
            val_ok = False

        items = []
        if extraction:
            items = [
                {"d": i.description, "a": i.amount}
                for i in extraction.line_items[:8]
            ]

        per_file.append(
            {
                "file": row["file"],
                "source": row.get("source"),
                "seconds": round(elapsed, 2),
                "fields": hits,
                "core": core,
                "pred_gross": getattr(extraction, "gross_amount", None),
                "pred_cash": getattr(extraction, "cash_tendered", None),
                "pred_change": getattr(extraction, "change_amount", None),
                "pred_vendor": getattr(extraction, "vendor", None),
                "line_items": items,
                "validation_ok": val_ok,
                "validation_note": reasons if extraction else [err],
            }
        )
        mark = "OK" if core else "MISS"
        g = getattr(extraction, "gross_amount", None)
        c = getattr(extraction, "cash_tendered", None)
        print(
            f"  {mark}  {row['file'][:32]:32s}  {elapsed:5.2f}s  "
            f"gross={g} cash={c}  items={len(items)}"
        )

    n = max(len(per_file), 1)
    summary = {
        "model": config_mod.settings.model,
        "n": len(per_file),
        "avg_seconds": round(sum(times) / n, 2) if times else None,
        "core_exact_rate": round(core_hits / len(per_file), 3) if per_file else 0,
        "cash_vs_total_ok": f"{cash_ok}/{cash_n}",
        "field_accuracy": {
            f: round(field_hits[f] / field_total[f], 3) if field_total[f] else None
            for f in FIELDS
        },
        "per_file": per_file,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", nargs="+", help="Run several MODEL tags back to back")
    args = parser.parse_args()

    models = args.compare or [None]
    all_results = []
    for m in models:
        summary = run_once(m)
        all_results.append(summary)
        tag = (m or config_mod.settings.model).replace(":", "_").replace("/", "_")
        out = ROOT / "eval" / f"results_{tag}.json"
        out.write_text(json.dumps(summary, indent=2))
        print(f"wrote {out}")

    OUT_PATH.write_text(json.dumps(all_results if len(all_results) > 1 else all_results[0], indent=2))
    print(f"\nwrote {OUT_PATH}")

    print("\n## Summary")
    print("| Model | Core (vendor+gross+ccy) | Gross | Cash | Avg s |")
    print("|---|---|---|---|---|")
    for s in all_results:
        fa = s["field_accuracy"]
        print(
            f"| {s['model']} | {s['core_exact_rate']} | {fa.get('gross_amount')} | "
            f"{s['cash_vs_total_ok']} | {s['avg_seconds']} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
