from app.services.transaction_service import TransactionService
from app.database.index import get_db
from celery import shared_task


@shared_task(bind=True,max_retries=10,default_retry_delay=60)
def fetch_initial_transactions(self,account_id : int):
    
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