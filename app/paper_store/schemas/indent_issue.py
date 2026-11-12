from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.paper_store.schemas.item import PaperItemRead


class PaperIndentLineCreate(BaseModel):
    paper_item_id: int
    unit_id: int | None = None
    # Explicit Ream + Sheet fields for SHEET items
    requested_reams: int = Field(default=0, ge=0)
    requested_sheets: int = Field(default=0, ge=0)
    issued_reams: int | None = Field(default=None, ge=0)
    issued_sheets: int | None = Field(default=None, ge=0)
    # Optional fallback / weight fields
    requested_quantity: Decimal | None = Field(default=None, ge=0)
    issued_quantity: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    remarks: str | None = None


class PaperManualIndentCreate(BaseModel):
    store_id: int
    section_id: int
    indent_date: date
    financial_year_id: int | None = None
    job_no: str | None = None
    remarks: str | None = None
    lines: list[PaperIndentLineCreate] = Field(..., min_length=1)


class PaperOnlineIndentCreate(BaseModel):
    store_id: int
    section_id: int | None = None
    indent_date: date
    financial_year_id: int | None = None
    job_no: str | None = None
    remarks: str | None = None
    lines: list[PaperIndentLineCreate] = Field(..., min_length=1)


class PaperOnlineIndentIssueLine(BaseModel):
    indent_line_id: int
    issued_reams: int = Field(default=0, ge=0)
    issued_sheets: int = Field(default=0, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    remarks: str | None = None


class PaperOnlineIndentIssueRequest(BaseModel):
    issue_date: date | None = None
    remarks: str | None = None
    lines: list[PaperOnlineIndentIssueLine] = Field(..., min_length=1)


class PaperIndentLineRead(BaseModel):
    id: int
    paper_item_id: int
    unit_id: int
    requested_quantity: Decimal
    approved_quantity: Decimal | None = None
    issued_quantity: Decimal | None = None
    requested_sheets: int = 0
    approved_sheets: int | None = None
    issued_sheets: int | None = None
    requested_weight_kg: Decimal = Decimal("0")
    approved_weight_kg: Decimal | None = None
    issued_weight_kg: Decimal | None = None
    remarks: str | None = None
    paper_item: PaperItemRead | None = None

    model_config = ConfigDict(from_attributes=True)


class PaperIndentRead(BaseModel):
    id: int
    indent_no: str
    indent_date: date
    financial_year_id: int
    store_id: int
    section_id: int
    job_no: str | None = None
    request_source: str
    status: str
    remarks: str | None = None
    created_by: int | None = None
    lines: list[PaperIndentLineRead] = []

    model_config = ConfigDict(from_attributes=True)


class PaperIssueLineRead(BaseModel):
    id: int
    paper_item_id: int
    unit_id: int
    quantity: Decimal
    sheets: int = 0
    weight_kg: Decimal
    remarks: str | None = None
    paper_item: PaperItemRead | None = None

    model_config = ConfigDict(from_attributes=True)


class PaperIssueRead(BaseModel):
    id: int
    issue_no: str
    issue_date: date
    financial_year_id: int
    indent_id: int
    store_id: int
    section_id: int
    job_no: str | None = None
    status: str
    remarks: str | None = None
    created_by: int | None = None
    posted_by: int | None = None
    posted_at: datetime | None = None
    lines: list[PaperIssueLineRead] = []

    model_config = ConfigDict(from_attributes=True)
