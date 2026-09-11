from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FinancialYearCreate(BaseModel):
    year_name: str = Field(min_length=4, max_length=20)
    start_date: date
    end_date: date
    is_current: bool = False

    @model_validator(mode="after")
    def validate_dates(self):
        if self.start_date >= self.end_date:
            raise ValueError("start_date must be before end_date")
        return self


class FinancialYearResponse(FinancialYearCreate):
    id: int
    is_closed: bool
    model_config = ConfigDict(from_attributes=True)
