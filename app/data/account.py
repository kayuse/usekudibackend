from datetime import datetime
import uuid
from pydantic import BaseModel, EmailStr, constr
from typing import Optional
from uuid import UUID
import os
from dotenv import load_dotenv

from app.data.mono import MonoAccountLinkData
from app.data.user import UserOut

load_dotenv(override=True)


class AccountCreate(BaseModel):
    account_name: str
    account_number: str
    bank_id: int
    account_type: str
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
    bank_account_type: Optional[str] = None  # Type of bank account
    institution_id: Optional[str] = None  # Unique identifier for the bank
    bank_code: Optional[str] = None  # Unique code for the bank
    image_url: Optional[str] = None  # URL to the bank's logo or image

    class Config:
        from_attributes = True


class BankCreate(BaseModel):
    bank_name: str
    bank_code: str

class BankCreateMultiple(BaseModel):
    bankName:str
    bankCode:str

class CategoryOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class TransactionSearch(BaseModel):
    start_date: datetime  # ISO format date string
    end_date: datetime  # ISO format date string
    account_id: Optional[int] = None  # Optional account ID to filter transactions
    text: Optional[str] = None  # Optional text to search in transaction descriptions
    category_id: Optional[int] = None  # Optional category ID to filter transactions
    skip: int = 0  # Number of records to skip (for pagination)
    limit: int = 200  # Maximum number of records to return (for pagination)


class AccountLinkData(BaseModel):
    customer_id: Optional[str] = None  # Optional customer ID for linking
    customer_email: EmailStr
    account_id: int
    customer_name: str
    scope: Optional[str] = "auth"
    institution_id: str
    institution_auth_method: Optional[str] = "internet_banking"
    meta_ref: Optional[str] = str(uuid.uuid4().hex)
    redirect_url: Optional[str] = os.getenv('REDIRECT_URL', 'https://003f03833122.ngrok-free.app/complete')


class AccountCreateOut(BaseModel):
    id: int
    account_name: str
    account_number: str
    account_id: Optional[str] = None  # Mono account ID
    active: bool
    current_balance: float
    currency: str
    bank_id: int
    bank: BankOut = None
    account_type: str = None
    link_account_response: Optional[MonoAccountLinkData] = None  # Response from linking account

    class Config:
        from_attributes = True


class AccountOut(BaseModel):
    id: int
    account_name: str
    account_number: str
    account_id: Optional[str] = None  # Mono account ID
    active: bool
    current_balance: float
    currency: str
    bank_id: int
    bank: Optional[BankOut] = None
    account_type: Optional[str] = None


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
    category: Optional[CategoryOut] = None  # Optional category object
    account: AccountOut = None

    class Config:
        from_attributes = True


class AccountDetailsOut(BaseModel):
    account_name: str
    account_number: str
    current_balance: float
    currency: str
    active: bool
    bank_id: int
    bank: Optional[BankOut] = None

    class Config:
        from_attributes = True


class TransactionCategoryOut(BaseModel):
    category_id: int
    category_name: str
    category_icon: Optional[str] = None
    amount: float


class TransactionWeekCategoryOut(BaseModel):
    week_starting: str
    week_ending: str
    categories: list[TransactionCategoryOut]


class WeeklyTrend(BaseModel):
    income_trend : list[TransactionWeekCategoryOut]
    expense_trend : list[TransactionWeekCategoryOut]


class TransactionAverage(BaseModel):
    average_in: float
    average_out: float


class BudgetOut(BaseModel):
    id: int
    user_id: int
    user: Optional[UserOut] = None
    amount: float
    category_id: Optional[int] = None
    category: Optional[CategoryOut] = None

    class Config:
        orm_mode = True
        from_attributes = True


class BudgetCreate(BaseModel):
    name: str
    category_id: int
    amount: float


class BudgetInsightOut(BaseModel):
    budget_name: str
    planned_amount: float
    actual_amount: float
    variance: float
