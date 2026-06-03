"""Redis client for caching market data and LLM responses."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from astock_agent_system.config import Settings, load_settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client for caching."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazy load Redis client."""
        if self._client is not None:
            return self._client

        try:
            import redis
        except ImportError as exc:
            raise ImportError(
                "redis is not installed. Run: pip install -e .[storage]"
            ) from exc

        redis_url = self.settings.storage.redis_url
        self._client = redis.from_url(redis_url, decode_responses=True)
        
        # Test connection
        self._client.ping()
        logger.info(f"Redis connected: {redis_url}")
        return self._client

    def get(self, key: str) -> str | None:
        """Get value from cache."""
        try:
            client = self._get_client()
            return client.get(key)
        except Exception as exc:
            logger.warning(f"Redis get failed for {key}: {exc}")
            return None

    def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Set value in cache with optional TTL (seconds)."""
        try:
            client = self._get_client()
            if ttl:
                return client.setex(key, ttl, value)
            return client.set(key, value)
        except Exception as exc:
            logger.warning(f"Redis set failed for {key}: {exc}")
            return False

    def get_json(self, key: str) -> dict[str, Any] | list[Any] | None:
        """Get JSON value from cache."""
        value = self.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON from cache key: {key}")
            return None

    def set_json(self, key: str, value: dict[str, Any] | list[Any], ttl: int | None = None) -> bool:
        """Set JSON value in cache."""
        try:
            json_str = json.dumps(value, ensure_ascii=False)
            return self.set(key, json_str, ttl)
        except Exception as exc:
            logger.warning(f"Failed to serialize JSON for cache key {key}: {exc}")
            return False

    def cache_market_data(
        self,
        stock_code: str,
        data_type: str,
        data: Any,
        ttl: int = 60
    ) -> bool:
        """Cache market data (quote, history, financial).
        
        Args:
            stock_code: Stock code
            data_type: 'quote', 'history', 'financial'
            data: Data to cache
            ttl: Time to live in seconds (default 60s for market data)
        """
        key = f"market:{data_type}:{stock_code}"
        return self.set_json(key, data, ttl)

    def get_market_data(
        self,
        stock_code: str,
        data_type: str
    ) -> dict[str, Any] | list[Any] | None:
        """Get cached market data."""
        key = f"market:{data_type}:{stock_code}"
        return self.get_json(key)

    def cache_llm_response(
        self,
        prompt: str,
        model: str,
        response: dict[str, Any],
        ttl: int = 3600
    ) -> bool:
        """Cache LLM response.
        
        Args:
            prompt: The prompt sent to LLM
            model: Model name
            response: LLM response
            ttl: Time to live in seconds (default 1 hour)
        """
        # Create hash of prompt + model as cache key
        key_str = f"{model}:{prompt}"
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]
        key = f"llm:{key_hash}"
        return self.set_json(key, response, ttl)

    def get_llm_response(
        self,
        prompt: str,
        model: str
    ) -> dict[str, Any] | None:
        """Get cached LLM response."""
        key_str = f"{model}:{prompt}"
        key_hash = hashlib.sha256(key_str.encode()).hexdigest()[:16]
        key = f"llm:{key_hash}"
        return self.get_json(key)

    def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        try:
            client = self._get_client()
            return bool(client.delete(key))
        except Exception as exc:
            logger.warning(f"Redis delete failed for {key}: {exc}")
            return False

    def clear_pattern(self, pattern: str) -> int:
        """Delete all keys matching a pattern.
        
        Args:
            pattern: Redis key pattern (e.g., 'market:*', 'llm:*')
        
        Returns:
            Number of keys deleted
        """
        try:
            client = self._get_client()
            keys = client.keys(pattern)
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning(f"Redis clear_pattern failed for {pattern}: {exc}")
            return 0

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        try:
            client = self._get_client()
            info = client.info('stats')
            return {
                "total_commands_processed": info.get('total_commands_processed', 0),
                "keyspace_hits": info.get('keyspace_hits', 0),
                "keyspace_misses": info.get('keyspace_misses', 0),
                "hit_rate": (
                    info.get('keyspace_hits', 0) / 
                    max(info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0), 1)
                )
            }
        except Exception as exc:
            logger.warning(f"Failed to get Redis stats: {exc}")
            return {}

    def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            self._client.close()
            logger.info("Redis connection closed")
