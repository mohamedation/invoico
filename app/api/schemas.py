from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

CATEGORIES = (
    "Software & Subscriptions",
    "Hardware & Equipment",
    "Office & Coworking",
    "Travel",
    "Meals & Entertainment",
    "Marketing",
    "Professional Services",
    "Telecom & Internet",
    "Education",
    "Other",
)

Category = Literal[
    "Software & Subscriptions",
    "Hardware & Equipment",
    "Office & Coworking",
    "Travel",
    "Meals & Entertainment",
    "Marketing",
    "Professional Services",
    "Telecom & Internet",
    "Education",
    "Other",
]

DocType = Literal["invoice", "receipt", "other"]
Status = Literal["auto_ok", "needs_review", "confirmed", "failed"]


class LineItem(BaseModel):
    description: Optional[str] = None
    qty: Optional[float] = 1.0
    amount: Optional[float] = Field(None, description="Line total, not unit price alone")


class Extraction(BaseModel):
    """What we ask the vision model to fill in from one page."""

    doc_type: DocType = "other"
    vendor: Optional[str] = Field(None, description="Seller / merchant name")
    invoice_no: Optional[str] = None
    issue_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    currency: Optional[str] = Field(None, description="ISO 4217, e.g. EUR or MYR")
    net_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[float] = Field(None, description="Percent, e.g. 19")
    gross_amount: Optional[float] = Field(
        None, description="Final total due — NEVER cash tendered"
    )
    cash_tendered: Optional[float] = Field(
        None, description="Cash the customer handed over (not the bill total)"
    )
    change_amount: Optional[float] = Field(None, description="Change returned")
    line_items: list[LineItem] = Field(default_factory=list)
    category: Category = "Other"


class DocumentUpdate(BaseModel):
    vendor: Optional[str] = None
    invoice_no: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    net_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[float] = None
    gross_amount: Optional[float] = None
    category: Optional[Category] = None
    doc_type: Optional[DocType] = None
    note: Optional[str] = None
    status: Optional[Status] = None
    confirm: bool = False


class DocumentOut(BaseModel):
    id: int
    file_path: str
    sha256: str
    doc_type: Optional[str] = None
    vendor: Optional[str] = None
    invoice_no: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: Optional[str] = None
    net_amount: Optional[float] = None
    vat_amount: Optional[float] = None
    vat_rate: Optional[float] = None
    gross_amount: Optional[float] = None
    category: Optional[str] = None
    status: str
    review_reason: Optional[str] = None
    note: Optional[str] = None
    model_used: Optional[str] = None
    raw_json: Optional[str] = None
    created_at: Optional[str] = None
    duplicate: bool = False


class HealthOut(BaseModel):
    ok: bool
    ollama: bool
    model: str
    detail: str = ""


class AnalyzeOut(BaseModel):
    ok: bool
    model: str
    analysis: str
    snapshot: dict[str, Any]


class ClearOut(BaseModel):
    deleted: int
