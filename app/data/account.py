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
    
class BankOut(BaseModel):
    bank_id: int
    bank_name: str
    image_url: Optional[str] = None  # URL to the bank's logo or image

    class Config:
        from_attributes = True
        
class AccountOut(BaseModel):
    id: int
    account_name: str
    account_number: str
    account_id: str = None  # Mono account ID
    active: bool
    current_balance: float
    currency: str
    bank_id: int
    bank: BankOut = None
    account_type: str = None
    class Config:
        from_attributes = True



class BankCreate(BaseModel):
    bank_name: str
    bank_code: str


class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True
        
class TransactionOut(BaseModel):
    id: int
    account_id: int
    transaction_id: str  # Mono transaction ID
    currency: str
    date: str  # ISO format date string
    amount: float
    transaction_type: str  # e.g., 'credit', 'debit'
    description: Optional[str] = None
    category_id: Optional[int] = None  # Optional category ID for the transaction
    category : CategoryOut = None  # Optional category object
    
    class Config:
        from_attributes = True