from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class TransferCreateLine(BaseModel):
    item_id: int
    unit_id: int
    requested_quantity: Decimal = Field(gt=0)
    remarks: str | None = None


class TransferCreateRequest(BaseModel):
    transfer_date: date | None = None
    source_store_id: int
    destination_store_id: int
    transfer_mode: str = "PULL"  # "PULL" (branch request) or "PUSH" (directorate directive)
    remarks: str | None = None
    lines: list[TransferCreateLine] = Field(min_length=1)


class TransferApprovalLine(BaseModel):
    line_id: int
    approved_quantity: Decimal = Field(ge=0)


class TransferApproveBranchRequest(BaseModel):
    remarks: str | None = None
    lines: list[TransferApprovalLine] | None = None


class TransferApproveDirectorateRequest(BaseModel):
    remarks: str | None = None
    lines: list[TransferApprovalLine] | None = None


class TransferAuthorizeSupplyRequest(BaseModel):
    remarks: str | None = None
    lines: list[TransferApprovalLine] | None = None


class TransferRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class TransferDispatchLine(BaseModel):
    transfer_line_id: int | None = None
    requisition_line_id: int | None = None
    dispatch_quantity: Decimal = Field(ge=0)
    asset_ids: list[int] | None = None


class TransferDispatchRequest(BaseModel):
    transfer_date: date | None = None
    lines: list[TransferDispatchLine] = Field(min_length=1)
    remarks: str | None = None
    vehicle_no: str | None = None
    received_by_name: str | None = None


class TransferGatePassUpdateRequest(BaseModel):
    vehicle_no: str | None = None
    received_by_name: str | None = None


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
    requisition_line_id: int | None = None
    item_id: int
    unit_id: int
    requested_quantity: Decimal
    approved_quantity: Decimal | None = None
    quantity: Decimal
    received_quantity: Decimal
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class TransferResponse(BaseModel):
    id: int
    transfer_no: str
    transfer_date: date
    financial_year_id: int
    source_store_id: int
    destination_store_id: int
    requisition_id: int | None = None
    transfer_mode: str = "PULL"
    status: str
    remarks: str | None = None
    vehicle_no: str | None = None
    received_by_name: str | None = None
    created_by: int | None = None
    branch_approved_at: datetime | None = None
    directorate_approved_at: datetime | None = None
    supply_authorized_at: datetime | None = None
    dispatched_at: datetime | None = None
    received_at: datetime | None = None
    closed_at: datetime | None = None
    rejection_reason: str | None = None
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
