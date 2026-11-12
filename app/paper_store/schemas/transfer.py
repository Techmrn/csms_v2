from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.paper_store.schemas.item import PaperItemRead


class PaperTransferLineCreate(BaseModel):
    paper_item_id: int
    unit_id: int | None = None
    requested_reams: int = Field(default=0, ge=0)
    requested_sheets: int = Field(default=0, ge=0)
    requested_quantity: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal | None = Field(default=None, ge=0)
    remarks: str | None = None


class PaperTransferCreateRequest(BaseModel):
    source_store_id: int
    destination_store_id: int
    transfer_date: date
    financial_year_id: int | None = None
    transfer_mode: str = "PULL"
    remarks: str | None = None
    lines: list[PaperTransferLineCreate] = Field(..., min_length=1)


class PaperTransferDispatchLine(BaseModel):
    line_id: int
    dispatch_reams: int = Field(default=0, ge=0)
    dispatch_sheets: int = Field(default=0, ge=0)
    dispatch_quantity: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0)


class PaperTransferDispatchRequest(BaseModel):
    vehicle_no: str | None = None
    driver_name: str | None = None
    carrier_name: str | None = None
    gate_pass_no: str | None = None
    remarks: str | None = None
    lines: list[PaperTransferDispatchLine] = Field(..., min_length=1)


class PaperTransferReceiveLine(BaseModel):
    line_id: int
    received_reams: int = Field(default=0, ge=0)
    received_sheets: int = Field(default=0, ge=0)
    received_quantity: Decimal | None = Field(default=None, ge=0)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0)


class PaperTransferReceiveRequest(BaseModel):
    remarks: str | None = None
    lines: list[PaperTransferReceiveLine] = Field(..., min_length=1)


class PaperTransferLineRead(BaseModel):
    id: int
    paper_item_id: int
    unit_id: int
    requested_quantity: Decimal
    approved_quantity: Decimal | None = None
    dispatched_quantity: Decimal
    received_quantity: Decimal
    requested_sheets: int = 0
    approved_sheets: int | None = None
    dispatched_sheets: int = 0
    received_sheets: int = 0
    requested_weight_kg: Decimal = Decimal("0")
    dispatched_weight_kg: Decimal = Decimal("0")
    received_weight_kg: Decimal = Decimal("0")
    weight_kg: Decimal
    remarks: str | None = None
    paper_item: PaperItemRead | None = None

    model_config = ConfigDict(from_attributes=True)


class PaperTransferRead(BaseModel):
    id: int
    transfer_no: str
    transfer_date: date
    financial_year_id: int
    source_store_id: int
    destination_store_id: int
    transfer_mode: str
    status: str
    vehicle_no: str | None = None
    driver_name: str | None = None
    carrier_name: str | None = None
    gate_pass_no: str | None = None
    remarks: str | None = None
    rejection_reason: str | None = None
    created_by: int
    dispatched_at: datetime | None = None
    received_at: datetime | None = None
    lines: list[PaperTransferLineRead] = []

    model_config = ConfigDict(from_attributes=True)
