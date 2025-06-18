from datetime import datetime
from dateutil.relativedelta import relativedelta

from dotenv import load_dotenv

from app.data.account import AccountCreate, AccountOut
from app.models.account import Account, Transaction
import requests
from sqlalchemy.orm import Session
import os
load_dotenv()

class TransactionService:
    
    def __init__(self, db_session=Session):
        if not db_session:
            raise ValueError("Database session is not initialized.")
        self.db = db_session
        self.mono_api_key = os.getenv('MONO_API_KEY')
        self.mono_api_secret = os.getenv('MONO_API_SECRET')
        self.mono_api_base_url = os.getenv('MONO_API_BASE_URL')

    def get_transaction(self, transaction_id: int):
        return self.db.query(Transaction).filter(Transaction.id == transaction_id).first()
    
    def index_transactions(self, account_id : int) -> bool:
        # Fetch the account from the database
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            print(f"Account with ID {account_id} not found.")
            return False
        # Fetch transactions from the Mono API
        headers = {
            "mono-sec-key": f"{self.mono_api_secret}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        start_date = datetime.now() - relativedelta(months=3)
        response = requests.get(
            f"{self.mono_api_base_url}/accounts/{account.account_id}/transactions?start_date={start_date.strftime('%Y-%m-%d')}&paginate=false",
            headers=headers
        )
        print(f"Fetching transactions for account: {account.account_number}")
        if response.status_code != 200:
            print(f"Failed to fetch transactions: {response.status_code} - {response.text}")
            return False
        transactions_data = response.json().get('data', [])
        for transaction_data in transactions_data:
            #print transaction_data entirely with all its keys and values
            print(f"Transaction Data: {transaction_data}")
            existing_transaction = self.db.query(Transaction).filter(
                Transaction.transaction_id == transaction_data['id'],
                Transaction.account_id == account.id
            ).first()
            if not existing_transaction:
                # Create a new transaction
                new_transaction = Transaction(
                    transaction_id=transaction_data['id'],
                    account_id=account.id,
                    amount=transaction_data.get('amount', 0.0),
                    currency=transaction_data.get('currency', 'NGN'),
                    description=transaction_data.get('description', ''),
                    date=transaction_data['date'],
                    balance_after_transaction=transaction_data.get('balance', 0.0),
                    transaction_type=transaction_data.get('type', 'unknown')
                )
                self.db.add(new_transaction)
                self.db.commit()
        print(f"Fetched and indexed transactions for account: {account.account_number}")
        account.indexed = True  # Mark the account as indexed
        account.active = True  # Optionally set the account as active
        self.db.commit()
        return True

    def get_transactions(self, skip: int = 0, limit: int = 100):
        return self.db.query(Transaction).offset(skip).limit(limit).all()

    def create_transaction(self, transaction: AccountCreate):
        db_transaction = Transaction(**transaction.dict())
        self.db.add(db_transaction)
        self.db.commit()
        self.db.refresh(db_transaction)
        return db_transaction

    def update_transaction(self, transaction_id: int, transaction: AccountCreate):
        db_transaction = self.get_transaction(transaction_id)
        if not db_transaction:
            return None
        for key, value in transaction.dict(exclude_unset=True).items():
            setattr(db_transaction, key, value)
        self.db.commit()
        self.db.refresh(db_transaction)
        return db_transaction

    def delete_transaction(self, transaction_id: int):
        db_transaction = self.get_transaction(transaction_id)
        if not db_transaction:
            return None
        self.db.delete(db_transaction)
        self.db.commit()
        return db_transaction