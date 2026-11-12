from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.paper_store.schemas.item import PaperItemRead


class PaperOpeningStockLineCreate(BaseModel):
    paper_item_id: int
    unit_id: int | None = None
    reams: int = Field(default=0, ge=0)
    sheets: int = Field(default=0, ge=0)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0)
    reel_count: int | None = None
    remarks: str | None = None


class PaperOpeningStockCreate(BaseModel):
    store_id: int
    financial_year_id: int
    opening_date: date
    remarks: str | None = None
    lines: list[PaperOpeningStockLineCreate] = Field(..., min_length=1)


class PaperOpeningStockLineRead(BaseModel):
    id: int
    paper_item_id: int
    unit_id: int
    total_sheets: int
    weight_kg: Decimal
    reel_count: int | None = None
    remarks: str | None = None
    paper_item: PaperItemRead | None = None

    model_config = ConfigDict(from_attributes=True)


class PaperOpeningStockRead(BaseModel):
    id: int
    opening_no: str
    opening_date: date
    financial_year_id: int
    store_id: int
    opening_type: str
    source_financial_year_id: int | None = None
    status: str
    remarks: str | None = None
    created_by: int | None = None
    posted_by: int | None = None
    posted_at: datetime | None = None
    lines: list[PaperOpeningStockLineRead] = []

    model_config = ConfigDict(from_attributes=True)

