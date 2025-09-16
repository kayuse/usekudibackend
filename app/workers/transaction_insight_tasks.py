from datetime import datetime

from app.services.transaction_ai_service import TransactionAIService
from app.services.transaction_service import TransactionService
from app.database.index import get_db
from celery import shared_task

from app.workers.celery_app import celery_app




@celery_app.task(name='auto_generate_insights', bind=True, max_retries=10, default_retry_delay=60)
def auto_generate_insights(self):
    # Fetch uncategorized transactions from DB
    # Call your LangChain classifier
    # Update category_id in DB
    print("Running auto insights task...")
    try:
        db = next(get_db())
        print(f"Starting task to categorize un categorized transactions")
        print(f"Database session: {db}")
        # Simulate fetching transactions
        service = TransactionAIService(db_session=db)
        result = service.categorize_transactions()
        if not result:
            raise self.retry(countdown=60)
        print("Auto classification completed successfully.")
    except Exception as e:
        print(e)
        print(f"Error during auto classification: {e}")
    finally:
        db.close()
