from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class EmployeeRecord(BaseModel):
    employee_id: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    last_name: Optional[str] = None
    email: EmailStr
    joining_date: Optional[str] = None
    department: Optional[str] = None
    city: Optional[str] = None
