import uuid
from datetime import datetime
from typing import List

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.data.account import AccountExchangeCreate, TransactionOut
from app.models.account import Bank, Transaction
from app.models.session import Session as SessionModel, SessionAccount, SessionTransaction, SessionFile

from app.data.session import SessionCreate, SessionOut, AccountExchangeSessionCreate, SessionAccountOut, Statement
from app.services.file_upload_service import FileUploadService
from app.services.mono_service import MonoService
from app.services.session_ai_service import SessionAIService
from app.workers.session_tasks import process_statements
from app.workers.transaction_tasks import fetch_session_transactions


class SessionService:

    def __init__(self, db=Session):
        self.db = db
        self.upload_service = FileUploadService()
        self.mono_service = MonoService()
        self.session_ai_service = SessionAIService(self.db)

    def start(self, data: SessionCreate) -> SessionOut:
        identifier: str = uuid.uuid4().hex
        session_name = f"session_{identifier}"

        session = SessionModel(identifier=identifier,
                               name=data.name,
                               customer_type=data.customer_type,
                               processing_status="started",
                               email=data.email)
        self.db.add(session)
        self.db.commit()
        return SessionOut.model_validate(session)

    def start_session(self, data: SessionCreate) -> SessionOut:
        identifier: str = uuid.uuid4().hex

    def exchange_account_session(self, data: AccountExchangeSessionCreate) -> List[SessionAccountOut]:

        try:
            session = self.db.query(SessionModel).filter(SessionModel.identifier == data.session_id).first()
            results: List[SessionAccountOut] = []
            for exchange_code in data.exchange_codes:
                response_data = self.mono_service.account_auth(exchange_code)
                account_details = self.mono_service.fetch_account_details(response_data.account_id)
                bank_id = self.db.query(Bank).filter(
                    Bank.bank_code == account_details.data.account.institution.bank_code).first().id
                session_account = SessionAccount(account_id=response_data.data.id, bank_id=bank_id,
                                                 account_name=account_details.data.account.name,
                                                 account_number=account_details.data.account.account_number,
                                                 currency=account_details.data.account.currency, session_id=session.id)
                self.db.add(session_account)
                self.db.commit()
                self.db.refresh(session_account)
                fetch_session_transactions.delay(session_account.id)
                results.append(SessionAccountOut.model_validate(session_account))

            return results

        except Exception as e:
            raise ValueError(f"Error establishing exchange: {str(e)}")

    async def process_statements(self, session_id: str, files: List[UploadFile],
                                 bank_ids: List[int],
                                 ) -> bool:
        try:
            session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            file_paths = await self.upload_service.upload_to_path(files)
            session_files: List[int] = []
            for index, file_path in enumerate(file_paths):

                session_file = SessionFile(file_path=file_path, session_id=session_record.id, password=None)
                self.db.add(session_file)
                self.db.commit()
                self.db.refresh(session_file)
                session_files.append(session_file.id)

            process_statements.delay(session_id, session_files, bank_ids)
            return True
        except Exception as e:
            raise ValueError(f"Error processing statements: {str(e)}")

    def get_session(self, session_id: str) -> SessionOut:
        try:
            session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            print(session)
            return SessionOut.model_validate(session)
        except Exception as e:
            raise ValueError(f"Error getting session: {str(e)}")
