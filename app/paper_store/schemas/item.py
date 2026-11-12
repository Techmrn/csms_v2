from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class PaperItemBase(BaseModel):
    code: str
    name: str
    paper_type: str
    form_type: str
    gsm: int
    sheets_per_ream: int = 500
    length_cm: Decimal | None = None
    width_cm: Decimal | None = None
    reel_width_cm: Decimal | None = None
    unit_id: int
    weight_per_ream_kg: Decimal | None = None
    remarks: str | None = None
    is_active: bool = True


class PaperItemCreate(PaperItemBase):
    pass


class PaperItemRead(PaperItemBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

