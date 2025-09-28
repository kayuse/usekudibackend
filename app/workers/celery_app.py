from celery import Celery
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from celery.schedules import crontab

load_dotenv()

celery_app = Celery(
    "backend",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

celery_app.conf.timezone = 'Africa/Lagos'

celery_app.conf.beat_schedule = {
    # 'auto-classify-transactions-every-10-mins': {
    #     'task': 'auto_classify_transactions',
    #     'schedule': crontab(minute='*/10'),  # every 10 mins
    # },
    'auto_classify_session_transactions-every-10-mins': {
        'task': 'auto_classify_session_transactions',
        'schedule': crontab(minute='*/20'),  # every 10 mins
    },
    'auto_generate_insights': {
        'task': 'auto_generate_insights',
        'schedule': crontab(minute='*'),  # every minute
    },

}
