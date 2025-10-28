import asyncio
import time
from typing import List

from celery import shared_task
import traceback

from app.data.mail import EmailTemplateData
from app.data.session import SessionAccountOut
from app.database.index import get_db
from app.models.session import SessionAccount, Session, SessionFile, SessionTransaction
from app.services.email_services import EmailService
from app.services.session_advice_service import SessionAdviceService
from app.services.session_ai_service import SessionAIService
from app.services.session_transaction_service import SessionTransactionService
from dotenv import load_dotenv
import os

load_dotenv(override=True)
base_url = os.getenv("APP_BASE_URL")


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def process_statements(self, session_id: str, files_id: List[int], bank_ids: List[int]):
    return asyncio.run(run_process_statements(session_id, files_id, bank_ids))


async def run_process_statements(session_id: str, files_id: List[int], bank_ids: List[int]):
    try:
        db = next(get_db())
        session_ai_service = SessionAIService(db)
        session_transaction_service = SessionTransactionService(db)
        session_accounts: List[SessionAccountOut] = []
        session_record = db.query(Session).filter(Session.identifier == session_id).first()

        print("Initializing session accounts...")
        session_record.processing_status = "initializing_statements"
        db.commit()
        for index, file_id in enumerate(files_id):
            print("Processing file {}".format(file_id))
            session_file = db.query(SessionFile).filter(SessionFile.id == file_id).first()
            statement = await session_ai_service.read_pdf_directly(session_file)
            if statement is None:
                continue
            bank_id = bank_ids[index]
            print("Bank ID: {}".format(bank_id))
            if statement.accountName is None:
                statement.accountName = "Unnamed Account"
            if statement.accountCurrency is None:
                statement.accountCurrency = "NGN"
            if statement.accountNumber is None:
                statement.accountNumber = "0000000000"

            account = SessionAccount(account_name=statement.accountName,
                                     account_number=statement.accountNumber,
                                     current_balance=statement.accountBalance,
                                     session_id=session_record.id,
                                     fetch_method='statement',
                                     currency=statement.accountCurrency,
                                     bank_id=bank_id)
            print("Added Session Account: {}".format(account))
            db.add(account)
            db.commit()
            db.refresh(account)
            session_transaction_service.process_transaction_statements(account.id, statement)
            session_accounts.append(SessionAccountOut.model_validate(account))

        session_record.processing_status = "categorizing"
        db.commit()

        category_response = await session_transaction_service.categorize_session_transactions(session_record.id)

        if not category_response:
            raise ValueError("Invalid Categorization for session transactions {}".format(session_id))
        session_record.processing_status = "analyzing_payments"
        db.commit()
        await analyze_run_payments(session_record.identifier)
        session_record.processing_status = "analyzing_transactions"
        db.commit()
        analyze_transactions(session_record.identifier)
        session_record.processing_status = "done"
        db.commit()
        email_service = EmailService()
        data = EmailTemplateData(
            to_email=session_record.email,
            template_name="session_ready_email.html",
            subject="Your Report is Ready",
            context={
                "name": session_record.name,
                "url": f"{base_url}/dashboard/{session_record.identifier}"
            }
        )
        email_service.send_templated_email(data)
        return True
    except Exception as e:
        print(e)
        traceback.print_exc()


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def analyze_transactions(self, session_id: str):
    try:

        db = next(get_db())
        print("Generating financial profile...")
        session_ai_service = SessionAIService(db)
        session_transaction_service = SessionTransactionService(db)
        session_record: Session = db.query(Session).filter(Session.identifier == session_id).first()

        session_record.processing_status = "analyzing_financial_profile"

        db.commit()

        financial_profile = session_transaction_service.calculate_financial_position(session_record.identifier)
        insights = session_ai_service.generate_insights(session=session_record,
                                                        data_in=financial_profile)
        session_record.processing_status = "analyzing_insights"

        db.commit()
        swot = session_ai_service.generate_swot(session=session_record,
                                                data_in=financial_profile)
        session_record.processing_status = "analyzing_swot"

        db.commit()
        savings_potential = session_ai_service.generate_savings_potential(session=session_record,
                                                                          data_in=financial_profile)
        session_record.processing_status = "analyzing_savings_potential"

        db.commit()
        session_ai_service.get_overall_assessment(session=session_record, insights=insights,
                                                  savings_potential=savings_potential, swot_insight=swot)
        session_record.processing_status = "processed_analysis"

        db.commit()
        return True
    except Exception as e:
        print(e)
        traceback.print_exc()


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def analyze_payments(self, session_id: str):
    return asyncio.run(analyze_run_payments(session_id))


async def analyze_run_payments(session_id: str):
    try:
        db = next(get_db())
        print("Analyzing Payments for Session {}".format(session_id))
        session_record: Session = db.query(Session).filter(Session.identifier == session_id).first()
        session_advice_service = SessionAdviceService(db)

        beneficiary_result = await session_advice_service.process_top_beneficiaries(session_record.identifier)
        recurring_data = session_advice_service.get_recurring_expenses(session_record.identifier)

    except Exception as e:
        print(e)
        traceback.print_exc()

# @shared_task
# def process_chat(session_id: str, socket_id: str, text: str):
#     db = next(get_db())
#     print("Processing Chat {}".format(session_id))
#     chat_service = SessionChatService(db)
#     chat_service.process(session_id, text)
#     publish(f"session_socket:{socket_id}", text)
#     print("Processing Chat {}".format(session_id))
#
#     return f"Processed message for {socket_id}: {text}"
