"""
Yahoo Finance price fetcher for structured products.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import Dict, List, Optional
from datetime import datetime, timedelta

import yfinance as yf
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

from .cache import get_cache

logger = logging.getLogger(__name__)


def rate_limit(calls_per_second: float = 2.0):
    """
    Rate limiting decorator to avoid API throttling.

    Yahoo Finance has rate limits. This ensures we don't exceed them.

    Args:
        calls_per_second: Maximum number of calls per second (default: 2.0)
    """
    min_interval = 1.0 / calls_per_second
    last_call = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Calculate time since last call
            elapsed = time.time() - last_call[0]

            # Sleep if we're calling too fast
            if elapsed < min_interval:
                sleep_time = min_interval - elapsed
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)

            # Update last call time and execute
            last_call[0] = time.time()
            return func(*args, **kwargs)

        return wrapper
    return decorator


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((Exception,)),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True
)
@rate_limit(calls_per_second=2.0)
def fetch_historical_prices(
    symbol: str,
    dates: List[str],
    lookback_days: int = 7,
    use_cache: bool = True
) -> Dict[str, Optional[Dict[str, float]]]:
    """
    Fetch historical prices for a symbol on or prior to specified dates.

    Uses adjusted close prices which account for stock splits and dividends.
    Includes automatic retry logic with exponential backoff and optional caching.

    Args:
        symbol: Yahoo Finance symbol (e.g., "^GSPC")
        dates: List of ISO-formatted date strings (YYYY-MM-DD)
        lookback_days: Number of days to look back if no data on exact date
        use_cache: Whether to use caching (default: True)

    Returns:
        Dictionary mapping date strings to price data:
        {
            "2024-01-15": {
                "actual_date": "2024-01-12",  # May differ if market closed
                "open": 4783.45,
                "high": 4850.43,
                "low": 4780.05,
                "close": 4839.81,
                "adj_close": 4839.81,  # Use this for financial calculations
                "volume": 3500000000
            }
        }
    """
    if not dates:
        logger.warning("No dates provided for fetching")
        return {}

    # Check cache first
    if use_cache:
        cache = get_cache()
        cached_data = cache.get(symbol, dates, lookback_days)
        if cached_data is not None:
            logger.info(f"Using cached prices for {symbol}")
            return cached_data

    logger.info(f"Fetching prices for {symbol} on {len(dates)} dates")
    results = {}

    # Parse all dates
    date_objects = []
    for date_str in dates:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_objects.append((date_str, date_obj))
        except ValueError as e:
            logger.error(f"Invalid date format '{date_str}': {e}")
            results[date_str] = None
            continue

    if not date_objects:
        logger.error("No valid dates to fetch")
        return results

    # Find the date range to fetch
    min_date = min(dt for _, dt in date_objects)
    max_date = max(dt for _, dt in date_objects)

    # Add lookback buffer
    start_date = min_date - timedelta(days=lookback_days)
    end_date = max_date + timedelta(days=1)  # yfinance end date is exclusive

    logger.debug(f"Fetching data from {start_date.date()} to {end_date.date()}")

    try:
        # Fetch historical data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            # No data available for this symbol
            logger.warning(f"No historical data available for {symbol}")
            for date_str, _ in date_objects:
                results[date_str] = None
            return results

        logger.info(f"Retrieved {len(hist)} trading days for {symbol}")

        # For each requested date, find the closest prior trading day
        for date_str, target_date in date_objects:
            price_data = find_price_on_or_before(hist, target_date, lookback_days)
            if price_data:
                logger.debug(f"Found price for {date_str}: actual date {price_data['actual_date']}")
            else:
                logger.warning(f"No price data found for {date_str} within {lookback_days} day lookback")
            results[date_str] = price_data

    except Exception as e:
        # Handle any errors (invalid symbol, network issues, etc.)
        logger.error(
            f"Error fetching data for {symbol}: {e}",
            extra={
                "symbol": symbol,
                "dates": dates,
                "lookback_days": lookback_days
            },
            exc_info=True
        )
        for date_str, _ in date_objects:
            results[date_str] = None
        raise  # Re-raise for retry logic

    # Store in cache if enabled
    if use_cache:
        cache = get_cache()
        cache.set(symbol, dates, lookback_days, results)

    return results


def find_price_on_or_before(
    hist_data,
    target_date: datetime,
    max_lookback: int = 7
) -> Optional[Dict[str, float]]:
    """
    Find price data on or before the target date.

    Args:
        hist_data: DataFrame from yfinance with historical prices
        target_date: The target date to find prices for
        max_lookback: Maximum days to look back

    Returns:
        Dictionary with price data including adj_close for calculations
    """
    # Filter to dates on or before target
    valid_dates = hist_data[hist_data.index <= target_date]

    if valid_dates.empty:
        logger.debug(f"No data on or before {target_date.date()}")
        return None

    # Get the most recent date within lookback window
    earliest_date = target_date - timedelta(days=max_lookback)
    valid_dates = valid_dates[valid_dates.index >= earliest_date]

    if valid_dates.empty:
        logger.debug(f"No data within {max_lookback} days of {target_date.date()}")
        return None

    # Get the most recent row
    most_recent = valid_dates.iloc[-1]
    actual_date = most_recent.name

    # CRITICAL: Use Adj Close for financial calculations
    # This accounts for stock splits and dividends
    return {
        "actual_date": actual_date.strftime("%Y-%m-%d"),
        "open": float(most_recent["Open"]),
        "high": float(most_recent["High"]),
        "low": float(most_recent["Low"]),
        "close": float(most_recent["Close"]),
        "adj_close": float(most_recent["Adj Close"]),  # Use this for calculations!
        "volume": int(most_recent["Volume"]),
    }


def fetch_prices_for_multiple_symbols(
    symbols: List[str],
    dates: List[str],
    lookback_days: int = 7,
    max_workers: int = 5,
    use_cache: bool = True
) -> Dict[str, Dict[str, Optional[Dict[str, float]]]]:
    """
    Fetch historical prices for multiple symbols concurrently.

    Uses ThreadPoolExecutor for parallel fetching, significantly improving
    performance for multiple symbols.

    Args:
        symbols: List of Yahoo Finance symbols
        dates: List of ISO-formatted date strings
        lookback_days: Number of days to look back if no data on exact date
        max_workers: Maximum concurrent requests (default: 5)
        use_cache: Whether to use caching (default: True)

    Returns:
        Dictionary mapping symbols to their price data
    """
    if not symbols:
        logger.warning("No symbols provided for fetching")
        return {}

    logger.info(f"Fetching prices for {len(symbols)} symbols concurrently (max_workers={max_workers})")
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_symbol = {
            executor.submit(
                fetch_historical_prices,
                symbol,
                dates,
                lookback_days,
                use_cache
            ): symbol
            for symbol in symbols
        }

        # Collect results as they complete
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                results[symbol] = future.result()
                logger.info(f"Successfully fetched prices for {symbol}")
            except Exception as e:
                logger.error(f"Failed to fetch prices for {symbol}: {e}", exc_info=True)
                results[symbol] = {date: None for date in dates}

    return results
