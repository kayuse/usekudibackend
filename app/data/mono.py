from datetime import datetime
from typing import Optional
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
    
class MonoAuthMethod(BaseModel):
    id: str
    type: str
    name: str
    identifier: Optional[str] = None

class MonoScope(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None

class MonoInstitutionData(BaseModel):
    id: str
    institution: str
    type: str
    nip_code: Optional[str] = None
    bank_code: Optional[str] = None
    country: Optional[str] = None
    auth_methods: list[MonoAuthMethod] 
    scope: list[MonoScope]
    
class MonoInstitutionResponse(BaseModel):
    status: str
    message: str
    timestamp: datetime
    # data: list[MonoInstitution]

class MonoAccountInstitutionData(BaseModel):
    id : str
    auth_method: str
    
class MonoAccountLinkData(BaseModel):
   id: Optional[str] = None
   mono_url : str
   customer: str
   scope:str
   institution: MonoAccountInstitutionData
   redirect_url: str
   is_multi: Optional[bool] = False
   created_at: Optional[datetime] = None
   
   
class MonoAccountLinkResponse(BaseModel):
    status: str
    message: str
    timestamp: datetime
    data: MonoAccountLinkData

class AccountMonoData(BaseModel):
    account_id: int
    mono_data: MonoAccountLinkData
    session_id: str