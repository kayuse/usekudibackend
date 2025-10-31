from datetime import datetime

from app.database.index import get_db
from app.services.account_service import AccountService
from app.services.transaction_service import TransactionService
from app.workers.celery_app import celery_app


@celery_app.task(name='auto_fetch_transactions', bind=True, max_retries=10, default_retry_delay=60)
def auto_fetch_transactions(self):
    print("Running auto fetch transactions...")
    try:
        db = next(get_db())
        print(f"Starting task to fetch transactions")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = AccountService(db_session=db)
        accounts = service.resync_transactions()

        print("Account Syncs completed successfully.", accounts)
    except Exception as e:
        print(f"Error during auto fetch transactions: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()



@celery_app.task(name='get_latest_currency', bind=True, max_retries=5, default_retry_delay=300)
def get_latest_currency(self):
    print("Running get latest currency...")
    try:
        db = next(get_db())
        print(f"Database session: {db}")
        service = AccountService(db_session=db)
        latest_currency = service.get_latest_currency()
        print("Latest currency fetched successfully.", latest_currency)
    except Exception as e:
        print(f"Error during get latest currency: {e}")
        self.retry(exc=e, countdown=60)
    finally:
        db.close()  