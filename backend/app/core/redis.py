from redis.asyncio import Redis

from app.core.config import settings

# Single shared async client. `from_url` handles the rediss:// (TLS) scheme
# automatically. decode_responses=True so reads come back as str, not bytes.
redis_client: Redis = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)
