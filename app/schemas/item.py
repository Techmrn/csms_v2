from pydantic import BaseModel, ConfigDict, Field


class ItemCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=255)
    category_id: int
    unit_id: int
    specification: str | None = None
    remarks: str | None = None


class ItemResponse(ItemCreate):
    id: int
    is_active: bool
    is_temporary: bool
    model_config = ConfigDict(from_attributes=True)
