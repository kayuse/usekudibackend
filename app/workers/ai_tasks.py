import asyncio

from celery import shared_task
from dotenv import load_dotenv
from twilio.rest import Client

from app.database.index import get_db
from app.models.message import Message
from app.services.ai_service import AIService
import os
load_dotenv(override=True)
account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')

@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def run_rag(self, ownerid: str, body: str):
    async def run_rag_task(owerid: str, body: str):
        try:
            db = next(get_db())
            print(f"Running AI Service for : {ownerid}")
            print(f"Database session: {db}")
            # Simulate fetching transactions
            service = AIService(db_session=db)
            message = await service.process(ownerid=ownerid, body=body)
            message_response = message.message if message else "Hello! How can I assist you today?"
            client = Client(account_sid, auth_token)
            result = client.messages.create(
                from_="whatsapp:+14155238886",  # Twilio sandbox number
                body=message_response,
                to=f"whatsapp:+{ownerid}"  # Recipient's WhatsApp number
            )
            if not result:
                raise self.retry(countdown=60)
            model = Message(
                content=body,
                response=message_response,
                user_id=1
            )
            db.add(model)
            db.commit()
            print(f"Fetching initial transactions for account: {ownerid}")
            # service = AccountService(db_session=db)

            # Here you would implement the logic to fetch transactions from an external API
            # For now, we just simulate a delay
            print(f"Fetched initial transactions for account: {ownerid}")
        finally:
            db.close()

    asyncio.run(run_rag_task(ownerid, body))
