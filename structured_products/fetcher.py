"""
Yahoo Finance price fetcher for structured products.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
import yfinance as yf


def fetch_historical_prices(
    symbol: str,
    dates: List[str],
    lookback_days: int = 7
) -> Dict[str, Optional[Dict[str, float]]]:
    """
    Fetch historical prices for a symbol on or prior to specified dates.

    Args:
        symbol: Yahoo Finance symbol (e.g., "^GSPC")
        dates: List of ISO-formatted date strings (YYYY-MM-DD)
        lookback_days: Number of days to look back if no data on exact date

    Returns:
        Dictionary mapping date strings to price data:
        {
            "2024-01-15": {
                "actual_date": "2024-01-12",  # May differ if market closed
                "open": 4783.45,
                "high": 4850.43,
                "low": 4780.05,
                "close": 4839.81,
                "volume": 3500000000
            }
        }
    """
    if not dates:
        return {}

    results = {}

    # Parse all dates
    date_objects = []
    for date_str in dates:
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_objects.append((date_str, date_obj))
        except ValueError:
            results[date_str] = None
            continue

    if not date_objects:
        return results

    # Find the date range to fetch
    min_date = min(dt for _, dt in date_objects)
    max_date = max(dt for _, dt in date_objects)

    # Add lookback buffer
    start_date = min_date - timedelta(days=lookback_days)
    end_date = max_date + timedelta(days=1)  # yfinance end date is exclusive

    try:
        # Fetch historical data
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            # No data available for this symbol
            for date_str, _ in date_objects:
                results[date_str] = None
            return results

        # For each requested date, find the closest prior trading day
        for date_str, target_date in date_objects:
            price_data = find_price_on_or_before(hist, target_date, lookback_days)
            results[date_str] = price_data

    except Exception as e:
        # Handle any errors (invalid symbol, network issues, etc.)
        print(f"Error fetching data for {symbol}: {e}")
        for date_str, _ in date_objects:
            results[date_str] = None

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
        Dictionary with price data or None if not found
    """
    # Filter to dates on or before target
    valid_dates = hist_data[hist_data.index <= target_date]

    if valid_dates.empty:
        return None

    # Get the most recent date within lookback window
    earliest_date = target_date - timedelta(days=max_lookback)
    valid_dates = valid_dates[valid_dates.index >= earliest_date]

    if valid_dates.empty:
        return None

    # Get the most recent row
    most_recent = valid_dates.iloc[-1]
    actual_date = most_recent.name

    return {
        "actual_date": actual_date.strftime("%Y-%m-%d"),
        "open": float(most_recent["Open"]),
        "high": float(most_recent["High"]),
        "low": float(most_recent["Low"]),
        "close": float(most_recent["Close"]),
        "volume": int(most_recent["Volume"]),
    }


def fetch_prices_for_multiple_symbols(
    symbols: List[str],
    dates: List[str],
    lookback_days: int = 7
) -> Dict[str, Dict[str, Optional[Dict[str, float]]]]:
    """
    Fetch historical prices for multiple symbols.

    Args:
        symbols: List of Yahoo Finance symbols
        dates: List of ISO-formatted date strings
        lookback_days: Number of days to look back if no data on exact date

    Returns:
        Dictionary mapping symbols to their price data
    """
    results = {}
    for symbol in symbols:
        results[symbol] = fetch_historical_prices(symbol, dates, lookback_days)
    return results
