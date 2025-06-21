from datetime import datetime
from pydantic import BaseModel


class MonoAccountResponseData(BaseModel):
    id: str

class MonoBalanceResponseData(BaseModel):
    id: str
    balance: float
    currency: str
    name: str
    account_number: str  
    
class MonoAuthResponse(BaseModel):
    status: str
    message: str
    timestamp: datetime
    data: MonoAccountResponseData


class MonoAccountBalanceResponse(BaseModel):
    status: str
    message: str
    timestamp: datetime
    data: MonoBalanceResponseData