from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class IndentLineCreate(BaseModel):
    item_id: int
    requested_quantity: Decimal = Field(gt=0)
    remarks: str | None = None


class IndentCreate(BaseModel):
    indent_date: date
    financial_year_id: int
    store_id: int
    office_id: int
    section_id: int | None = None
    request_source: str = "PHYSICAL"
    request_type: str | None = None
    reference_no: str | None = None
    reference_date: date | None = None
    remarks: str | None = None
    lines: list[IndentLineCreate] = Field(min_length=1)


class IndentLineResponse(BaseModel):
    id: int
    item_id: int
    requested_quantity: Decimal
    issued_quantity: Decimal | None
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class IndentResponse(BaseModel):
    id: int
    indent_no: str
    indent_date: date
    financial_year_id: int
    store_id: int
    office_id: int
    section_id: int | None
    request_source: str
    status: str
    remarks: str | None
    lines: list[IndentLineResponse]
    model_config = ConfigDict(from_attributes=True)


class IssueFinalizeLine(BaseModel):
    indent_line_id: int
    issued_quantity: Decimal = Field(ge=0)
    remarks: str | None = None


class IssueFinalizeRequest(BaseModel):
    issue_date: date | None = None
    remarks: str | None = None
    lines: list[IssueFinalizeLine] = Field(min_length=1)


class IssueLineResponse(BaseModel):
    id: int
    item_id: int
    unit_id: int
    quantity: Decimal
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class IssueResponse(BaseModel):
    id: int
    issue_no: str
    issue_date: date
    financial_year_id: int
    indent_id: int
    source_store_id: int
    destination_office_id: int
    destination_section_id: int | None
    status: str
    posting_group_id: UUID | None
    lines: list[IssueLineResponse]
    model_config = ConfigDict(from_attributes=True)
