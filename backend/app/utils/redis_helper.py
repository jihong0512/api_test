from typing import Optional

from redis import Redis

from app.config import settings


_redis_client: Optional[Redis] = None


def get_redis_client() -> Redis:
    """Return a singleton Redis client (decode responses enabled)."""

    global _redis_client
    if _redis_client is None:
        _redis_client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,
        )
    return _redis_client




