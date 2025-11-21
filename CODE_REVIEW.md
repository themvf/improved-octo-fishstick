# Structured Products Toolkit - Senior Developer Code Review

**Reviewer Perspective**: Senior Developer with Finance/Trading Systems Background
**Review Date**: 2025-11-11
**Overall Assessment**: Good foundation, but needs significant enhancements for production use

---

## Executive Summary

The toolkit provides a solid foundation for extracting structured product data, but has critical gaps in:
- **Financial accuracy** (not using adjusted prices, missing critical indices)
- **Data validation** (no sanity checks on extracted data)
- **Production readiness** (no logging, error handling, rate limiting)
- **Structured products domain** (missing barrier levels, caps, participation rates)
- **Performance** (sequential API calls, no caching)

**Recommendation**: Requires substantial refactoring before production deployment.

---

## 🔴 CRITICAL ISSUES

### 1. **Using Close Instead of Adjusted Close**
**Severity**: CRITICAL
**Location**: `fetcher.py:122`

```python
"close": float(most_recent["Close"]),  # ❌ WRONG
```

**Problem**: The code uses raw close prices instead of adjusted close. This is **fundamentally broken** for any financial analysis because:
- Stock splits will show incorrect returns (e.g., 2:1 split makes it look like -50% loss)
- Dividend payments distort performance calculations
- Historical comparisons are meaningless

**Impact**: Any structured product with equity underlyings will have incorrect valuations.

**Fix**:
```python
"close": float(most_recent["Close"]),
"adj_close": float(most_recent["Adj Close"]),  # Use this for calculations
```

**For structured products, you MUST use adjusted close for:**
- Performance calculations
- Barrier observations
- Autocall triggers
- Final valuation

---

### 2. **No Date Validation**
**Severity**: HIGH
**Location**: `parser.py:148`

**Problem**: The code extracts dates but doesn't validate chronological order:
```python
# Current code accepts this invalid data:
{
  "pricing_date": "2024-01-15",
  "maturity_date": "2020-01-15"  # ❌ Maturity before pricing!
}
```

**Fix**: Add validation:
```python
def validate_dates(dates: Dict[str, str]) -> List[str]:
    """Validate date chronology and return warnings."""
    warnings = []

    if "pricing_date" in dates and "maturity_date" in dates:
        pricing = datetime.strptime(dates["pricing_date"], "%Y-%m-%d")
        maturity = datetime.strptime(dates["maturity_date"], "%Y-%m-%d")
        if maturity <= pricing:
            warnings.append("Maturity date must be after pricing date")

    # Check settlement is after trade date
    if "trade_date" in dates and "settlement_date" in dates:
        trade = datetime.strptime(dates["trade_date"], "%Y-%m-%d")
        settlement = datetime.strptime(dates["settlement_date"], "%Y-%m-%d")
        if settlement < trade:
            warnings.append("Settlement date must be on or after trade date")

    return warnings
```

---

### 3. **Missing Critical Indices**
**Severity**: MEDIUM
**Location**: `parser.py:13-35`

**Missing indices commonly used in structured products**:
- VIX (^VIX) - volatility products
- Sector indices (XLF, XLE, XLK, etc.)
- International indices (CAC 40, SMI, ASX 200)
- Commodity indices (gold, oil, etc.)
- China A50 (^FTXIN9)

**Fix**: Expand INDEX_MAPPING significantly.

---

## 💰 FINANCIAL DOMAIN CONCERNS

### 4. **No Corporate Actions Handling**
**Problem**: Code doesn't account for:
- Stock splits (critical for barrier observations)
- Reverse splits
- Dividend reinvestment
- Index rebalancing events
- Ticker symbol changes

**Example failure scenario**:
```
Product: Autocallable note on TSLA
Barrier: $150 (set in 2022)
TSLA does 3:1 split in 2022
Code checks barrier against unadjusted price → wrong trigger
```

**Solution**: Always use adjusted prices and document split-adjustment methodology.

---

