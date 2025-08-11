from datetime import datetime
import json
import os
from typing import List, Optional, Any, Coroutine
import uuid

from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
import requests

from app.data.mono import AccountMonoData, MonoAccountLinkData, MonoAccountLinkResponse, MonoAuthResponse
from app.services import cache_service
from app.services.mono_service import MonoService
from app.workers.transaction_tasks import fetch_initial_transactions, sync_account_transactions
from app.data.account import AccountCreate, AccountCreateOut, AccountExchangeCreate, AccountExchangeOut, \
    AccountLinkData, AccountOut, BankOut
from app.data.user import UserOut
from sqlalchemy.orm import Session
from app.models.account import Account, Bank, FetchMethod, Transaction


class AccountService:
    def __init__(self, db_session=Session):
        self.db = db_session
        load_dotenv(override=True)  # Load environment variables from .env file
        self.mono_api_key = os.getenv('MONO_API_KEY')
        self.mono_api_secret = os.getenv('MONO_API_SECRET')
        self.mono_api_base_url = os.getenv('MONO_API_BASE_URL')
        self.mono_service = MonoService()
        self.accounts = {}  # account_id -> Account

    async def create_account(self, user: UserOut, account: AccountCreate) -> AccountCreateOut:
        # check if account already exists using db session
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
                          current_balance=0.0,
                          currency=account.currency,
                          fetch_method=FetchMethod(account.fetch_method),
                          user_id=user.id,
                          active=False)

        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        # Link the account immediately
        link_account_data = AccountLinkData(
            customer_email=user.email,
            account_id=account.id,
            customer_name=user.fullname,
            institution_auth_method='internet_banking',
            institution_id=account.bank.institution_id,
            scope='auth')

        link_account_response = await self.link_account(link_account_data, user.id)  # Link account immediately

        print(f"Link Account Response: {link_account_response}")

        return AccountCreateOut(
            account_name=account.account_name,
            account_number=account.account_number,
            active=account.active,
            id=account.id,  # Assuming id is the primary key in Account model
            current_balance=account.current_balance,
            currency=account.currency,
            bank_id=account.bank_id,
            link_account_response=link_account_response,
            bank=BankOut(
                bank_id=account.bank.id,
                bank_name=account.bank.bank_name,
                image_url=account.bank.image_url
            ),
            account_type=account.account_type
        )

    def get_banks(self) -> List[Bank]:
        return self.db.query(Bank).where(Bank.active == True).all()

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

    def establish_exchange(self, data: AccountExchangeCreate) -> AccountExchangeOut:
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

            response_data: MonoAuthResponse = MonoAuthResponse(**response.json())
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

    def get_referred_balance(self, account_id: int) -> float:
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return 0.0
        # Fetch the balance from Mono API
        try:

            latest_transaction = self.db.query(Transaction).filter(
                Transaction.account_id == account_id).order_by(Transaction.date.desc()).first()
            print(f"Latest transaction for account {account_id}: {latest_transaction}")
            if latest_transaction:
                return latest_transaction.balance_after_transaction
            # If no transactions found, return the current balance from the account
            return account.current_balance

        except Exception as e:
            print(f"Error fetching balance for account {account_id}: {e}")
            return 0.0

    def sync_account(self, account_id: str, user_id: str) -> AccountOut:
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not account:
            raise ValueError("Account not found.")
        if account.account_id is None:
            raise ValueError("Account is not linked. Please Link your Account first.")
        # Fetch the latest balance and transactions from Mono
        data = self.mono_service.fetch_account_balance(account.account_id)
        print(f"Syncing account: {account.account_number} with ID: {account.account_id}")
        print(f"Response Data: {data}")
        if data.status == "successful" and data.data.balance / 100 != account.current_balance:
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

    def disable_account(self, account_id: int, user_id: int) -> AccountOut:
        # Fetch the account from the database
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not account:
            raise ValueError("Account not found.")

        # Disable the account

        if not account.account_id:
            raise ValueError("Account is not linked. Please Link your Account first.")

        result = self.mono_service.disable(account.account_id)
        if not result:
            raise ValueError("Failed to disable account on Mono.")

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

    def enable_account(self, account_id: int, user_id: int) -> AccountOut:
        # Fetch the account and user details from the database
        account = self.db.query(Account).filter(Account.id == account_id, Account.user_id == user_id).first()
        if not account:
            raise ValueError("Account not found.")

        # Enable the account
        if account.account_id is not None:
            result = self.mono_service.enable(account.account_id)
            if not result:
                raise ValueError("Failed to enable account on Mono.")

        account.active = True
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

    async def initiate_account_linking(self, account_id: int, user_id: int) -> AccountMonoData:
        """
        Initiate account linking using Mono API.
        """
        try:
            account: Account = self.db.query(Account).join(Account.user).join(Account.bank).filter(
                Account.id == account_id, Account.user_id == user_id).first()
            # if not account:
            #     raise ValueError("Account not found.")

            data = AccountLinkData(
                customer_email=account.user.email,
                customer_name=account.user.fullname,
                account_id=account.id,
                institution_id=account.bank.institution_id,
                institution_auth_method=account.bank.auth_method or 'internet_banking',
                scope='auth'
            )


            response = self.mono_service.initiate_account_linking(data)
            print(response)
            if response.status != "successful":
                raise ValueError(f"Failed to initiate account linking: {response.message}")

            data = response.data
            print(f"Account linking initiated for account ID: {account.id} with session ID: {data}")
            unique_id = str(uuid.uuid4())
            mono_acount_data = AccountMonoData(
                account_id=account.id,
                mono_data=data,
                session_id=unique_id
            )
            await cache_service.set_cache(mono_acount_data.mono_data.customer,
                                          json.dumps(mono_acount_data.model_dump(mode="json")), 1800)
            await cache_service.set_cache(unique_id, json.dumps({'status': True}), 1800)  # Cache for 30 seconds
            return mono_acount_data
        except requests.RequestException as e:
            print(f"Failed to initiate account linking: {e}")
            raise ValueError(f"Error initiating account linking: {str(e)}")

    def delete_account(self, account_id: int, user_id: int) -> bool:
        # delete account from the database
        print(account_id, user_id)
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

    def resync_transactions(self) -> list[Account]:
        # fetch accounts where last_synced is more than 24 hours ago
        accounts = self.db.query(Account).filter(Account.active == True).filter(
            Account.last_synced < datetime.now() - relativedelta(days=1)).all()
        unsliced_accounts: list[Account] = []
        for account in accounts:
            start_from = account.last_synced or datetime.now() - relativedelta(months=3)
            sync_account_transactions.delay(account.id, start_from)
            unsliced_accounts.append(account)

        return unsliced_accounts

    async def link_account(self, data: AccountLinkData, user_id: int) -> AccountMonoData:
        """
        Link an account using Mono API.
        """
        try:
            account = self.db.query(Account).filter(Account.id == data.account_id, Account.user_id == user_id).first()
            if not account:
                raise ValueError("Account not found.")

            response = self.mono_service.initiate_account_linking(data)

            if response.status != "successful":
                raise ValueError(f"Failed to link account: {response.message}")
            data = response.data
            unique_id = str(uuid.uuid4())
            mono_acount_data = AccountMonoData(
                account_id=account.id,
                mono_data=data,
                session_id=unique_id
            )
            await cache_service.set_cache(mono_acount_data.mono_data.customer,
                                          json.dumps(mono_acount_data.model_dump(mode="json")), 1800)
            await cache_service.set_cache(unique_id, json.dumps({'status': True}), 1800)  # Cache for 30 seconds
            return data
        except requests.RequestException as e:
            raise ValueError(f"Error linking account: {str(e)}")

    async def sync_account_id_with_account(self, data: dict) -> AccountOut:
        customer_id = data.get('customer')
        link_data = await cache_service.get_cache(customer_id)
        link_json_data = json.loads(link_data)
        account_mono_data = AccountMonoData(**link_json_data)
        account = self.db.query(Account).filter(Account.id == account_mono_data.account_id).first()
        if not account:
            raise ValueError("Account not found.")
        account.account_id = data['id']
        account.active = True
        self.db.commit()
        self.db.refresh(account)

        self.refresh_balance(account.id)
        fetch_initial_transactions.delay(account.id)

        result = AccountOut(
            id=account.id,
            account_name=account.account_name,
            account_number=account.account_number,
            account_id=account.account_id,
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
        # Clear the cache after syncing account ID
        await cache_service.delete_cache(account_mono_data.session_id)
        await cache_service.delete_cache(customer_id)
        return result

    # write a service from the router session to get a session stored in cache and check if the session is active
    async def get_session_status(self, session_id: str) -> dict:
        session_data = await cache_service.get_cache(session_id)

        if not session_data:
            print(f"Session {session_id} not found in cache.")
            return {'status': False}

        session_data = json.loads(session_data)
        return session_data
