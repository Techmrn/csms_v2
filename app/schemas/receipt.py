from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReceiptLineCreate(BaseModel):
    item_id: int
    received_quantity: Decimal = Field(gt=0)
    accepted_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    rejected_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    unit_id: int
    unit_price: Decimal | None = Field(default=None, ge=0)
    remarks: str | None = None


class ReceiptCreate(BaseModel):
    receipt_date: date
    financial_year_id: int
    store_id: int
    source_type: str = "EXTERNAL"
    supplier_name: str | None = None
    purchase_reference: str | None = None
    invoice_reference: str | None = None
    challan_reference: str | None = None
    remarks: str | None = None
    lines: list[ReceiptLineCreate] = Field(min_length=1)


class ReceiptLineResponse(BaseModel):
    id: int
    item_id: int
    received_quantity: Decimal
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    unit_id: int
    unit_price: Decimal | None
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class ReceiptResponse(BaseModel):
    id: int
    receipt_no: str
    receipt_date: date
    financial_year_id: int
    store_id: int
    source_type: str
    supplier_name: str | None
    purchase_reference: str | None
    invoice_reference: str | None
    challan_reference: str | None
    status: str
    verified_at: datetime | None = None
    posted_at: datetime | None = None
    posting_group_id: UUID | None
    lines: list[ReceiptLineResponse]
    model_config = ConfigDict(from_attributes=True)