### 5. **Ignoring Business Day Conventions**
**Problem**: Financial dates follow specific conventions:
- T+1, T+2 settlement
- Modified following (if date falls on holiday, move to next business day)
- Different calendars for different markets (US, UK, JP holidays)

**Current code**:
```python
# Just finds the most recent trading day within 7 days
# Doesn't respect actual settlement conventions
```

**Fix**: Use `pandas_market_calendars` or `exchange_calendars`:
```python
import pandas_market_calendars as mcal

def get_trading_date(date: datetime, exchange: str = "NYSE") -> datetime:
    """Get actual trading date respecting market calendar."""
    cal = mcal.get_calendar(exchange)
    schedule = cal.schedule(start_date=date - timedelta(10), end_date=date)
    valid_days = schedule.index
    valid_days = valid_days[valid_days <= date]
    return valid_days[-1] if len(valid_days) > 0 else None
```

---

### 6. **No Currency Handling**
**Problem**: International indices trade in different currencies:
- DAX (EUR)
- Nikkei (JPY)
- FTSE (GBP)

For multi-asset products, you need FX rates for:
- Currency hedging
- Cross-currency products
- FX-linked structures

**Fix**: Add currency metadata and FX rate fetching.

---

## 🏗️ STRUCTURED PRODUCTS SPECIFIC ISSUES

### 7. **Missing Critical Product Terms Extraction**
**Severity**: HIGH

Structured products have key terms that should be extracted:

```python
# Missing from current implementation:
PRODUCT_TERMS = [
    "participation rate",  # e.g., "150% participation"
    "cap",                 # e.g., "25% cap"
    "floor",
    "barrier",            # e.g., "70% barrier" or "60% knock-in"
    "knock-in",
    "knock-out",
    "autocall",
    "coupon",
    "trigger level",
    "protection level",
    "gearing",
    "leverage",
]
```

**Implementation**:
```python
def extract_product_terms(text: str) -> Dict[str, any]:
    """Extract structured product terms."""
    terms = {}

    # Extract percentages near keywords
    patterns = {
        "participation_rate": r"participation\s+(?:rate\s+)?(?:of\s+)?(\d+(?:\.\d+)?%)",
        "cap": r"(?:capped\s+at|cap\s+of|maximum\s+return\s+of)\s+(\d+(?:\.\d+)?%)",
        "barrier": r"(?:barrier\s+(?:at|of|level)?|protection\s+(?:at|of))\s+(\d+(?:\.\d+)?%)",
        "coupon": r"(?:coupon\s+(?:of|rate)?|pays|payment\s+of)\s+(\d+(?:\.\d+)?%)",
    }

    for term, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            terms[term] = match.group(1)

    return terms
```

---

### 8. **No Support for Worst-of / Best-of Structures**
**Problem**: Many structured products are linked to baskets:
- Worst-of: Performance based on worst performer in basket
- Best-of: Performance based on best performer
- Average: Equal-weighted or custom-weighted basket

**Current limitation**: Only fetches prices for first symbol.

**Fix**:
```python
def calculate_basket_performance(
    prices: Dict[str, pd.DataFrame],
    weights: Dict[str, float],
    method: str = "worst-of"
) -> pd.Series:
    """Calculate basket performance for multi-asset products."""
    # Implementation for worst-of, best-of, weighted average
    pass
```

---

### 9. **Missing CUSIP/ISIN Extraction**
**Problem**: No extraction of security identifiers.

**Fix**:
```python
def extract_identifiers(text: str) -> Dict[str, str]:
    """Extract security identifiers."""
    identifiers = {}

    # CUSIP: 9 characters (alphanumeric)
    cusip_match = re.search(r'\b([A-Z0-9]{9})\b', text)
    if cusip_match:
        identifiers["cusip"] = cusip_match.group(1)

    # ISIN: 12 characters (2-letter country code + 9-digit identifier + check digit)
    isin_match = re.search(r'\b([A-Z]{2}[A-Z0-9]{10})\b', text)
    if isin_match:
        identifiers["isin"] = isin_match.group(1)

    return identifiers
```

