from abc import ABC, abstractmethod
from typing import Optional

class ICacheProvider(ABC):
    """
    Interface for cache and ephemeral state management.
    Can be implemented via Redis or an In-Memory Dict fallback.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Gets value by key."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """Sets key to value with optional TTL (time-to-live) in seconds."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Deletes key from cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Checks if key exists in cache."""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clears all cached elements (used for session cleanup or testing)."""
        pass
