from pydantic import BaseModel, ConfigDict, Field


class UnitCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    symbol: str | None = None
    decimal_allowed: bool = False


class UnitResponse(UnitCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)