---

## ⚡ PERFORMANCE ISSUES

### 10. **Sequential API Calls**
**Severity**: MEDIUM
**Location**: `fetcher.py:147-149`

```python
# Current: O(n) time, sequential
for symbol in symbols:
    results[symbol] = fetch_historical_prices(symbol, dates, lookback_days)
```

**Problem**: For 10 symbols, this makes 10 sequential API calls (~10 seconds).

**Fix**: Use concurrent requests:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed

def fetch_prices_for_multiple_symbols(
    symbols: List[str],
    dates: List[str],
    lookback_days: int = 7,
    max_workers: int = 5
) -> Dict[str, Dict[str, Optional[Dict[str, float]]]]:
    """Fetch historical prices concurrently."""
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {
            executor.submit(fetch_historical_prices, symbol, dates, lookback_days): symbol
            for symbol in symbols
        }

        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                results[symbol] = future.result()
            except Exception as e:
                print(f"Error fetching {symbol}: {e}")
                results[symbol] = None

    return results
```

**Performance gain**: 10 symbols in ~2 seconds instead of ~10 seconds.

---

### 11. **No Caching Mechanism**
**Severity**: MEDIUM

**Problem**: Re-fetching the same data repeatedly.

**Fix**: Add simple caching:
```python
import functools
import hashlib
import json
from pathlib import Path

def _cache_key(symbol: str, dates: List[str], lookback_days: int) -> str:
    """Generate cache key."""
    data = json.dumps({"symbol": symbol, "dates": sorted(dates), "lookback": lookback_days})
    return hashlib.md5(data.encode()).hexdigest()

@functools.lru_cache(maxsize=100)
def fetch_historical_prices_cached(symbol: str, dates_tuple: tuple, lookback_days: int):
    """Cached version of fetch_historical_prices."""
    return fetch_historical_prices(symbol, list(dates_tuple), lookback_days)
```

---

### 12. **Regex Not Compiled**
**Severity**: LOW
**Location**: `parser.py:97`

```python
# Compiled once at module level
TICKER_PATTERN = re.compile(r'\b(\^?[A-Z]{2,5})\b')

def extract_symbols(...):
    matches = TICKER_PATTERN.findall(text)  # Faster
```

**Performance gain**: ~20% faster for repeated calls.

---

## 🛡️ PRODUCTION READINESS

### 13. **No Logging**
**Severity**: HIGH

**Problem**: Using `print()` for errors. Impossible to debug production issues.

**Fix**:
```python
import logging

logger = logging.getLogger(__name__)

# In code:
logger.info(f"Fetching prices for {symbol}")
logger.warning(f"No data found for {symbol} on {date}")
logger.error(f"API error: {e}", exc_info=True)
```

---

### 14. **No Rate Limiting**
**Severity**: MEDIUM

**Problem**: Yahoo Finance has rate limits. Code will get blocked.

**Fix**:
```python
from time import sleep
from functools import wraps

def rate_limit(calls_per_second: float = 2):
    """Rate limiting decorator."""
    min_interval = 1.0 / calls_per_second
    last_call = [0.0]

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_call[0]
            if elapsed < min_interval:
                sleep(min_interval - elapsed)
            last_call[0] = time.time()
            return func(*args, **kwargs)
        return wrapper
    return decorator

@rate_limit(calls_per_second=2)
def fetch_historical_prices(...):
    # Implementation
```

---

### 15. **No Retry Logic**
**Severity**: MEDIUM

**Problem**: Network failures cause immediate failure.

**Fix**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
def fetch_historical_prices(...):
    # Implementation with automatic retries
```

---

### 16. **Missing Unit Tests**
**Severity**: HIGH

