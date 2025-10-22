import uuid
from datetime import datetime
from typing import List

import requests
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from app.data.session import SessionPaymentData, SessionPaymentResponse
from app.models.session import Session as SessionModel, SessionPaymentStore, SessionPayment
import os

load_dotenv(override=True)


class SessionPaymentService:

    def __init__(self, db=Session):
        self.db = db
        self.paystack_secret_key = os.getenv("PAYSTACK_SECRET_KEY")
        self.paystack_url = os.getenv("PAYSTACK_BASE_URL")

    def verify_payment(self, session_id: str, payment_reference: str) -> bool:

        url = f"{self.paystack_url}transaction/verify/{payment_reference}"

        headers = {"Authorization": f"Bearer {self.paystack_secret_key}"}

        response = requests.get(url, headers=headers)
        result: SessionPaymentResponse = SessionPaymentResponse(**response.json())

        session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()

        payment_record = SessionPaymentStore(amount=result.data.amount, payment_reference=payment_reference,
                                             payment_id=1, session_id=session_record.id)
        session_record.paid = True
        self.db.add(payment_record)
        self.db.commit()
        self.db.refresh(payment_record)

        if response.status_code != 200:
            raise ValueError("Error connecting to Paystack")

        data = result.data
        if not data or result.status == False:
            raise ValueError("Payment not verified")

        return True
