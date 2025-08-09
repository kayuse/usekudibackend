
from requests import Session
from app.models.message import Message
from app.data.message import WhatsAppMessage
from app.services.ai_service import AIService
from app.services.auth_service import AuthService  # Import UserService from its module
from twilio.rest import Client
import os
from dotenv import load_dotenv

from app.workers.ai_tasks import run_rag

load_dotenv(override=True)  # Load environment variables from .env file
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

class MessageService:
    def __init__(self, db_session = Session):
        self.db_session = db_session
        self.client = Client(account_sid, auth_token)
        self.auth_service = AuthService(db_session=db_session)  # Assuming you have a UserService to handle user-related operations
        self.ai_service = AIService(db_session=db_session)  # Assuming you have an AIService to handle AI-related operations

    async def process(self, body: dict, app = 'whatsapp') -> dict:

        if app == 'whatsapp':
            return await self.process_whatsapp_message(body)
        else:
            raise ValueError("Unsupported app type. Supported types are 'whatsapp' and 'sms'.") 
        
        return {'status': 'success', 'message': 'Message processed successfully'}
    async def process_whatsapp_message(self, body: dict) -> dict:
        """
        Process a WhatsApp message.
        """
        whatsAppMessage = WhatsAppMessage(**body)
        to_number = whatsAppMessage.WaId
        run_rag.delay(to_number,whatsAppMessage.Body)
        return {'status': 'success', 'message': 'WhatsApp message processed successfully'}
    def _get_current_timestamp(self):
        from datetime import datetime
        return datetime.now().isoformat()