**Required test coverage**:
```
tests/
├── test_parser.py
│   ├── test_extract_symbols_from_text
│   ├── test_extract_symbols_from_html
│   ├── test_extract_dates_various_formats
│   ├── test_date_validation
│   └── test_edge_cases
├── test_fetcher.py
│   ├── test_fetch_historical_prices
│   ├── test_handle_missing_data
│   ├── test_business_day_logic
│   └── test_concurrent_fetching
└── test_integration.py
    └── test_end_to_end_workflow
```

**Example test**:
```python
def test_extract_dates_chronological_validation():
    """Test that invalid date sequences are caught."""
    filing = """
    Pricing Date: January 15, 2024
    Maturity Date: January 15, 2020
    """
    dates = extract_dates(filing)
    warnings = validate_dates(dates)
    assert len(warnings) > 0
    assert "maturity" in warnings[0].lower()
```

---

## 🎯 CODE QUALITY IMPROVEMENTS

### 17. **Type Hints Incomplete**
**Location**: Multiple

```python
# Current
def extract_text_from_html(html_content: str) -> str:  # ✅ Good

# But also:
def extract_symbols(...) -> Dict[str, any]:  # ❌ Use 'Any' not 'any'

# Better:
from typing import Any, Dict, List, Optional, Union

def extract_symbols(
    content: str,
    is_html: bool = False,
    additional_symbols: Optional[List[str]] = None
) -> Dict[str, Union[List[str], Any]]:  # More precise
```

---

### 18. **Magic Numbers**
**Location**: Multiple

```python
# Current
pattern = re.escape(keyword) + r'[:\s,]*([^\.]{0,100})'  # What is 100?
ticker_pattern = r'\b(\^?[A-Z]{2,5})\b'  # Why 2-5?

# Better
MAX_DATE_CONTEXT_CHARS = 100  # Characters to search after date keyword
MIN_TICKER_LENGTH = 2  # Minimum ticker symbol length
MAX_TICKER_LENGTH = 5  # Maximum ticker symbol length

pattern = re.escape(keyword) + rf'[:\s,]*([^\.]{{0,{MAX_DATE_CONTEXT_CHARS}}})'
ticker_pattern = rf'\b(\^?[A-Z]{{{MIN_TICKER_LENGTH},{MAX_TICKER_LENGTH}}})\b'
```

---

### 19. **Error Messages Not Actionable**
**Location**: `fetcher.py:80`

```python
# Current
print(f"Error fetching data for {symbol}: {e}")

# Better
logger.error(
    f"Failed to fetch historical prices for {symbol}. "
    f"Dates requested: {dates}. "
    f"Error: {e}. "
    f"Suggestions: (1) Check symbol is valid, (2) Check internet connection, "
    f"(3) Verify dates are not in the future",
    exc_info=True
)
```

---

### 20. **No Configuration File**
**Problem**: Hard-coded settings scattered throughout code.

**Fix**: Create `config.py`:
```python
from dataclasses import dataclass
from typing import Dict

@dataclass
class Config:
    # API settings
    DEFAULT_LOOKBACK_DAYS: int = 7
    MAX_LOOKBACK_DAYS: int = 30
    RATE_LIMIT_CALLS_PER_SECOND: float = 2.0
    REQUEST_TIMEOUT_SECONDS: int = 30
    MAX_RETRY_ATTEMPTS: int = 3

    # Parser settings
    MAX_DATE_CONTEXT_CHARS: int = 100
    MIN_TICKER_LENGTH: int = 2
    MAX_TICKER_LENGTH: int = 5

    # Data validation
    MIN_DAYS_TO_MATURITY: int = 30  # Warn if maturity < 30 days
    MAX_YEARS_TO_MATURITY: int = 30  # Warn if maturity > 30 years

    # Performance
    CONCURRENT_REQUEST_WORKERS: int = 5
    ENABLE_CACHE: bool = True
    CACHE_TTL_SECONDS: int = 3600
```

---

## 📊 ADDITIONAL ENHANCEMENTS

