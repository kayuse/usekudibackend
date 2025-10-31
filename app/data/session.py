from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field

from app.data.account import BankOut, TransactionCategoryOut, CategoryOut
from app.models.session import SessionTransaction, SessionAccount


class SessionCreate(BaseModel):
    email: str
    customer_type: str
    name: str


class SessionOut(BaseModel):
    id: int
    name: str
    identifier: str
    email: str
    currency_code : Optional[str]
    customer_type: Optional[str]
    processing_status: str
    paid: Optional[bool]
    overall_assessment: Optional[str] = None
    overall_assessment_title: Optional[str] = None
    model_config = {
        "from_attributes": True
    }


class SessionInsightOut(BaseModel):
    title: str
    priority: str
    insight_type: str
    insight: str
    session_id: int
    model_config = {
        "from_attributes": True
    }


class SessionSwotOut(BaseModel):
    analysis: str
    swot_type: str
    session_id: int
    model_config = {
        "from_attributes": True
    }


class SessionAccountOut(BaseModel):
    id: int
    account_name: str
    bank_id: Optional[int]
    account_number: str
    session_id: int
    current_balance: float
    currency: Optional[str]
    indexed: bool
    model_config = {
        "from_attributes": True
    }


class SessionTransactionOut(BaseModel):
    id: int
    amount: float
    account_id: int
    category_id: Optional[int] = None
    session_account: SessionAccountOut
    category: Optional[CategoryOut] = None
    transaction_id: str
    date: datetime
    transaction_type: str
    description: str
    currency: Optional[str]

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
    transactionDate: Optional[datetime] = Field(...,
                                                description="Date in YYYY-MM-DD h:i:s format use 12am as default time if time not found")
    transactionId: Optional[str] = Field(None, description="Transaction reference/ID if present")
    description: Optional[str] = Field(..., description="Transaction Description or Details if present")
    transactionType: Optional[str] = Field(...,
                                           description="Transaction Type it's either Debit or Credit. You can use the Amount Field to determine the type of transaction")
    amount: Optional[float] = Field(...,
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


class SessionStatusOut(BaseModel):
    session_id: str
    status: str


class TransactionDataOut(BaseModel):
    transactions: list[SessionTransactionOut]
    accounts: list[SessionAccountOut]


class RiskOut(BaseModel):
    liquidity_risk: float
    concentration_risk: float
    expense_risk: float
    volatility_risk: float
    compliance_risk: Optional[int] = 0


class IncomeCategoryOut(BaseModel):
    category_name: str
    category_id: int
    amount: float


class SpendingProfileOut(BaseModel):
    spending_ratio: float
    savings_ratio: float
    budget_conscious: float


class SessionSavingsPotentialOut(BaseModel):
    potential: str
    amount: float
    session_id: int

    model_config = {
        "from_attributes": True
    }


class SessionBeneficiaryOut(BaseModel):
    beneficiary: str
    total_amount: float
    transaction_count: int
    session_id: int
    model_config = {
        "from_attributes": True
    }


class FinancialProfileDataIn(BaseModel):
    session_id: str
    income_flow: IncomeFlowOut
    risk: RiskOut
    income_categories: list[TransactionCategoryOut]
    expense_categories: list[TransactionCategoryOut]
    spending_profile: SpendingProfileOut
    transactions: TransactionDataOut


class SessionPaymentData(BaseModel):
    id: int
    domain: str
    reference: str
    receipt_number: Optional[str]
    amount: float


class SessionPaymentResponse(BaseModel):
    status: bool
    message: str
    data: SessionPaymentData

class CurrencyCodeData(BaseModel):
    id: int = Field(..., description="Currency ID")
    code: str = Field(..., description="Currency Code")

class CurrencyOut(BaseModel):
    id: int
    name: str
    code: str

    model_config = {
        "from_attributes": True
    }
    