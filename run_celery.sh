celery -A app.workers.worker worker --loglevel=info --pool=solo
