from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StockVerificationLineCreate(BaseModel):
    item_id: int
    physical_quantity: Decimal = Field(ge=0)
    remarks: str | None = None


class StockVerificationCreate(BaseModel):
    verification_date: date
    financial_year_id: int
    store_id: int
    remarks: str | None = None
    lines: list[StockVerificationLineCreate] = Field(min_length=1)


class StockVerificationAuthorizeRequest(BaseModel):
    remarks: str | None = None


class StockVerificationLineResponse(BaseModel):
    id: int
    item_id: int
    system_quantity: Decimal
    physical_quantity: Decimal
    variance_quantity: Decimal
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class StockVerificationResponse(BaseModel):
    id: int
    verification_no: str
    verification_date: date
    financial_year_id: int
    store_id: int
    status: str
    remarks: str | None
    created_by: int
    counted_by: int | None
    counted_at: datetime | None
    authorized_by: int | None
    authorized_at: datetime | None
    closed_by: int | None
    closed_at: datetime | None
    lines: list[StockVerificationLineResponse]
    model_config = ConfigDict(from_attributes=True)


class AdjustmentCreateFromVerificationRequest(BaseModel):
    verification_id: int
    adjustment_type: str
    reason: str
    remarks: str | None = None


class AdjustmentAuthorizeRequest(BaseModel):
    remarks: str | None = None


class AdjustmentPostRequest(BaseModel):
    remarks: str | None = None


class AdjustmentLineResponse(BaseModel):
    id: int
    item_id: int
    quantity: Decimal
    unit_id: int
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class AdjustmentResponse(BaseModel):
    id: int
    adjustment_no: str
    adjustment_date: date
    financial_year_id: int
    store_id: int
    verification_id: int
    adjustment_type: str
    reason: str
    reference_no: str | None
    status: str
    remarks: str | None
    created_by: int
    authorized_by: int | None
    authorized_at: datetime | None
    posted_by: int | None
    posted_at: datetime | None
    posting_group_id: UUID | None
    lines: list[AdjustmentLineResponse]
    model_config = ConfigDict(from_attributes=True)


class UnserviceableLineCreate(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0)
    unit_id: int
    reason: str | None = None
    remarks: str | None = None


class UnserviceableCreate(BaseModel):
    date: date
    financial_year_id: int
    store_id: int
    reason: str
    remarks: str | None = None
    lines: list[UnserviceableLineCreate] = Field(min_length=1)


class UnserviceableActionRequest(BaseModel):
    remarks: str | None = None


class UnserviceableLineResponse(BaseModel):
    id: int
    item_id: int
    quantity: Decimal
    unit_id: int
    reason: str | None
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class UnserviceableResponse(BaseModel):
    id: int
    reference_no: str
    date: date
    financial_year_id: int
    store_id: int
    status: str
    reason: str
    remarks: str | None
    reported_by: int
    verified_by: int | None
    verified_at: datetime | None
    authorized_by: int | None
    authorized_at: datetime | None
    posted_by: int | None
    posted_at: datetime | None
    posting_group_id: UUID | None
    lines: list[UnserviceableLineResponse]
    model_config = ConfigDict(from_attributes=True)
