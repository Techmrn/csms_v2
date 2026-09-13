import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

class AssetLifecycleRequest(BaseModel):
    reason: str | None = None
    date: datetime.date | None = None

class AssetRepairReturnRequest(BaseModel):
    resolution: str | None = None
    date: datetime.date | None = None


class AssetDetailResponse(BaseModel):
    make: str | None = None
    model: str | None = None
    purchase_date: datetime.date | None = None
    purchase_reference: str | None = None
    purchase_value: Decimal | None = None
    warranty_expiry_date: datetime.date | None = None
    technical_specifications: str | None = None
    remarks: str | None = None
    model_config = ConfigDict(from_attributes=True)


class AssetMovementResponse(BaseModel):
    id: int
    movement_type: str
    from_store_id: int | None = None
    to_store_id: int | None = None
    from_office_id: int | None = None
    from_section_id: int | None = None
    to_office_id: int | None = None
    to_section_id: int | None = None
    reference_type: str | None = None
    reference_id: int | None = None
    reference_document: str | None = None
    movement_date: datetime.date
    remarks: str | None = None
    created_by: int
    created_at: datetime.datetime
    model_config = ConfigDict(from_attributes=True)


class AssetResponse(BaseModel):
    id: int
    asset_no: str
    item_id: int
    serial_no: str | None = None
    current_store_id: int | None = None
    current_office_id: int | None = None
    current_section_id: int | None = None
    status: str
    acquisition_financial_year_id: int | None = None
    remarks: str | None = None
    detail: AssetDetailResponse | None = None
    model_config = ConfigDict(from_attributes=True)
