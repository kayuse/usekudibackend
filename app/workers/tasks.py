from app.services.transaction_service import TransactionService
from app.database.index import get_db
from celery import shared_task


@shared_task
def fetch_initial_transactions(account_id : int):
    
    try:
        db = next(get_db())
        print(f"Starting task to fetch initial transactions for account: {account_id}")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = TransactionService(db_session=db)
        result = service.index_transactions(account_id=account_id)
        print(f"Fetching initial transactions for account: {account_id}")
        # service = AccountService(db_session=db)
        
        # Here you would implement the logic to fetch transactions from an external API
        # For now, we just simulate a delay
        import time
        time.sleep(1)
        print(f"Fetched initial transactions for account: {account_id}")
    finally:
        db.close()