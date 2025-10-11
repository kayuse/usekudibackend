from app.util.redis import redis,get_redis

async def set_cache(key: str, value: str, expire_seconds: int = 600):
    redis.set(key, value, ex=expire_seconds)
    return True

async def get_cache(key: str) -> str | None:
    try:
        print(f"Fetching for key {key}")
        return redis.get(key)
    except Exception as e:
        print(f"Error fetching cache for key {key}: {e}")
        return None

async def delete_cache(key: str):
    try:
        print(f"Deleting cache for key: {key}")
        redis.delete(key)
    except Exception as e:
        print(f"Error deleting cache for key {key}: {e}")
        

async def publish(key, data: str) -> bool:
    try:
        print(f"Publishing data to key {key}")
        redis.publish(key, data)
        return True
    except Exception as e:
        print(f"Error publishing data to key {key}: {e}")
        return False