import os
from typing import List, Optional
from uuid import uuid4

from dotenv import load_dotenv
import requests

from app.workers.tasks import fetch_initial_transactions


from app.data.account import AccountCreate, AccountExchangeCreate, AccountExchangeOut, AccountOut, MonoAuthResponse
from app.data.user import UserOut
from sqlalchemy.orm import Session
from app.models.account import Account, Bank, FetchMethod



load_dotenv()

class AccountService:
    def __init__(self, db_session=Session):
        self.db = db_session
        self.mono_api_key = os.getenv('MONO_API_KEY')
        self.mono_api_secret = os.getenv('MONO_API_SECRET')
        self.mono_api_base_url = os.getenv('MONO_API_BASE_URL')
        self.accounts = {}  # account_id -> Account

    def create_account(self, user: UserOut, account: AccountCreate) -> AccountOut:
       #check if account already exists using db session
        existing_account = self.db.query(Account).filter(
            Account.account_number == account.account_number and
            Account.bank_id == account.bank_id
        ).first()
        if existing_account:
            raise ValueError("Account with this account number already exists for this user.")
        # Create a new account
        account = Account(account_name=account.account_name,
                          account_number=account.account_number,
                          bank_id=account.bank_id,
                          account_type=account.account_type,
                          current_balance=account.balance,
                          currency=account.currency,
                          fetch_method=FetchMethod(account.fetch_method),
                          user_id=user.id,
                          active=False)
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        return AccountOut(
            account_name=account.account_name,
            account_number=account.account_number,
            active=account.active,
            id=account.id  # Assuming id is the primary key in Account model
        )

    def get_banks(self) -> List[Bank]:
        return self.db.query(Bank).all()
    
    def establish_exchange(self, data : AccountExchangeCreate) -> AccountExchangeOut:
        try:
            headers = {
                "mono-sec-key": f"{self.mono_api_secret}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            payload = { 
                "code": data.exchange_code,  # Generate a unique account ID
            }
            response = requests.post(
                f"{self.mono_api_base_url}/accounts/auth",
                headers=headers,
                json=payload
            )
            if response.status_code != 200:
                raise ValueError(f"Failed to establish exchange: Please try again later")
                
            
            response_data : MonoAuthResponse = MonoAuthResponse(**response.json())
            if response_data.status != "successful":
                raise ValueError(f"Failed to establish exchange: {response_data.message}")
            account = self.db.query(Account).filter(Account.id == data.account_id).first()
            if not account:
                raise ValueError("Account not found.")
            account.account_id = response_data.data.id
            account.active = True
            self.db.commit()
            self.db.refresh(account)

            fetch_initial_transactions.delay(account.id)  # Call the worker to fetch initial transactions
            return AccountExchangeOut(
                id=account.id,
                account_id=account.account_id
            )
        except Exception as e:
            raise ValueError(f"Error establishing exchange: {str(e)}")
        
    def get_accounts_by_user(self, user_id: str) -> List[Account]:
        return [acc for acc in self.accounts.values() if acc.user_id == user_id]

    def delete_account(self, account_id: str) -> bool:
        if account_id in self.accounts:
            del self.accounts[account_id]
            return True
        return False

    def set_account_active(self, account_id: str, active: bool) -> bool:
        account = self.accounts.get(account_id)
        if account:
            account.active = active
            return True
        return False

    def update_account(self, account_id: str, name: Optional[str] = None, details: Optional[dict] = None) -> bool:
        account = self.accounts.get(account_id)
        if account:
            if name is not None:
                account.name = name
            if details is not None:
                account.details = details
            return True
        return False