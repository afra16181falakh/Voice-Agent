import time
from typing import Dict, Optional, Tuple
from app.core.interfaces.cache import ICacheProvider

class InMemoryCacheProvider(ICacheProvider):
    """
    In-memory implementation of ICacheProvider for local development without Redis.
    Supports basic TTL eviction on reads.
    """

    def __init__(self):
        # Key -> (Value, Expire Timestamp)
        self._store: Dict[str, Tuple[str, Optional[float]]] = {}

    async def get(self, key: str) -> Optional[str]:
        if key not in self._store:
            return None
        
        value, expire_at = self._store[key]
        if expire_at is not None and time.time() > expire_at:
            # Expired, evict it
            del self._store[key]
            return None
            
        return value

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        expire_at = time.time() + ttl if ttl is not None else None
        self._store[key] = (value, expire_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return (await self.get(key)) is not None

    async def clear(self) -> None:
        self._store.clear()
