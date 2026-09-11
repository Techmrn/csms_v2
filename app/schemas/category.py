from pydantic import BaseModel, ConfigDict, Field


class CategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=100)
    type: str
    description: str | None = None


class CategoryResponse(CategoryCreate):
    id: int
    is_active: bool
    model_config = ConfigDict(from_attributes=True)
