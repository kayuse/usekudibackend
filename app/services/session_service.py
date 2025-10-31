import uuid
from datetime import datetime
from typing import List

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.data.account import AccountExchangeCreate, TransactionOut
from app.models.account import Bank, Transaction
from app.models.session import Session as SessionModel, SessionAccount, SessionTransaction, SessionFile, SessionInsight, \
    SessionSwot, SessionSavingsPotential, SessionBeneficiary

from app.data.session import SessionCreate, SessionOut, AccountExchangeSessionCreate, SessionAccountOut, \
    SessionInsightOut, SessionSwotOut, SessionSavingsPotentialOut
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
                                 ) -> bool:
        try:
            session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            file_paths = await self.upload_service.upload_to_path(files)
            session_files: List[int] = []
            for index, file_path in enumerate(file_paths):
                session_file = SessionFile(file_path=file_path,
                                           session_id=session_record.id, bank_id=None,
                                           password=None)
                self.db.add(session_file)
                self.db.commit()
                self.db.refresh(session_file)
                session_files.append(session_file.id)

            process_statements.delay(session_id, session_files)
            return True
        except Exception as e:
            raise ValueError(f"Error processing statements: {str(e)}")

    async def retry_process_statements(self, session_id: str) -> bool:
        try:
            session_record = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            session_files = self.db.query(SessionFile).filter(SessionFile.session_id == session_record.id).all()
            accounts = self.db.query(SessionAccount).filter(SessionAccount.session_id == session_record.id).all()
            account_ids = [a.id for a in accounts]
            file_ids = [sf.id for sf in session_files]
            bank_ids = [sf.bank_id for sf in session_files]
            # delete sessionsavings, sessionaccounts, sessiontransactions, sessioninsights, sessionswots, sessiobeneficiaries
            print("Deleting previous session data for retry...")
            self.db.query(SessionSavingsPotential).filter(
                SessionSavingsPotential.session_id == session_record.id).delete()
            self.db.query(SessionSwot).filter(SessionSwot.session_id == session_record.id).delete()
            self.db.query(SessionInsight).filter(SessionInsight.session_id == session_record.id).delete()
            self.db.query(SessionTransaction).filter(
                SessionTransaction.account_id.in_(account_ids)).delete()
            self.db.query(SessionAccount).filter(SessionAccount.session_id == session_record.id).delete()
            self.db.query(SessionBeneficiary).filter(SessionBeneficiary.session_id == session_record.id).delete()
            self.db.commit()
            print("Deleted previous session data for retry.")
            process_statements.delay(session_id, file_ids, bank_ids)
            return True
        except Exception as e:
            raise ValueError(f"Error retrying processing statements: {str(e)}")

    def get_session(self, session_id: str) -> SessionOut:
        try:
            session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            print(session)
            return SessionOut.model_validate(session)
        except Exception as e:
            raise ValueError(f"Error getting session: {str(e)}")

    def get_insights(self, session_id: str) -> list[SessionInsightOut]:
        try:
            session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            insights = self.db.query(SessionInsight).filter(SessionInsight.session_id == session.id).all()
            return [SessionInsightOut.model_validate(s) for s in insights]
        except Exception as e:
            raise ValueError(f"Error getting insights: {str(e)}")

    def get_swot(self, session_id: str) -> list[SessionSwotOut]:
        try:
            session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            swots = self.db.query(SessionSwot).filter(SessionSwot.session_id == session.id).all()
            return [SessionSwotOut.model_validate(s) for s in swots]
        except Exception as e:
            raise ValueError(f"Error getting session SWOT: {str(e)}")

    def get_savings_potentials(self, session_id: str) -> list[SessionSavingsPotentialOut]:
        try:
            session = self.db.query(SessionModel).filter(SessionModel.identifier == session_id).first()
            savings_potentials = self.db.query(SessionSavingsPotential).filter(
                SessionSavingsPotential.session_id == session.id).all()
            return [SessionSavingsPotentialOut.model_validate(sp) for sp in savings_potentials]
        except Exception as e:
            raise ValueError(f"Error getting session savings potentials: {str(e)}")
