from redis import Redis
import os
from dotenv import load_dotenv

load_dotenv(override=True)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis = Redis.from_url(REDIS_URL, decode_responses=True)


def get_redis():
    return redis
