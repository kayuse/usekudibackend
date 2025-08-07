from typing import Optional
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    firstname: str
    lastname: str
    mobile : Optional[str] = None   
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    
class UserOut(BaseModel):
    id: int
    email: EmailStr
    fullname: str

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

