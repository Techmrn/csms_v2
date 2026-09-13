from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class TransferDispatchLine(BaseModel):
    requisition_line_id: int
    dispatch_quantity: Decimal = Field(ge=0)


class TransferDispatchRequest(BaseModel):
    transfer_date: date | None = None
    lines: list[TransferDispatchLine] = Field(min_length=1)
    remarks: str | None = None


class TransferReceiveLine(BaseModel):
    transfer_line_id: int
    received_quantity: Decimal = Field(ge=0)


class TransferReceiveRequest(BaseModel):
    receive_date: date
    lines: list[TransferReceiveLine] = Field(min_length=1)
    remarks: str | None = None


class TransferDiscrepancyResolutionRequest(BaseModel):
    resolution_type: str
    resolution: str = Field(min_length=1)


class TransferLineResponse(BaseModel):
    id: int
    requisition_line_id: int
    item_id: int
    unit_id: int
    quantity: Decimal
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class TransferResponse(BaseModel):
    id: int
    transfer_no: str
    transfer_date: date
    financial_year_id: int
    source_store_id: int
    destination_store_id: int
    requisition_id: int
    status: str
    dispatched_at: datetime | None
    received_at: datetime | None
    closed_at: datetime | None
    lines: list[TransferLineResponse]
    model_config = ConfigDict(from_attributes=True)


class TransferDiscrepancyResponse(BaseModel):
    id: int
    transfer_id: int
    transfer_line_id: int
    receive_date: date
    discrepancy_type: str
    discrepancy_quantity: Decimal
    status: str
    reason: str | None
    resolution: str | None
    resolved_at: datetime | None
    model_config = ConfigDict(from_attributes=True)
