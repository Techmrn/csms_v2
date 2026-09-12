from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PettyPurchaseLineCreate(BaseModel):
    item_id: int | None = None
    temporary_item_name: str | None = Field(default=None, max_length=255)
    temporary_specification: str | None = None
    quantity: Decimal = Field(gt=0)
    unit_id: int
    unit_price: Decimal | None = Field(default=None, ge=0)
    immediate_issue_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    remarks: str | None = None

    @model_validator(mode="after")
    def validate_item_reference(self):
        if (self.item_id is None) == (self.temporary_item_name is None):
            raise ValueError("Provide either item_id or temporary_item_name, not both")
        if self.immediate_issue_quantity > self.quantity:
            raise ValueError("Immediate issue quantity cannot exceed purchase quantity")
        return self


class PettyPurchaseCreate(BaseModel):
    purchase_date: date
    financial_year_id: int
    store_id: int
    indent_id: int | None = None
    vendor_name: str | None = None
    reference_no: str | None = None
    invoice_no: str | None = None
    remarks: str | None = None
    actor_id: int
    lines: list[PettyPurchaseLineCreate] = Field(min_length=1)


class PettyPurchaseVerifyRequest(BaseModel):
    actor_id: int
    remarks: str | None = None


class PettyPurchasePostRequest(BaseModel):
    actor_id: int
    remarks: str | None = None


class PettyPurchaseLineResponse(BaseModel):
    id: int
    item_id: int
    temporary_item_name: str | None
    temporary_specification: str | None
    quantity: Decimal
    unit_id: int
    unit_price: Decimal | None
    immediate_issue_quantity: Decimal
    remarks: str | None
    model_config = ConfigDict(from_attributes=True)


class PettyPurchaseResponse(BaseModel):
    id: int
    petty_purchase_no: str
    purchase_date: date
    financial_year_id: int
    store_id: int
    indent_id: int | None
    vendor_name: str | None
    reference_no: str | None
    invoice_no: str | None
    status: str
    remarks: str | None
    verified_by: int | None
    verified_at: datetime | None
    posted_by: int | None
    posted_at: datetime | None
    posting_group_id: UUID | None
    lines: list[PettyPurchaseLineResponse]
    model_config = ConfigDict(from_attributes=True)
