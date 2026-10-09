import logging

from motor.motor_asyncio import AsyncIOMotorClient

from .config import settings

log = logging.getLogger("touchgrass.db")

client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=4000)
db = client[settings.mongodb_db]
images = db["images"]
stories = db["stories"]


async def init_db() -> bool:
    """Create indexes. Returns False (without crashing) if MongoDB is unreachable."""
    try:
        await images.create_index("created_at", expireAfterSeconds=settings.image_ttl_seconds)
        await images.create_index("session_id")
        await stories.create_index("created_at")
        await stories.create_index("expire_at", expireAfterSeconds=0)  # private stories auto-delete
        await stories.create_index([("public", 1), ("created_at", -1)])
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("MongoDB not reachable at %s (%s)", settings.mongodb_uri, e)
        return False
