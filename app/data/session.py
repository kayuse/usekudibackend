from typing import Optional, List

from pydantic import BaseModel, Field

from app.data.account import BankOut
from app.models.session import SessionTransaction, SessionAccount


class SessionCreate(BaseModel):
    email: str


class SessionOut(BaseModel):
    id: int
    name: str
    identifier: str
    email: str
    customer_type: Optional[str]
    model_config = {
        "from_attributes": True
    }


class SessionAccountOut(BaseModel):
    id: int
    account_name: str
    bank_id: int
    account_number: str
    session_id: int
    model_config = {
        "from_attributes": True
    }


class SessionUpload(BaseModel):
    email: str
    model_config = {
        "from_attributes": True
    }


class AccountExchangeSessionCreate(BaseModel):
    session_id: str
    exchange_codes: List[str]


class Transaction(BaseModel):
    transactionDate: str = Field(...,
                                 description="Date in YYYY-MM-DD h:i:s format use 12am as default time if time not found")
    transactionId: Optional[str] = Field(None, description="Transaction reference/ID if present")
    description: str = Field(..., description="Transaction Description or Details if present")
    transactionType: str = Field(...,
                                 description="Transaction Type it's either Debit or Credit. You can use the Amount Field to determine the type of transaction")
    amount: float = Field(...,
                          description="Transaction amount, It could also be in different columns as Withdrawal and Deposit")
    balance: Optional[float] = Field(None, description="Balance after the transaction")


class Statement(BaseModel):
    accountName: Optional[str] = Field(None, description="Name of account holder")
    accountNumber: Optional[str] = Field(None, description="Bank account number")
    accountBalance: Optional[float] = Field(None, description="The Account Balance of the Statement Generated")
    accountCurrency: Optional[str] = Field(None, description="Currency code of the Statement Generated")
    bank: Optional[str] = Field(None, description="Bank name")
    transactions: List[Transaction] = Field(..., description="List of transactions")


class BankData(BaseModel):
    bank_name: Optional[str] = Field(..., description="Bank Name")
    bank_id: int = Field(..., description="Bank ID")


class IncomeFlowOut(BaseModel):
    inflow: float
    outflow: float
    closing_balance: float
    net_income: float

class TransactionDataOut(BaseModel):
    transactions : list[type[SessionTransaction]]
    accounts : list[type[SessionAccount]]

class RiskOut(BaseModel):
    liquidity_risk: float
    concentration_risk: float
    expense_risk: float
    volatility_risk: float
    compliance_risk: Optional[int]

class IncomeCategoryOut(BaseModel):
    category_name: str
    category_id: int
    amount: float

class SpendingProfileOut(BaseModel):
    spending_ratio : float
    savings_ratio : float
    budget_conscious:float

class FinancialProfileDataIn(BaseModel):
    session : SessionOut
    income_flow: IncomeFlowOut
    risk: RiskOut
    income_categories: list[IncomeCategoryOut]
    spending_profile: SpendingProfileOut
    transactions: List[TransactionDataOut]
