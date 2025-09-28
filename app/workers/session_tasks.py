from typing import List

from celery import shared_task

from app.data.session import SessionAccountOut
from app.database.index import get_db
from app.models.session import SessionAccount, Session
from app.services.session_ai_service import SessionAIService
from app.services.session_transaction_service import SessionTransactionService


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def process_statements(self, session_id: str, file_paths: List[str], bank_ids: List[int]):
    try:
        db = next(get_db())
        session_ai_service = SessionAIService(db)
        session_transaction_service = SessionTransactionService(db)
        session_accounts: List[SessionAccountOut] = []
        id_session = db.query(Session).filter(Session.identifier == session_id).first()
        print("Initializing session accounts...")

        for index, file_path in enumerate(file_paths):
            print("Processing file {}".format(file_path))
            statement = session_ai_service.read_pdf_statement(file_path)
            bank_id = bank_ids[index]
            print("Bank ID: {}".format(bank_id))
            account = SessionAccount(account_name=statement.accountName,
                                     account_number=statement.accountNumber,
                                     current_balance=statement.accountBalance,
                                     session_id=id_session.id,
                                     fetch_method='statement',
                                     currency=statement.accountCurrency,
                                     bank_id=bank_id)
            print("Added Session Account: {}".format(account))
            db.add(account)
            db.commit()
            db.refresh(account)
            session_transaction_service.process_transaction_statements(account.id, statement)
            session_accounts.append(SessionAccountOut.model_validate(account))

        return True
    except Exception as e:
        print(e)


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def analyze_transactions(self, session_id: str):
    try:
        db = next(get_db())
        session_ai_service = SessionAIService(db)
        session_transaction_service = SessionTransactionService(db)
        session_accounts: List[SessionAccountOut] = []
        id_session = db.query(Session).filter(Session.identifier == session_id).first()
        print("Initializing session accounts...")

        for index, file_path in enumerate(file_paths):
            print("Processing file {}".format(file_path))
            statement = session_ai_service.read_pdf_statement(file_path)
            bank_id = bank_ids[index]
            print("Bank ID: {}".format(bank_id))
            account = SessionAccount(account_name=statement.accountName,
                                     account_number=statement.accountNumber,
                                     current_balance=statement.accountBalance,
                                     session_id=id_session.id,
                                     fetch_method='statement',
                                     currency=statement.accountCurrency,
                                     bank_id=bank_id)
            print("Added Session Account: {}".format(account))
            db.add(account)
            db.commit()
            db.refresh(account)
            session_transaction_service.process_transaction_statements(account.id, statement)
            session_accounts.append(SessionAccountOut.model_validate(account))

        return True
    except Exception as e:
        print(e)
# self.retry(countdown=10)
