from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class OpeningAssetInput(BaseModel):
    asset_no: str = Field(min_length=1, max_length=50)
    serial_no: str | None = None
    make: str | None = None
    model: str | None = None
    purchase_date: date | None = None
    purchase_reference: str | None = None
    purchase_value: Decimal | None = Field(default=None, ge=0)
    warranty_expiry_date: date | None = None
    technical_specifications: str | None = None
    remarks: str | None = None


class OpeningStockLineCreate(BaseModel):
    item_id: int
    quantity: Decimal = Field(gt=0)
    unit_id: int
    asset_details: list[OpeningAssetInput] | None = None
    remarks: str | None = None


class OpeningStockCreate(BaseModel):
    opening_date: date
    financial_year_id: int
    store_id: int
    remarks: str | None = None
    lines: list[OpeningStockLineCreate] = Field(min_length=1)


class OpeningStockResponse(BaseModel):
    id: int
    opening_no: str
    opening_date: date
    financial_year_id: int
    store_id: int
    status: str

    model_config = {"from_attributes": True}


class StockBalanceResponse(BaseModel):
    store_id: int
    financial_year_id: int
    item_id: int
    item_code: str
    item_name: str
    unit_code: str
    balance: Decimal


class StockRegisterRow(BaseModel):
    id: int
    movement_date: date
    movement_type: str
    quantity_in: Decimal
    quantity_out: Decimal
    balance: Decimal
    reference_type: str
    reference_id: int
    reference_no: str | None
