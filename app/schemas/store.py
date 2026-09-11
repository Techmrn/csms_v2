from pydantic import BaseModel, ConfigDict, Field


class StoreCreate(BaseModel):
    office_id: int
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    store_type: str
    is_primary: bool = True
    remarks: str | None = None


class StoreResponse(StoreCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)
