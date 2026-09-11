from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StockReturnLineCreate(BaseModel):
    original_issue_line_id: int
    quantity: Decimal = Field(gt=0)
    remarks: str | None = None


class StockReturnCreate(BaseModel):
    return_date: date
    financial_year_id: int
    store_id: int
    original_issue_id: int
    returning_office_id: int | None = None
    returning_section_id: int | None = None
    reason: str = Field(min_length=1)
    remarks: str | None = None
    lines: list[StockReturnLineCreate] = Field(min_length=1)


class StockReturnLineResponse(BaseModel):
    id: int
    original_issue_line_id: int
    item_id: int
    quantity: Decimal
    unit_id: int
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class StockReturnResponse(BaseModel):
    id: int
    return_no: str
    return_date: date
    financial_year_id: int
    store_id: int
    original_issue_id: int
    returning_office_id: int | None
    returning_section_id: int | None
    status: str
    reason: str
    verified_at: datetime | None = None
    posted_at: datetime | None = None
    posting_group_id: UUID | None
    lines: list[StockReturnLineResponse]
    model_config = ConfigDict(from_attributes=True)
