from datetime import datetime

from app.services.transaction_service import TransactionService
from app.database.index import get_db
from celery import shared_task

from app.workers.celery_app import celery_app


@shared_task(bind=True, max_retries=10, default_retry_delay=60)
def fetch_initial_transactions(self, account_id: int):
    try:
        db = next(get_db())
        print(f"Starting task to fetch initial transactions for account: {account_id}")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = TransactionService(db_session=db)
        result = service.index_transactions(account_id=account_id)
        if not result:
            raise self.retry(countdown=60)
        print(f"Fetching initial transactions for account: {account_id}")
        # service = AccountService(db_session=db)

        # Here you would implement the logic to fetch transactions from an external API
        # For now, we just simulate a delay
        print(f"Fetched initial transactions for account: {account_id}")
    finally:
        db.close()


@celery_app.task(name='auto_classify_transactions', bind=True, max_retries=10, default_retry_delay=60)
def auto_classify_transactions(self):
    # Fetch uncategorized transactions from DB
    # Call your LangChain classifier
    # Update category_id in DB
    print("Running auto classification...")
    try:
        db = next(get_db())
        print(f"Starting task to categorize un categorized transactions")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = TransactionService(db_session=db)
        result = service.categorize_transactions()
        if not result:
            raise self.retry(countdown=60)
        print("Auto classification completed successfully.")
    except Exception as e:
        print(e)
        print(f"Error during auto classification: {e}")
    finally:
        db.close()

@celery_app.task(name='generate_transaction_embeddings', bind=True, max_retries=10, default_retry_delay=60)
def generate_transaction_embeddings(self):
    print("Running transaction embeddings generation...")
    try:
        db = next(get_db())
        print(f"Starting task to generate transaction embeddings")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = TransactionService(db_session=db)
        result =  service.generate_transaction_embeddings()
        if not result:
            raise self.retry(countdown=60)
        print("Auto embeddings completed successfully.")
    except Exception as e:
        print(e)
        print(f"Error during auto embeddings: {e}")
    finally:
        db.close()


@celery_app.task(name='sync_account_transactions', bind=True, max_retries=10, default_retry_delay=60)
def sync_account_transactions(self, account_id: int, start_from: datetime):
    print("Running auto fetch transactions...")
    try:
        db = next(get_db())
        print(f"Starting task to fetch transactions")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = TransactionService(db_session=db)

        is_synced = service.index_transactions(account_id, start_from)
        if not is_synced:
            raise self.retry(countdown=60)

        print("Account Transaction Sync completed successfully.")
    except Exception as e:
        print(f"Error during auto fetch transactions: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()
