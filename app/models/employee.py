from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class EmployeeRecord(BaseModel):
    employee_id: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    last_name: str | None = None
    email: EmailStr
    joining_date: str | None = None
    department: str | None = None
    city: str | None = None
