# Quick Fixes - Top Priority Issues

These are the most critical issues that must be fixed before using this code in production.

---

## 🔴 FIX #1: Use Adjusted Close Prices (CRITICAL)

**File**: `structured_products/fetcher.py:120-127`

### Current Code (WRONG):
```python
return {
    "actual_date": actual_date.strftime("%Y-%m-%d"),
    "open": float(most_recent["Open"]),
    "high": float(most_recent["High"]),
    "low": float(most_recent["Low"]),
    "close": float(most_recent["Close"]),  # ❌ WRONG for financial analysis
    "volume": int(most_recent["Volume"]),
}
```

### Fixed Code:
```python
return {
    "actual_date": actual_date.strftime("%Y-%m-%d"),
    "open": float(most_recent["Open"]),
    "high": float(most_recent["High"]),
    "low": float(most_recent["Low"]),
    "close": float(most_recent["Close"]),
    "adj_close": float(most_recent["Adj Close"]),  # ✅ Use this for calculations
    "volume": int(most_recent["Volume"]),
}
```

**Why this matters**:
- A stock that splits 2:1 will show a 50% "loss" with unadjusted prices
- Dividends will distort performance calculations
- Barrier observations will trigger incorrectly
- **This is the #1 cause of errors in financial backtesting**

---

## 🔴 FIX #2: Add Logging

**File**: `structured_products/fetcher.py`

### Current Code (WRONG):
```python
except Exception as e:
    print(f"Error fetching data for {symbol}: {e}")  # ❌ Using print()
```

### Fixed Code:
```python
import logging

logger = logging.getLogger(__name__)

# At the top of each module
logger = logging.getLogger(__name__)

# In your functions:
try:
    ticker = yf.Ticker(symbol)
    hist = ticker.history(start=start_date, end=end_date)
except Exception as e:
    logger.error(
        f"Failed to fetch data for {symbol}",
        extra={
            "symbol": symbol,
            "dates": dates,
            "lookback_days": lookback_days
        },
        exc_info=True
    )
    raise
```

### Add to CLI (`__main__.py`):
```python
import logging

def main():
    # Configure logging at startup
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('structured_products.log'),
            logging.StreamHandler()
        ]
    )

    logger = logging.getLogger(__name__)
    logger.info("Starting structured products extraction")
    # ... rest of code
```

---

## 🟡 FIX #3: Add Date Validation

**File**: Create new `structured_products/validation.py`

```python
"""Data validation for structured products."""

import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger(__name__)


class ValidationWarning:
    """Represents a validation warning."""

    def __init__(self, severity: str, message: str, field: str = None):
        self.severity = severity  # 'error', 'warning', 'info'
        self.message = message
        self.field = field

    def __str__(self):
        return f"[{self.severity.upper()}] {self.message}"


def validate_dates(dates: Dict[str, str]) -> List[ValidationWarning]:
    """
    Validate date chronology and business logic.

    Returns:
        List of validation warnings
    """
    warnings = []

    try:
        # Parse all dates
        parsed_dates = {}
        for key, date_str in dates.items():
            try:
                parsed_dates[key] = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError:
                warnings.append(
                    ValidationWarning("error", f"Invalid date format: {date_str}", key)
                )

        # Check chronological order
        if "pricing_date" in parsed_dates and "maturity_date" in parsed_dates:
            if parsed_dates["maturity_date"] <= parsed_dates["pricing_date"]:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Maturity date ({dates['maturity_date']}) must be after "
                        f"pricing date ({dates['pricing_date']})"
                    )
                )

        # Check trade date vs settlement date
        if "trade_date" in parsed_dates and "settlement_date" in parsed_dates:
            if parsed_dates["settlement_date"] < parsed_dates["trade_date"]:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Settlement date ({dates['settlement_date']}) cannot be before "
                        f"trade date ({dates['trade_date']})"
                    )
                )

        # Check pricing date vs trade date (usually same or trade is T+1)
        if "pricing_date" in parsed_dates and "trade_date" in parsed_dates:
            days_diff = (parsed_dates["trade_date"] - parsed_dates["pricing_date"]).days
            if days_diff > 5:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Trade date is {days_diff} days after pricing date. "
                        f"This is unusual (typically T+0 or T+1)"
                    )
                )

        # Check valuation dates
        if "initial_valuation_date" in parsed_dates and "final_valuation_date" in parsed_dates:
            if parsed_dates["final_valuation_date"] <= parsed_dates["initial_valuation_date"]:
                warnings.append(
                    ValidationWarning(
                        "error",
                        "Final valuation date must be after initial valuation date"
                    )
                )

        # Check maturity is reasonable (not too short or too long)
        if "pricing_date" in parsed_dates and "maturity_date" in parsed_dates:
            days_to_maturity = (parsed_dates["maturity_date"] - parsed_dates["pricing_date"]).days
            years_to_maturity = days_to_maturity / 365.25

            if years_to_maturity < 0.08:  # Less than 1 month
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Very short maturity: {days_to_maturity} days. "
                        f"Verify this is not an error."
                    )
                )
            elif years_to_maturity > 30:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Very long maturity: {years_to_maturity:.1f} years. "
                        f"Verify this is not an error."
                    )
                )

        # Check dates aren't in the distant past
        now = datetime.now()
        for key, date_obj in parsed_dates.items():
            years_ago = (now - date_obj).days / 365.25
            if years_ago > 10:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"{key} is {years_ago:.1f} years ago. Verify this is correct."
                    )
                )

    except Exception as e:
        logger.error(f"Error during date validation: {e}", exc_info=True)
        warnings.append(ValidationWarning("error", f"Validation error: {e}"))

    return warnings


def validate_symbols(symbols: List[str]) -> List[ValidationWarning]:
    """
    Validate extracted symbols.

    Returns:
        List of validation warnings
    """
    warnings = []

    if not symbols:
        warnings.append(
            ValidationWarning("warning", "No symbols detected in filing")
        )

    # Check for common errors
    for symbol in symbols:
        if len(symbol) < 2:
            warnings.append(
                ValidationWarning("warning", f"Symbol '{symbol}' is unusually short")
            )
        if len(symbol) > 6 and not symbol.startswith("^"):
            warnings.append(
                ValidationWarning("warning", f"Symbol '{symbol}' is unusually long")
            )

    return warnings
```

