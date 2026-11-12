from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field

from app.paper_store.schemas.item import PaperItemRead


class PaperReceiptLineCreate(BaseModel):
    paper_item_id: int
    unit_id: int | None = None
    # Explicit Ream + Sheet fields for SHEET items
    challan_reams: int = Field(default=0, ge=0)
    challan_sheets: int = Field(default=0, ge=0)
    received_reams: int = Field(default=0, ge=0)
    received_sheets: int = Field(default=0, ge=0)
    accepted_reams: int = Field(default=0, ge=0)
    accepted_sheets: int = Field(default=0, ge=0)
    damaged_reams: int = Field(default=0, ge=0)
    damaged_sheets: int = Field(default=0, ge=0)
    # Optional fallback quantity fields (reams or kg)
    challan_quantity: Decimal | None = Field(default=None, ge=0)
    received_quantity: Decimal | None = Field(default=None, ge=0)
    accepted_quantity: Decimal | None = Field(default=None, ge=0)
    damaged_quantity: Decimal | None = Field(default=None, ge=0)
    # Primary weight field for REEL items (or theoretical weight for SHEET)
    weight_kg: Decimal = Field(default=Decimal("0"), ge=0)
    reel_count: int | None = None
    reel_numbers: str | None = None
    remarks: str | None = None


class PaperReceiptCreate(BaseModel):
    store_id: int
    receipt_date: date
    financial_year_id: int | None = None
    source_depot: str = Field(..., min_length=2, max_length=255)
    allotment_no: str | None = None
    allotment_date: date | None = None
    challan_no: str | None = None
    challan_date: date | None = None
    vehicle_no: str | None = None
    carrier_name: str | None = None
    lorry_receipt_no: str | None = None
    remarks: str | None = None
    lines: list[PaperReceiptLineCreate] = Field(..., min_length=1)


class PaperReceiptLineRead(BaseModel):
    id: int
    paper_item_id: int
    unit_id: int
    challan_quantity: Decimal
    received_quantity: Decimal
    accepted_quantity: Decimal
    damaged_quantity: Decimal
    challan_sheets: int = 0
    received_sheets: int = 0
    accepted_sheets: int = 0
    damaged_sheets: int = 0
    weight_kg: Decimal
    reel_count: int | None = None
    reel_numbers: str | None = None
    remarks: str | None = None
    paper_item: PaperItemRead | None = None

    model_config = ConfigDict(from_attributes=True)


class PaperReceiptRead(BaseModel):
    id: int
    receipt_no: str
    receipt_date: date
    financial_year_id: int
    store_id: int
    source_depot: str
    allotment_no: str | None = None
    allotment_date: date | None = None
    challan_no: str | None = None
    challan_date: date | None = None
    vehicle_no: str | None = None
    carrier_name: str | None = None
    lorry_receipt_no: str | None = None
    status: str
    remarks: str | None = None
    created_by: int | None = None
    posted_by: int | None = None
    lines: list[PaperReceiptLineRead] = []

    model_config = ConfigDict(from_attributes=True)
