from datetime import datetime
import json
import time
from dateutil.relativedelta import relativedelta

from dotenv import load_dotenv
from sqlalchemy import text
from app.data.account import AccountCreate, AccountOut, CategoryOut, TransactionOut, TransactionSearch
from app.data.mono import MonoInstitutionData
from app.models.account import Account, Bank, Category, Transaction
from sqlalchemy.orm import Session
from app.services import cache_service
import os

from app.services.ai_service import AIService
from app.services.mono_service import MonoService

load_dotenv()


class TransactionService:

    def __init__(self, db_session=Session):
        if not db_session:
            raise ValueError("Database session is not initialized.")
        self.db = db_session
        self.mono_api_key = os.getenv('MONO_API_KEY')
        self.mono_api_secret = os.getenv('MONO_API_SECRET')
        self.mono_api_base_url = os.getenv('MONO_API_BASE_URL')
        self.mono_service = MonoService()
        self.ai_service = AIService(db_session=db_session)  # Assuming you have an AiService class for AI-related tasks

    def get_transaction(self, transaction_id: int):
        return self.db.query(Transaction).filter(Transaction.id == transaction_id).first()

    def index_transactions(self, account_id: int, start_from: datetime = None) -> bool:
        # Fetch the account from the database
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            print(f"Account with ID {account_id} not found.")
            return False
        # Fetch transactions from the Mono API
        start_from = start_from or datetime.now() - relativedelta(months=3)

        transactions_data = self.mono_service.get_transactions(start_date=start_from.strftime('%d-%m-%Y'),
                                                               end_date=datetime.now().strftime('%d-%m-%Y'),
                                                               account_id=account.account_id)
        if transactions_data is None:
            return False
        return self.upsert_transactions_from_mono(account_id, transactions_data)

    def upsert_transactions_from_mono(self, account_id: int, transactions_data: list[dict]) -> bool:
        """
        Upsert transactions from Mono API data into the database.
        :param account_id: ID of the account to associate transactions with.
        :param transactions_data: List of transaction data dictionaries from Mono API.
        :return: True if successful, False otherwise.
        """
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            print(f"Account with ID {account_id} not found.")
            return False
        if transactions_data is None:
            return False
        # Ensure transactions_data is a list
        if not isinstance(transactions_data, list):
            print("Transactions data is not a list.")
            return False
        print(f"Upserting transactions for account: {account.account_number}, "
              f"Number of transactions: {len(transactions_data)}")
        for transaction_data in transactions_data:

            existing_transaction = self.db.query(Transaction).filter(
                Transaction.transaction_id == transaction_data['id']).filter(
                Transaction.account_id == account.id).first()
            print(f"Processing transaction ID: {transaction_data} for account: {account.account_number}")
            if existing_transaction:
                # Update existing transaction
                continue
            amount = abs((transaction_data.get('amount', 0.0) or 0.0) / 100)
            # Create a new transaction
            new_transaction = Transaction(
                transaction_id=transaction_data['id'],
                account_id=account.id,
                amount=(transaction_data.get('amount', 0.0) or 0.0) / 100,
                currency=transaction_data.get('currency', 'NGN') or 'NGN',
                description=transaction_data.get('narration', ''),
                date=transaction_data['date'],
                balance_after_transaction=(transaction_data.get('balance') or 0.0) / 100,
                transaction_type=transaction_data.get('type', 'unknown') or 'unknown'
            )
            self.db.add(new_transaction)
            self.db.commit()
        account.last_synced = datetime.now()
        account.indexed = True
        self.db.commit()
        self.db.refresh(account)
        print(f"Upserted transactions for account: {account.account_number}")
        return True

    def sync_transactions(self, account_id: int) -> bool:
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            print(f"Account with ID {account_id} not found.")
            return False
        # if last synced is less than today, index transactions
        if account.last_synced and account.last_synced >= datetime.now() - relativedelta(days=1):
            print(f"Account with ID {account_id} is already synced within the last 24 hours.")
            return True

        print(f"Account with ID {account_id} is not indexed. Indexing now...")
        return self.index_transactions(account_id,
                                       start_from=account.last_synced or datetime.now() - relativedelta(months=3))

    def get_account_transactions(self, account_id: int, skip: int = 0, limit: int = 500):
        account = self.db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return None
        return self.db.query(Transaction).filter(Transaction.account_id == account_id).offset(skip).limit(limit).all()

    def get_transactions(self, user_id: int, start_date: datetime, end_date: datetime, skip: int = 0,
                         limit: int = 50) -> list[TransactionOut]:
        query = self.db.query(Transaction).join(Account)
        query = query.filter(Account.user_id == user_id).filter(Account.active == True)
        query = query.filter(Transaction.date >= start_date).filter(Transaction.date <= end_date)
        query = query.order_by(Transaction.date.desc()).offset(skip).limit(limit)
        transactions = query.all()

        data: list[TransactionOut] = []
        for transaction in transactions:
            a_transaction = TransactionOut(
                account_id=transaction.account_id,
                amount=transaction.amount,
                description=transaction.description,
                date=str(transaction.date),
                currency=transaction.currency,
                transaction_id=transaction.transaction_id,
                id=transaction.id,
                category_id=transaction.category_id,
                transaction_type=transaction.transaction_type,
                account=AccountOut(
                    id=transaction.account.id,
                    account_id=transaction.account.account_id,
                    account_name=transaction.account.account_name,
                    active=transaction.account.active,
                    account_number=transaction.account.account_number,
                    account_type=transaction.account.account_type,
                    currency=transaction.account.currency,
                    current_balance=transaction.account.current_balance,
                    bank_id=transaction.account.bank_id
                )
            )
            data.append(a_transaction)

        return data
    def search(self, user_id: int, params: TransactionSearch) -> list[TransactionOut]:
        query = self.db.query(Transaction).join(Account).join(Category)
        query = query.filter(Account.user_id == user_id)
        query = query.filter(Transaction.date >= params.start_date).filter(Transaction.date <= params.end_date)
        if params.account_id:
            query = query.filter(Transaction.account_id == params.account_id)
        if params.category_id:
            query = query.filter(Transaction.category_id == params.category_id)
        if params.text:
            query = query.filter(Transaction.description.ilike(f"%{params.text}%"))

        query = query.order_by(Transaction.date.desc()).offset(params.skip).limit(params.limit)
        transactions = query.all()

        data: list[TransactionOut] = []
        for transaction in transactions:
            a_transaction = TransactionOut(
                account_id=transaction.account_id,
                amount=transaction.amount,
                description=transaction.description,
                date=str(transaction.date),
                currency=transaction.currency,
                transaction_id=transaction.transaction_id,
                id=transaction.id,
                category_id=transaction.category_id,
                transaction_type=transaction.transaction_type,
                account=AccountOut(
                    id=transaction.account.id,
                    account_id=transaction.account.account_id,
                    account_name=transaction.account.account_name,
                    active=transaction.account.active,
                    account_number=transaction.account.account_number,
                    account_type=transaction.account.account_type,
                    currency=transaction.account.currency,
                    current_balance=transaction.account.current_balance,
                    bank_id=transaction.account.bank_id
                ),
                category=CategoryOut(
                    id=transaction.category.id,
                    name=transaction.category.name,
                    description=transaction.category.description
                )
            )
            data.append(a_transaction)
        print(f"Found {len(data)} transactions matching the search criteria.")
        return data

    def get_spending_categories(self, user_id: int) -> list[CategoryOut]:
        pass

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

    def categorize_transactions(self) -> bool:
        try:

            transactions = self.db.query(Transaction).filter(Transaction.category_id.is_(None)).all()
            print(f"Found {len(transactions)} transactions to categorize.")
            categories = self.db.query(Category).all()
            if not transactions:
                print("No transactions to categorize.")
                return True

            for transaction in transactions:
                # Here you would implement your logic to categorize the transaction
                # For example, you could use a machine learning model or a set of rules
                # For now, we'll just print the transaction
                print(f"Categorizing transaction: {transaction.id} - {transaction.description}")
                # Example categorization logic (to be replaced with actual logic)
                category_id = self.ai_service.categorize_transaction(transaction, categories)
                transaction.category_id = category_id
                self.db.commit()
                self.db.refresh(transaction)
                time.sleep(5)

            return True
        except Exception as e:
            print(f"Error categorizing transactions: {e}")
            return False

    def delete_transaction(self, transaction_id: int):
        db_transaction = self.get_transaction(transaction_id)
        if not db_transaction:
            return None
        self.db.delete(db_transaction)
        self.db.commit()
        return db_transaction

    async def get_institutions(self) -> list[dict[str, any]]:
        data = await cache_service.get_cache('institutions')
        if data:
            data = json.loads(data)
            institutions_data = [MonoInstitutionData(**institution).model_dump() for institution in data]
            return institutions_data

        institutions_data = self.mono_service.get_institutions()
        if not institutions_data:
            print("No institutions found.")
            return []

        # get bank with institution id and insert into bank table if not exists
        result: list[dict[str, any]] = []
        for institution in institutions_data:
            mono_data = MonoInstitutionData(**institution)
            bank = self.db.query(Bank).filter(Bank.institution_id == mono_data.id).first()
            if not bank:
                new_bank = Bank(
                    institution_id=mono_data.id,
                    bank_name=mono_data.institution,
                    bank_code=mono_data.bank_code or '',
                    bank_account_type=mono_data.type or '',
                    auth_method=mono_data.auth_methods[0].type or 'internet_banking',
                    image_url=''
                )
                self.db.add(new_bank)
                self.db.commit()
                self.db.refresh(new_bank)
                print(f"Inserted new bank: {new_bank.bank_name} with institution ID: {institution['id']}")
            result.append(mono_data)
        await cache_service.set_cache('institutions', json.dumps(institutions_data), expire_seconds=86400)

        return result

    def generate_transaction_embeddings(self) -> bool:
        # categoryid is not none
        print("Generating embeddings for transactions...")
        transactions = self.db.query(Transaction).filter(
            Transaction.embedding.is_(None) & Transaction.category_id.is_not(None)).all()
        print(f"Found {len(transactions)} transactions to generate embeddings for.")
        if not transactions:
            print(f"No unembedded transactions found.")
            return True

        for transaction in transactions:
            # embed the transaction description category name amount type and date
            data = self.db.execute(text(f"SELECT * from data_view where transaction_id={transaction.id}")).fetchone()

            # Prepare the text to embed
            text_to_embed = (f"{data.transaction_description.lower()}. "
                             f"Category: {data.category_name} — {data.category_description}. "
                             f"Type: {data.transaction_type}. "
                             f"Date: {data.transaction_date.strftime('%B %d, %Y')}. "
                             f"From a {data.account_type} account in {transaction.currency}.")

            print(f"Generating embedding for transaction ID {transaction.id} with text: {text_to_embed}")
            # Generate embeddings for the transaction description
            embedding = self.ai_service.generate_embedding(text_to_embed)
            if not embedding:
                print(f"Failed to generate embedding for transaction ID {transaction.id}.")
                return False

            # Store the embedding in the database
            transaction.embedding = embedding
            self.db.commit()

        print(f"Generated and stored embedding for transaction ID {transaction.id}.")
        return True
