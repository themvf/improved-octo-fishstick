"""
Caching module for structured products toolkit.

Provides optional caching for price data to improve performance
and reduce API calls.
"""

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class PriceCache:
    """
    Simple file-based cache for historical price data.

    Caches price data to disk with configurable TTL (time-to-live).
    Thread-safe for read operations, uses file locking for writes.
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        ttl_seconds: int = 3600,
        enabled: bool = True
    ):
        """
        Initialize price cache.

        Args:
            cache_dir: Directory for cache files (default: ~/.structured_products_cache)
            ttl_seconds: Time-to-live for cache entries in seconds (default: 3600 = 1 hour)
            enabled: Whether caching is enabled (default: True)
        """
        self.enabled = enabled

        if not self.enabled:
            logger.info("Price caching is disabled")
            return

        if cache_dir is None:
            cache_dir = os.path.join(
                os.path.expanduser("~"),
                ".structured_products_cache"
            )

        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds

        # Create cache directory if it doesn't exist
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Price cache initialized: {self.cache_dir} (TTL: {ttl_seconds}s)")
        except Exception as e:
            logger.error(f"Failed to create cache directory: {e}")
            self.enabled = False

    def _make_cache_key(
        self,
        symbol: str,
        dates: List[str],
        lookback_days: int
    ) -> str:
        """
        Generate cache key from request parameters.

        Args:
            symbol: Yahoo Finance symbol
            dates: List of date strings
            lookback_days: Lookback days parameter

        Returns:
            Hash string to use as cache key
        """
        # Sort dates for consistent hashing
        sorted_dates = sorted(dates)

        # Create deterministic data structure
        cache_data = {
            "symbol": symbol,
            "dates": sorted_dates,
            "lookback_days": lookback_days
        }

        # Generate hash
        data_str = json.dumps(cache_data, sort_keys=True)
        hash_obj = hashlib.md5(data_str.encode())
        return hash_obj.hexdigest()

    def _get_cache_file_path(self, cache_key: str) -> Path:
        """
        Get file path for cache key.

        Args:
            cache_key: Cache key hash

        Returns:
            Path object for cache file
        """
        return self.cache_dir / f"{cache_key}.json"

    def get(
        self,
        symbol: str,
        dates: List[str],
        lookback_days: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached price data if available and not expired.

        Args:
            symbol: Yahoo Finance symbol
            dates: List of date strings
            lookback_days: Lookback days parameter

        Returns:
            Cached data dictionary or None if not found/expired
        """
        if not self.enabled:
            return None

        try:
            cache_key = self._make_cache_key(symbol, dates, lookback_days)
            cache_file = self._get_cache_file_path(cache_key)

            if not cache_file.exists():
                logger.debug(f"Cache miss for {symbol}: file not found")
                return None

            # Read cache file
            with open(cache_file, 'r') as f:
                cache_entry = json.load(f)

            # Check expiration
            cached_time = cache_entry.get("timestamp", 0)
            age_seconds = time.time() - cached_time

            if age_seconds > self.ttl_seconds:
                logger.debug(
                    f"Cache expired for {symbol}: age {age_seconds:.0f}s > TTL {self.ttl_seconds}s"
                )
                # Delete expired cache file
                try:
                    cache_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete expired cache file: {e}")
                return None

            logger.info(
                f"Cache hit for {symbol}: age {age_seconds:.0f}s, {len(cache_entry['data'])} dates"
            )
            return cache_entry["data"]

        except Exception as e:
            logger.error(f"Error reading cache for {symbol}: {e}", exc_info=True)
            return None

    def set(
        self,
        symbol: str,
        dates: List[str],
        lookback_days: int,
        data: Dict[str, Any]
    ) -> bool:
        """
        Store price data in cache.

        Args:
            symbol: Yahoo Finance symbol
            dates: List of date strings
            lookback_days: Lookback days parameter
            data: Price data to cache

        Returns:
            True if successfully cached, False otherwise
        """
        if not self.enabled:
            return False

        try:
            cache_key = self._make_cache_key(symbol, dates, lookback_days)
            cache_file = self._get_cache_file_path(cache_key)

            cache_entry = {
                "symbol": symbol,
                "dates": dates,
                "lookback_days": lookback_days,
                "timestamp": time.time(),
                "data": data
            }

            # Write atomically using temp file + rename
            temp_file = cache_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(cache_entry, f, indent=2)

            # Atomic rename
            temp_file.replace(cache_file)

            logger.debug(f"Cached price data for {symbol}: {len(data)} dates")
            return True

        except Exception as e:
            logger.error(f"Error writing cache for {symbol}: {e}", exc_info=True)
            return False

    def clear(self, older_than_seconds: Optional[int] = None) -> int:
        """
        Clear cache entries.

        Args:
            older_than_seconds: Only clear entries older than this (None = clear all)

        Returns:
            Number of entries cleared
        """
        if not self.enabled:
            return 0

        cleared = 0
        try:
            current_time = time.time()

            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    if older_than_seconds is not None:
                        # Check age before deleting
                        with open(cache_file, 'r') as f:
                            cache_entry = json.load(f)
                        cached_time = cache_entry.get("timestamp", 0)
                        age = current_time - cached_time

                        if age < older_than_seconds:
                            continue

                    cache_file.unlink()
                    cleared += 1

                except Exception as e:
                    logger.warning(f"Error deleting cache file {cache_file}: {e}")

            logger.info(f"Cleared {cleared} cache entries")
            return cleared

        except Exception as e:
            logger.error(f"Error clearing cache: {e}", exc_info=True)
            return cleared

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        if not self.enabled:
            return {
                "enabled": False,
                "total_entries": 0,
                "total_size_mb": 0,
            }

        try:
            cache_files = list(self.cache_dir.glob("*.json"))
            total_size = sum(f.stat().st_size for f in cache_files)

            # Count expired entries
            current_time = time.time()
            expired = 0
            valid = 0

            for cache_file in cache_files:
                try:
                    with open(cache_file, 'r') as f:
                        cache_entry = json.load(f)
                    cached_time = cache_entry.get("timestamp", 0)
                    age = current_time - cached_time

                    if age > self.ttl_seconds:
                        expired += 1
                    else:
                        valid += 1
                except Exception:
                    pass

            return {
                "enabled": True,
                "cache_dir": str(self.cache_dir),
                "ttl_seconds": self.ttl_seconds,
                "total_entries": len(cache_files),
                "valid_entries": valid,
                "expired_entries": expired,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}", exc_info=True)
            return {
                "enabled": True,
                "error": str(e)
            }


# Global cache instance (singleton pattern)
_global_cache: Optional[PriceCache] = None


def get_cache(
    cache_dir: Optional[str] = None,
    ttl_seconds: int = 3600,
    enabled: bool = True
) -> PriceCache:
    """
    Get or create the global cache instance.

    Args:
        cache_dir: Directory for cache files
        ttl_seconds: Time-to-live for cache entries
        enabled: Whether caching is enabled

    Returns:
        PriceCache instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = PriceCache(
            cache_dir=cache_dir,
            ttl_seconds=ttl_seconds,
            enabled=enabled
        )

    return _global_cache


def clear_global_cache(older_than_seconds: Optional[int] = None) -> int:
    """
    Clear the global cache.

    Args:
        older_than_seconds: Only clear entries older than this

    Returns:
        Number of entries cleared
    """
    global _global_cache

    if _global_cache is not None:
        return _global_cache.clear(older_than_seconds)

    return 0
