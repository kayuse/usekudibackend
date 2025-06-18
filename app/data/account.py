from datetime import datetime
from pydantic import BaseModel, EmailStr, constr
from typing import Optional
from uuid import UUID

class AccountCreate(BaseModel):
    account_name: str
    account_number: str
    bank_id: int
    account_type: str
    balance: float
    fetch_method: str
    currency: str

class AccountExchangeCreate(BaseModel):
    account_id: int
    exchange_code: str

class AccountExchangeOut(BaseModel):
    id: int
    account_id: str
    

class MonoAccountResponseData(BaseModel):
    id: str

class MonoAuthResponse(BaseModel):
    status: str
    message: str
    timestamp: datetime
    data: MonoAccountResponseData

class AccountOut(BaseModel):
    id: int
    account_name: str
    account_number: str
    account_id: Optional[str] = None  # Mono account ID
    active: bool
    class Config:
        from_attributes = True

class BankOut(BaseModel):
    bank_id: int
    bank_name: str
    image_url: Optional[str] = None  # URL to the bank's logo or image

    class Config:
        from_attributes = True

class BankCreate(BaseModel):
    bank_name: str
    bank_code: str