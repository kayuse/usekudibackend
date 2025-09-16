from pydantic import BaseModel


class SessionCreate(BaseModel):
    email: str
    payment_id : int