### Update `__main__.py` to use validation:
```python
from .validation import validate_dates, validate_symbols

# After extracting data:
symbol_data = extract_symbols(content, is_html=is_html, additional_symbols=args.symbols)
date_data = extract_dates(content, is_html=is_html)

# Validate
date_warnings = validate_dates(date_data)
symbol_warnings = validate_symbols(symbol_data["yahoo_symbols"])

# Add to result
result["validation"] = {
    "date_warnings": [str(w) for w in date_warnings],
    "symbol_warnings": [str(w) for w in symbol_warnings],
    "has_errors": any(w.severity == "error" for w in date_warnings + symbol_warnings)
}

# Log warnings
for warning in date_warnings + symbol_warnings:
    if warning.severity == "error":
        logger.error(warning)
    elif warning.severity == "warning":
        logger.warning(warning)
```

---

## 🟡 FIX #4: Add Concurrent Fetching

**File**: `structured_products/fetcher.py`

### Current Code (SLOW):
```python
def fetch_prices_for_multiple_symbols(
    symbols: List[str],
    dates: List[str],
    lookback_days: int = 7
) -> Dict[str, Dict[str, Optional[Dict[str, float]]]]:
    results = {}
    for symbol in symbols:  # ❌ Sequential - very slow
        results[symbol] = fetch_historical_prices(symbol, dates, lookback_days)
    return results
```

### Fixed Code (FAST):
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

logger = logging.getLogger(__name__)

def fetch_prices_for_multiple_symbols(
    symbols: List[str],
    dates: List[str],
    lookback_days: int = 7,
    max_workers: int = 5
) -> Dict[str, Dict[str, Optional[Dict[str, float]]]]:
    """
    Fetch historical prices for multiple symbols concurrently.

    Args:
        symbols: List of Yahoo Finance symbols
        dates: List of ISO-formatted date strings
        lookback_days: Number of days to look back
        max_workers: Maximum concurrent requests (default: 5)

    Returns:
        Dictionary mapping symbols to their price data
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_symbol = {
            executor.submit(
                fetch_historical_prices,
                symbol,
                dates,
                lookback_days
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
                results[symbol] = None

    return results
```

**Performance improvement**: 10 symbols in ~2 seconds instead of ~10 seconds (5x faster)

---

## 🟡 FIX #5: Add Rate Limiting

**File**: `structured_products/fetcher.py`

### Add at top of file:
```python
import time
from functools import wraps

def rate_limit(calls_per_second: float = 2.0):
    """
    Rate limiting decorator to avoid API throttling.

    Yahoo Finance limits requests. This ensures we don't exceed limits.
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


# Apply to fetch function
@rate_limit(calls_per_second=2.0)
def fetch_historical_prices(...):
    # existing implementation
```

---

## 🟡 FIX #6: Add Retry Logic

**File**: Add to `requirements.txt`:
```
tenacity>=8.2.0
```

**File**: `structured_products/fetcher.py`

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
import requests

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.RequestException, ConnectionError)),
    before_sleep=lambda retry_state: logger.warning(
        f"Retry attempt {retry_state.attempt_number} after error: {retry_state.outcome.exception()}"
    )
)
@rate_limit(calls_per_second=2.0)
def fetch_historical_prices(
    symbol: str,
    dates: List[str],
    lookback_days: int = 7
) -> Dict[str, Optional[Dict[str, float]]]:
    """
    Fetch historical prices with automatic retries.

    Will retry up to 3 times with exponential backoff (2s, 4s, 8s).
    """
    # existing implementation
```

---

## Summary of Changes

### Updated requirements.txt:
```txt
beautifulsoup4>=4.12.0
lxml>=4.9.0
yfinance>=0.2.0
python-dateutil>=2.8.0
requests>=2.31.0
tenacity>=8.2.0  # NEW: For retry logic
```

### Files to Update:
1. ✅ `fetcher.py` - Add adj_close, logging, rate limiting, retries, concurrent fetching
2. ✅ `validation.py` - NEW FILE - Add date and symbol validation
3. ✅ `__main__.py` - Add logging configuration and validation calls
4. ✅ `requirements.txt` - Add tenacity

### Estimated Time:
- **Fix #1 (Adj Close)**: 15 minutes
- **Fix #2 (Logging)**: 30 minutes
- **Fix #3 (Validation)**: 1 hour
- **Fix #4 (Concurrent)**: 30 minutes
- **Fix #5 (Rate Limit)**: 20 minutes
- **Fix #6 (Retry)**: 20 minutes

**Total: ~3 hours** to implement all critical fixes.

### Testing After Fixes:
```bash
# Run with example filing
python -m structured_products -i example_filing.txt --pretty

# Check the log file
cat structured_products.log

# Verify validation warnings appear in output
# Verify adj_close is in price data
# Verify multiple symbols fetch quickly (concurrent)
```
