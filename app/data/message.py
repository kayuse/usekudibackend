

from typing import Optional
from pydantic import BaseModel


class WhatsAppMessage(BaseModel):
    """
    Model for WhatsApp message.
    """
    SmsMessageSid: str
    NumMedia: int
    MessageSid: str
    MessageStatus: Optional[str] = None
    Body: str
    To: str
    NumSegments: int
    MessageSid: str
    AccountSid: str
    WaId: str
    From: str
    ApiVersion: str