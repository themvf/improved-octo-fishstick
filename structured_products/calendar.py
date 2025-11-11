"""
Business day calendar support for structured products.

Handles trading day validation, settlement date calculation,
and market-specific holiday calendars.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Set
from enum import Enum

logger = logging.getLogger(__name__)


class Market(Enum):
    """Supported market calendars."""
    NYSE = "NYSE"  # New York Stock Exchange
    LSE = "LSE"    # London Stock Exchange
    TSE = "TSE"    # Tokyo Stock Exchange
    HKEX = "HKEX"  # Hong Kong Exchange
    SSE = "SSE"    # Shanghai Stock Exchange
    GENERIC = "GENERIC"  # Generic weekday calendar


# US Federal Holidays (fixed dates)
US_FIXED_HOLIDAYS = {
    (1, 1): "New Year's Day",
    (7, 4): "Independence Day",
    (12, 25): "Christmas Day",
}


def is_weekend(date: datetime) -> bool:
    """
    Check if date falls on weekend.

    Args:
        date: Date to check

    Returns:
        True if Saturday or Sunday
    """
    return date.weekday() >= 5  # 5=Saturday, 6=Sunday


def is_us_holiday(date: datetime) -> bool:
    """
    Check if date is a US market holiday.

    Includes major holidays that close US markets.
    Note: This is a simplified implementation. For production,
    use a comprehensive calendar library.

    Args:
        date: Date to check

    Returns:
        True if US holiday
    """
    # Check fixed holidays
    if (date.month, date.day) in US_FIXED_HOLIDAYS:
        return True

    # New Year's Day observed (if Jan 1 is weekend)
    if date.month == 1 and date.day == 2 and date.weekday() == 0:
        # Monday after New Year's on Sunday
        return True

    # Martin Luther King Jr. Day (3rd Monday of January)
    if date.month == 1 and date.weekday() == 0:
        if 15 <= date.day <= 21:
            return True

    # Presidents Day (3rd Monday of February)
    if date.month == 2 and date.weekday() == 0:
        if 15 <= date.day <= 21:
            return True

    # Memorial Day (last Monday of May)
    if date.month == 5 and date.weekday() == 0:
        if date.day >= 25:
            return True

    # Labor Day (1st Monday of September)
    if date.month == 9 and date.weekday() == 0:
        if date.day <= 7:
            return True

    # Thanksgiving (4th Thursday of November)
    if date.month == 11 and date.weekday() == 3:
        if 22 <= date.day <= 28:
            return True

    # Christmas observed (if Dec 25 is weekend)
    if date.month == 12 and date.day == 26 and date.weekday() == 0:
        # Monday after Christmas on Sunday
        return True
    if date.month == 12 and date.day == 24 and date.weekday() == 4:
        # Friday before Christmas on Saturday
        return True

    return False


def is_uk_holiday(date: datetime) -> bool:
    """
    Check if date is a UK market holiday.

    Args:
        date: Date to check

    Returns:
        True if UK holiday
    """
    # Fixed holidays
    if (date.month, date.day) in [(1, 1), (12, 25), (12, 26)]:
        return True

    # Early May Bank Holiday (1st Monday of May)
    if date.month == 5 and date.weekday() == 0 and date.day <= 7:
        return True

    # Spring Bank Holiday (last Monday of May)
    if date.month == 5 and date.weekday() == 0 and date.day >= 25:
        return True

    # Summer Bank Holiday (last Monday of August)
    if date.month == 8 and date.weekday() == 0 and date.day >= 25:
        return True

    return False


def is_trading_day(date: datetime, market: Market = Market.NYSE) -> bool:
    """
    Check if date is a trading day for the specified market.

    Args:
        date: Date to check
        market: Market calendar to use

    Returns:
        True if trading day
    """
    # Check weekend
    if is_weekend(date):
        return False

    # Check market-specific holidays
    if market == Market.NYSE:
        return not is_us_holiday(date)
    elif market == Market.LSE:
        return not is_uk_holiday(date)
    elif market == Market.GENERIC:
        return True  # Any weekday
    else:
        # For other markets, just use weekday check
        # In production, add comprehensive calendar support
        logger.warning(f"No holiday calendar for {market.value}, using weekday check")
        return True


def next_trading_day(
    date: datetime,
    market: Market = Market.NYSE,
    max_days: int = 30
) -> Optional[datetime]:
    """
    Get next trading day after given date.

    Args:
        date: Starting date
        market: Market calendar to use
        max_days: Maximum days to search

    Returns:
        Next trading day or None if not found within max_days
    """
    current = date + timedelta(days=1)
    days_checked = 0

    while days_checked < max_days:
        if is_trading_day(current, market):
            return current
        current += timedelta(days=1)
        days_checked += 1

    logger.warning(f"No trading day found within {max_days} days of {date.date()}")
    return None


def previous_trading_day(
    date: datetime,
    market: Market = Market.NYSE,
    max_days: int = 30
) -> Optional[datetime]:
    """
    Get previous trading day before given date.

    Args:
        date: Starting date
        market: Market calendar to use
        max_days: Maximum days to search

    Returns:
        Previous trading day or None if not found within max_days
    """
    current = date - timedelta(days=1)
    days_checked = 0

    while days_checked < max_days:
        if is_trading_day(current, market):
            return current
        current -= timedelta(days=1)
        days_checked += 1

    logger.warning(f"No trading day found within {max_days} days before {date.date()}")
    return None


def get_settlement_date(
    trade_date: datetime,
    settlement_days: int = 2,
    market: Market = Market.NYSE
) -> datetime:
    """
    Calculate settlement date based on trade date.

    Uses actual trading days, not calendar days.

    Args:
        trade_date: Trade date
        settlement_days: Number of trading days to settlement (default: T+2)
        market: Market calendar to use

    Returns:
        Settlement date
    """
    current = trade_date
    days_added = 0

    while days_added < settlement_days:
        current = next_trading_day(current, market)
        if current is None:
            logger.error(f"Could not calculate settlement date for {trade_date}")
            # Fallback: add calendar days
            return trade_date + timedelta(days=settlement_days)
        days_added += 1

    return current


def get_trading_days_between(
    start_date: datetime,
    end_date: datetime,
    market: Market = Market.NYSE
) -> List[datetime]:
    """
    Get list of trading days between two dates (inclusive).

    Args:
        start_date: Start date
        end_date: End date
        market: Market calendar to use

    Returns:
        List of trading days
    """
    if start_date > end_date:
        start_date, end_date = end_date, start_date

    trading_days = []
    current = start_date

    while current <= end_date:
        if is_trading_day(current, market):
            trading_days.append(current)
        current += timedelta(days=1)

    return trading_days


def count_trading_days_between(
    start_date: datetime,
    end_date: datetime,
    market: Market = Market.NYSE
) -> int:
    """
    Count trading days between two dates (inclusive).

    Args:
        start_date: Start date
        end_date: End date
        market: Market calendar to use

    Returns:
        Number of trading days
    """
    return len(get_trading_days_between(start_date, end_date, market))


def adjust_to_trading_day(
    date: datetime,
    convention: str = "following",
    market: Market = Market.NYSE
) -> datetime:
    """
    Adjust date to nearest trading day using specified convention.

    Args:
        date: Date to adjust
        convention: Adjustment convention
            - "following": Next trading day
            - "preceding": Previous trading day
            - "modified_following": Next trading day unless it crosses month
            - "nearest": Nearest trading day (prefer previous if equidistant)
        market: Market calendar to use

    Returns:
        Adjusted date
    """
    if is_trading_day(date, market):
        return date

    if convention == "following":
        result = next_trading_day(date, market)
        return result if result else date

    elif convention == "preceding":
        result = previous_trading_day(date, market)
        return result if result else date

    elif convention == "modified_following":
        next_day = next_trading_day(date, market)
        if next_day and next_day.month == date.month:
            return next_day
        else:
            # If next trading day is in different month, use preceding
            result = previous_trading_day(date, market)
            return result if result else date

    elif convention == "nearest":
        next_day = next_trading_day(date, market)
        prev_day = previous_trading_day(date, market)

        if next_day is None and prev_day is None:
            return date
        elif next_day is None:
            return prev_day
        elif prev_day is None:
            return next_day
        else:
            # Choose nearest, prefer previous if equidistant
            days_to_next = (next_day - date).days
            days_to_prev = (date - prev_day).days
            return prev_day if days_to_prev <= days_to_next else next_day

    else:
        logger.warning(f"Unknown convention '{convention}', using 'following'")
        result = next_trading_day(date, market)
        return result if result else date


def infer_market_from_symbol(symbol: str) -> Market:
    """
    Infer market calendar from symbol.

    Args:
        symbol: Yahoo Finance symbol

    Returns:
        Inferred market
    """
    symbol_upper = symbol.upper()

    # US indices
    if symbol_upper.startswith("^") and symbol_upper in ["^GSPC", "^DJI", "^IXIC", "^NDX", "^RUT", "^VIX"]:
        return Market.NYSE

    # UK indices
    if symbol_upper in ["^FTSE"]:
        return Market.LSE

    # Japan indices
    if symbol_upper in ["^N225"]:
        return Market.TSE

    # Hong Kong indices
    if symbol_upper in ["^HSI"]:
        return Market.HKEX

    # China indices
    if ".SS" in symbol_upper or symbol_upper in ["^FTXIN9"]:
        return Market.SSE

    # Default to NYSE for US stocks and US sector ETFs
    if not symbol_upper.startswith("^") and ".SS" not in symbol_upper and ".HK" not in symbol_upper:
        return Market.NYSE

    # Generic for everything else
    return Market.GENERIC


def validate_date_business_day(
    date: datetime,
    market: Market = Market.NYSE,
    date_type: str = "unknown"
) -> List[str]:
    """
    Validate that date is a business day and provide warnings if not.

    Args:
        date: Date to validate
        market: Market calendar to use
        date_type: Type of date (e.g., "pricing_date", "settlement_date")

    Returns:
        List of warning messages (empty if valid)
    """
    warnings = []

    if is_weekend(date):
        warnings.append(
            f"{date_type} ({date.strftime('%Y-%m-%d')}) falls on {date.strftime('%A')} (weekend)"
        )

    if not is_trading_day(date, market):
        if market == Market.NYSE:
            holiday_name = "a US market holiday"
        elif market == Market.LSE:
            holiday_name = "a UK market holiday"
        else:
            holiday_name = "a holiday"

        warnings.append(
            f"{date_type} ({date.strftime('%Y-%m-%d')}) falls on {holiday_name}"
        )

    return warnings
