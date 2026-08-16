from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional

class PartnerCreateSchema(BaseModel):
    name: str = Field(..., example='ООО "Партнёр-Софт"')
    webhook_url: HttpUrl = Field(..., example="https://b24-07hfop.bitrix24.ru/rest/1/dfssbu7jskxkf1rx/")

class EmployeeSchema(BaseModel):
    external_bitrix_id: int
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    second_name: Optional[str] = None
    phone: Optional[str] = None
    position: Optional[str] = None
    departments: List[int] = []
    is_active: bool = True

class PartnerResponseSchema(BaseModel):
    id: int
    name: str
    webhook_url: str
    employees_count: int
    employees: List[EmployeeSchema]