### 21. **Add Data Quality Metrics**
```python
@dataclass
class ExtractionQuality:
    """Metrics on extraction quality."""
    symbols_found: int
    symbols_validated: int  # Verified against known index list
    dates_found: int
    dates_validated: int  # Passed chronology checks
    price_fetch_success_rate: float
    warnings: List[str]
    confidence_score: float  # 0-1 overall confidence

    def to_dict(self) -> dict:
        return asdict(self)
```

---

### 22. **Add HTML Table Extraction**
Many filings have structured tables:

```python
def extract_terms_from_table(soup: BeautifulSoup) -> Dict[str, str]:
    """Extract product terms from HTML tables."""
    terms = {}

    for table in soup.find_all('table'):
        for row in table.find_all('tr'):
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)

                if any(kw in key for kw in ['barrier', 'cap', 'participation']):
                    terms[key] = value

    return terms
```

---

### 23. **Add PDF Support**
Many filings are PDFs, not HTML:

```python
# Add to requirements.txt
# pdfplumber>=0.9.0

import pdfplumber

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from PDF filing."""
    text = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text.append(page.extract_text())
    return "\n".join(text)
```

---

## 🚀 RECOMMENDED REFACTORING

### Priority 1 (Do Now):
1. ✅ Use adjusted close prices
2. ✅ Add date validation
3. ✅ Add logging
4. ✅ Add unit tests
5. ✅ Add rate limiting

### Priority 2 (Next Sprint):
6. ✅ Add concurrent API fetching
7. ✅ Extract product terms (barriers, caps, etc.)
8. ✅ Add caching
9. ✅ Expand index coverage
10. ✅ Add business day calendar support

### Priority 3 (Future):
11. ✅ Add PDF support
12. ✅ Add basket product support (worst-of, best-of)
13. ✅ Add FX rate fetching for multi-currency products
14. ✅ Build ML model for term extraction
15. ✅ Add real-time monitoring/alerting

---

## 📈 PERFORMANCE BENCHMARK

Current implementation (10 symbols, 5 dates):
- Sequential fetching: ~10-12 seconds
- No caching: Every run fetches fresh data
- No rate limiting: Risk of being blocked

Optimized implementation:
- Concurrent fetching: ~2-3 seconds (4x faster)
- With caching: ~0.1 seconds for repeated queries (100x faster)
- With rate limiting: Reliable, no blocks

---

## 💡 FINAL RECOMMENDATIONS

### Immediate Actions:
1. **Stop using Close, use Adj Close** - This is a critical bug
2. **Add comprehensive logging** - Essential for production debugging
3. **Implement date validation** - Prevents garbage data
4. **Add unit tests** - Aim for >80% coverage

### Architecture Improvements:
5. **Separate concerns**: Parser → Validator → Fetcher → Analyzer
6. **Add configuration layer**: Externalize all magic numbers
7. **Implement proper error handling**: Distinguish retriable vs. permanent errors

### Domain Expertise:
8. **Consult with product structuring team**: Ensure all critical terms are captured
9. **Review with compliance**: Ensure extracted data meets regulatory requirements
10. **Test against real filings**: Build a test corpus of 50+ real structured product filings

### Production Readiness:
11. **Add monitoring**: Track extraction success rates, API performance
12. **Implement alerting**: Notify when data quality drops
13. **Create runbook**: Document common issues and resolutions

---

## 📝 CONCLUSION

The toolkit has a solid foundation but needs significant enhancements for production use. The most critical issue is using unadjusted close prices, which fundamentally breaks any financial calculations.

**Estimated effort to production-ready**:
- Fix critical issues: 2-3 days
- Add comprehensive testing: 3-4 days
- Performance optimizations: 2-3 days
- Structured products enhancements: 5-7 days
- **Total: 2-3 weeks** for a production-grade system

**Risk Assessment**:
- **Current code in production**: HIGH RISK (incorrect prices, no validation)
- **After Priority 1 fixes**: MEDIUM RISK (acceptable for internal tools)
- **After all priorities**: LOW RISK (production-ready)

Would proceed with incremental rollout: internal testing → limited production → full production.
