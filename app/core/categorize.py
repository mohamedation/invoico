"""Pick a category — remembered vendor rules win over the model guess."""

from __future__ import annotations

import re

from app.api.schemas import CATEGORIES
from app.core import db


def normalize_vendor(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    return cleaned or None


def resolve_category(vendor: str | None, model_category: str | None) -> str:
    key = normalize_vendor(vendor)
    if key:
        learned = db.get_vendor_category(key)
        if learned:
            return learned

    if model_category in CATEGORIES:
        return model_category
    return "Other"


def remember_vendor_category(vendor: str | None, category: str) -> None:
    key = normalize_vendor(vendor)
    if key and category in CATEGORIES:
        db.upsert_vendor_rule(key, category)
