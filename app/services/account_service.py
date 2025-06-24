from datetime import datetime
import os
from typing import List, Optional
from uuid import uuid4

from dotenv import load_dotenv
import requests

from app.data.mono import MonoAuthResponse
from app.services.mono_service import MonoService
from app.workers.tasks import fetch_initial_transactions


from app.data.account import AccountCreate, AccountExchangeCreate, AccountExchangeOut, AccountOut, BankOut
from app.data.user import UserOut
from sqlalchemy.orm import Session
from app.models.account import Account, Bank, FetchMethod



class AccountService:
    def __init__(self, db_session=Session):
        self.db = db_session
        load_dotenv(override=True)  # Load environment variables from .env file
        self.mono_api_key = os.getenv('MONO_API_KEY')
        self.mono_api_secret = os.getenv('MONO_API_SECRET')
        self.mono_api_base_url = os.getenv('MONO_API_BASE_URL')
        self.mono_service = MonoService()
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
            id=account.id , # Assuming id is the primary key in Account model
            current_balance=account.current_balance,
            currency=account.currency,
            bank_id=account.bank_id,
            bank=BankOut(
                bank_id=account.bank.id,
                bank_name=account.bank.bank_name,
                image_url=account.bank.image_url
            ),
            account_type=account.account_type
        )

    def get_banks(self) -> List[Bank]:
        return self.db.query(Bank).all()
    
    def refresh_balance(self, id: str) -> AccountOut:
        account = self.db.query(Account).filter(Account.id == id).first()
        if not account:
            raise ValueError("Account not found.")
        
        data = self.mono_service.fetch_account_balance(account.account_id)
        
        if data.status == "successful":
            account.current_balance = data.data.balance / 100
            account.currency = data.data.currency
            self.db.commit()
            self.db.refresh(account)
        
        return AccountOut(
                id=account.id,
                account_name=account.account_name,
                account_number=account.account_number,
                account_id=account.account_id,
                active=account.active,
                bank_id=account.bank_id,
                bank=BankOut(
                    bank_id=account.bank.id,
                    bank_name=account.bank.bank_name,
                    image_url=account.bank.image_url
                ),
                current_balance=account.current_balance,
                currency=account.currency
        )
    
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
            print(response.status_code, response.text, self.mono_api_secret)
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
            self.refresh_balance(account.id)  # Refresh the balance after establishing exchange
            fetch_initial_transactions.delay(account.id)  # Call the worker to fetch initial transactions
            return AccountExchangeOut(
                id=account.id,
                account_id=account.account_id
            )
        except Exception as e:
            raise ValueError(f"Error establishing exchange: {str(e)}")
        
    def get_accounts_by_user(self, user_id: str) -> List[AccountOut]:
        try:
            accounts = self.db.query(Account).join(Account.bank).filter(Account.user_id == user_id).all()
            return [AccountOut(
                id=account.id,
                account_name=account.account_name,
                account_number=account.account_number,
                account_id=account.account_id,
                active=account.active,
                current_balance=account.current_balance,
                bank_id=account.bank_id,
                bank=BankOut(
                    bank_id=account.bank.id,
                    bank_name=account.bank.bank_name,
                    image_url=account.bank.image_url
                ),
                currency=account.currency,
                account_type=account.account_type
            ) for account in accounts]
        except Exception as e:
            raise ValueError(f"Error fetching accounts: {str(e)}")
        

    def sync_account(self, account_id: str, user_id : str) -> AccountOut:
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not account:
            raise ValueError("Account not found.")
        if account.account_id is None:
            raise ValueError("Account is not linked. Please Link your Account first.")
        # Fetch the latest balance and transactions from Mono
        data = self.mono_service.fetch_account_balance(account.account_id)
    
        if data.status == "successful":
            account.current_balance = data.data.balance / 100
            account.currency = data.data.currency
            self.db.commit()
            self.db.refresh(account)
        
        return AccountOut(
                id=account.id,
                account_name=account.account_name,
                account_number=account.account_number,
                bank_id=account.bank_id,
                active=account.active,
                current_balance=account.current_balance,
                currency=account.currency
        )
    
    def disable_account(self, account_id: int, user_id : int) -> AccountOut:
        # Fetch the account from the database
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not account:
            raise ValueError("Account not found.")
        
        # Disable the account
        account.active = False
        self.db.commit()
        self.db.refresh(account)
        
        return AccountOut(
            id=account.id,
            account_name=account.account_name,
            account_number=account.account_number,
            active=account.active,
            current_balance=account.current_balance,
            currency=account.currency,
            bank_id=account.bank_id,
            bank=BankOut(
                bank_id=account.bank.id,
                bank_name=account.bank.bank_name,
                image_url=account.bank.image_url
            ),
            account_type=account.account_type
        )
        
        
    def delete_account(self, account_id: int, user_id : int) -> bool:
        #delete account from the database
        print(account_id, user_id )
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not account:
            raise ValueError("Account not found.")
        # Remove the account from the database
        self.db.delete(account)
        self.db.commit()
        # Remove the account from the in-memory dictionary
        return True

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