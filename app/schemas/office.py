from pydantic import BaseModel, ConfigDict, Field


class OfficeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    office_type: str
    parent_office_id: int | None = None
    display_order: int | None = None
    remarks: str | None = None


class OfficeResponse(OfficeCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)
