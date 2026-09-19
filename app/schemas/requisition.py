from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class RequisitionLineCreate(BaseModel):
    item_id: int
    requested_quantity: Decimal = Field(gt=0)
    remarks: str | None = None


class RequisitionCreate(BaseModel):
    requisition_date: date
    financial_year_id: int
    requesting_office_id: int
    requesting_store_id: int
    reference_no: str | None = None
    remarks: str | None = None
    lines: list[RequisitionLineCreate] = Field(min_length=1)


class RequisitionApprovalLine(BaseModel):
    requisition_line_id: int
    approved_quantity: Decimal = Field(ge=0)


class BranchApprovalLine(BaseModel):
    requisition_line_id: int
    requested_quantity: Decimal = Field(gt=0)


class BranchApprovalRequest(BaseModel):
    remarks: str | None = None
    lines: list[BranchApprovalLine] | None = None


class CentralApprovalRequest(BaseModel):
    lines: list[RequisitionApprovalLine] = Field(min_length=1)
    remarks: str | None = None


class RequisitionLineResponse(BaseModel):
    id: int
    item_id: int
    requested_quantity: Decimal
    approved_quantity: Decimal | None
    dispatched_quantity: Decimal
    received_quantity: Decimal
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class RequisitionResponse(BaseModel):
    id: int
    requisition_no: str
    requisition_date: date
    financial_year_id: int
    requesting_office_id: int
    requesting_store_id: int
    status: str
    reference_no: str | None
    remarks: str | None
    branch_approved_at: datetime | None
    central_approved_at: datetime | None
    closed_at: datetime | None
    lines: list[RequisitionLineResponse]
    model_config = ConfigDict(from_attributes=True)
