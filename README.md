# Structured Products Toolkit

Professional toolkit to extract symbols, dates, product terms, and identifiers from structured note filings (HTML, text, or PDF), and fetch historical prices from Yahoo Finance.

## Features

### Core Functionality
- **Symbol Extraction**: Automatically detects 50+ index names (S&P 500, Russell 2000, NASDAQ, VIX, sectors, international) and converts them to Yahoo Finance symbols
- **Date Extraction**: Finds key dates such as pricing date, trade date, valuation dates, maturity date, etc.
- **Price Fetching**: Retrieves historical OHLCV data (including adjusted close) from Yahoo Finance for detected symbols on specified dates
- **Flexible Input**: Supports HTML, plain text, and PDF filings, from files or stdin

### Advanced Features
- **Product Terms Extraction**: Extract barriers, caps, participation rates, knock-in/knock-out levels, autocall triggers, coupons, and more
- **Security Identifiers**: Extract and validate CUSIP, ISIN, and SEDOL identifiers
- **Business Day Calendar**: Calculate settlement dates with T+2 logic and market-specific holiday calendars
- **PDF Support**: Extract text and tables from PDF filings (optional dependency)
- **Data Validation**: Comprehensive validation of extracted symbols and dates with confidence scoring
- **Price Caching**: Optional file-based caching to reduce API calls and improve performance
- **Rate Limiting**: Built-in rate limiting and retry logic for reliable API access

## Install

### Basic Installation

```bash
pip install -r requirements.txt
```

### Optional: PDF Support

For PDF file support, install pdfplumber:

```bash
pip install pdfplumber
```

Check PDF support:
```bash
python -m structured_products --check-pdf-support
```

## Quick start

Process an HTML filing:
```bash
python -m structured_products -i path/to/filing.html --pretty
```

Process a PDF filing:
```bash
python -m structured_products -i path/to/filing.pdf --pretty
```

Process a text filing:
```bash
python -m structured_products -i path/to/filing.txt --pretty
```

Read from stdin:
```bash
cat filing.txt | python -m structured_products --pretty
```

### Extract Product Terms and Identifiers

```bash
python -m structured_products -i filing.pdf \
  --extract-terms \
  --extract-identifiers \
  --pretty
```

### Use Price Caching

```bash
# Enable caching (default)
python -m structured_products -i filing.html --pretty

# Disable caching
python -m structured_products -i filing.html --no-cache --pretty

# View cache stats
python -m structured_products --cache-stats

# Clear cache
python -m structured_products --clear-cache
```

## Override/add symbols

You can add or override symbols that should be tracked:

```bash
python -m structured_products -i filing.html -s ^GSPC -s ^RUT --pretty
```

## Output Format

The tool outputs JSON with the following structure:

```json
{
  "indices": [
    "S&P 500",
    "Russell 2000"
  ],
  "yahoo_symbols": [
    "^GSPC",
    "^RUT"
  ],
  "raw_tickers": [
    "SPX",
    "RUT"
  ],
  "dates": {
    "pricing_date": "2024-01-15",
    "trade_date": "2024-01-18",
    "maturity_date": "2027-01-15"
  },
  "prices": {
    "symbol": "^GSPC",
    "data": {
      "2024-01-15": {
        "actual_date": "2024-01-15",
        "open": 4783.45,
        "high": 4850.43,
        "low": 4780.05,
        "close": 4839.81,
        "adj_close": 4839.81,
        "volume": 3500000000
      }
    }
  },
  "product_terms": {
    "participation_rate": {
      "value": 100.0,
      "unit": "%",
      "raw_text": "100% participation",
      "confidence": "high"
    },
    "buffer": {
      "value": 10.0,
      "unit": "%",
      "raw_text": "10% buffer",
      "confidence": "high"
    }
  },
  "terms_summary": {
    "payoff_type": "buffered_participation",
    "has_downside_protection": true,
    "has_upside_cap": false,
    "has_leverage": false,
    "is_path_dependent": false,
    "terms_extracted": 2,
    "confidence": "high"
  },
  "identifiers": {
    "cusip": "12345AB89",
    "isin": "US12345AB890",
    "sedol": null
  },
  "validation": {
    "has_errors": false,
    "has_warnings": false,
    "is_valid": true,
    "error_count": 0,
    "warning_count": 0,
    "date_warnings": [],
    "symbol_warnings": []
  }
}
```

### Output Fields

#### Core Fields (Always Present)

- **indices**: List of detected index names from the filing
- **yahoo_symbols**: List of Yahoo Finance symbol codes (with `^` prefix for indices)
- **raw_tickers**: List of all ticker-like patterns found in the filing
- **dates**: Dictionary mapping date types to ISO-formatted dates (YYYY-MM-DD)
- **prices**: Historical price data for the first Yahoo symbol
  - **symbol**: The Yahoo Finance symbol
  - **data**: Dictionary mapping requested dates to price information
    - **actual_date**: The actual trading date (may differ from requested if market was closed)
    - **open**: Opening price
    - **high**: Highest price
    - **low**: Lowest price
    - **close**: Closing price
    - **adj_close**: Adjusted closing price (accounts for splits and dividends) - **USE THIS FOR CALCULATIONS**
    - **volume**: Trading volume

#### Optional Fields (When Requested)

- **product_terms**: Product term details (with `--extract-terms`)
  - Each term includes: value, unit, raw_text, confidence
  - Supported terms: participation_rate, cap, floor, barrier, knock_in, knock_out, autocall, coupon, gearing, leverage, buffer, principal_protection, term_length, observation_frequency

- **terms_summary**: Summary of product structure (with `--extract-terms`)
  - **payoff_type**: Inferred payoff type (autocallable, buffered_participation, etc.)
  - **has_downside_protection**: Boolean indicating downside protection
  - **has_upside_cap**: Boolean indicating upside cap
  - **has_leverage**: Boolean indicating leveraged participation
  - **is_path_dependent**: Boolean indicating path dependency
  - **terms_extracted**: Number of terms found
  - **confidence**: Extraction confidence level

- **identifiers**: Security identifiers (with `--extract-identifiers`)
  - **cusip**: 9-character CUSIP (validated with check digit)
  - **isin**: 12-character ISIN (validated with Luhn algorithm)
  - **sedol**: 7-character SEDOL

- **validation**: Validation results (unless `--no-validation`)
  - **has_errors**: Boolean indicating if errors were found
  - **has_warnings**: Boolean indicating if warnings were found
  - **is_valid**: Overall validation status
  - **date_warnings**: List of date-related warnings
  - **symbol_warnings**: List of symbol-related warnings

## Supported Indices

The toolkit automatically recognizes and converts the following indices:

| Index Name | Yahoo Symbol |
|------------|--------------|
| S&P 500, SPX | ^GSPC |
| Russell 2000, RUT | ^RUT |
| NASDAQ | ^IXIC |
| NASDAQ-100, NDX | ^NDX |
| Dow Jones, DJIA | ^DJI |
| FTSE 100 | ^FTSE |
| DAX | ^GDAXI |
| Nikkei 225 | ^N225 |
| Hang Seng | ^HSI |
| Euro Stoxx 50 | ^STOXX50E |

## CLI Options

```
usage: python -m structured_products [-h] [-i INPUT] [-s SYMBOLS] [--pretty]
                                     [--lookback LOOKBACK] [-v] [--log-file LOG_FILE]
                                     [--no-validation] [--extract-terms] [--extract-identifiers]
                                     [--no-cache] [--clear-cache] [--cache-stats]
                                     [--max-pdf-pages MAX_PDF_PAGES] [--check-pdf-support]

Extract symbols and dates from structured product filings and fetch historical prices.

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Path to input filing (HTML, text, or PDF). If not provided, reads from stdin.
  -s SYMBOLS, --symbol SYMBOLS
                        Additional Yahoo Finance symbol to include (can be specified multiple times)
  --pretty              Pretty-print JSON output
  --lookback LOOKBACK   Days to look back for historical prices (default: 7)

Logging:
  -v, --verbose         Enable verbose logging (DEBUG level)
  --log-file LOG_FILE   Path to log file (default: structured_products.log if verbose)

Extraction Options:
  --extract-terms       Extract product terms (barriers, caps, participation rates, etc.)
  --extract-identifiers Extract security identifiers (CUSIP, ISIN, SEDOL)
  --no-validation       Skip validation checks

Caching:
  --no-cache            Disable price caching
  --clear-cache         Clear price cache and exit
  --cache-stats         Show cache statistics and exit

PDF Options:
  --max-pdf-pages N     Maximum pages to extract from PDF (default: all)
  --check-pdf-support   Check if PDF support is available and exit
```

## Programmatic Usage

You can also use the toolkit as a Python library:

```python
from structured_products import extract_symbols, extract_dates, fetch_historical_prices

# Read your filing content
with open("filing.html", "r") as f:
    content = f.read()

# Extract symbols
symbols = extract_symbols(content, is_html=True)
print(symbols["yahoo_symbols"])  # ['^GSPC', '^RUT']

# Extract dates
dates = extract_dates(content, is_html=True)
print(dates)  # {'pricing_date': '2024-01-15', 'maturity_date': '2027-01-15'}

# Fetch prices
if symbols["yahoo_symbols"] and dates:
    symbol = symbols["yahoo_symbols"][0]
    date_list = list(dates.values())
    prices = fetch_historical_prices(symbol, date_list, lookback_days=7)
    print(prices)
```

## Date Extraction

The toolkit searches for the following date types:

- Pricing Date
- Trade Date
- Valuation Date / Initial Valuation Date / Final Valuation Date
- Maturity Date
- Settlement Date
- Issue Date
- Observation Date

Dates are automatically parsed from various formats:
- MM/DD/YYYY or DD-MM-YYYY
- YYYY-MM-DD
- Month DD, YYYY
- DD Month YYYY

## Price Fetching Behavior

- Prices are fetched for the **first Yahoo symbol** in the detected list
- If the requested date is a non-trading day (weekend/holiday), the most recent prior trading day is used (within the lookback window)
- Default lookback window is 7 days (configurable with `--lookback`)
- Price data includes: open, high, low, close, and volume

## Error Handling

- If no symbols are detected, prices will not be fetched
- If a symbol is invalid or data is unavailable, the `prices` field will contain an error message
- If date parsing fails for a specific date, it will be omitted from the output

## Requirements

### Core Dependencies

- Python 3.7+
- beautifulsoup4>=4.12.0 (HTML parsing)
- lxml>=4.9.0 (XML/HTML parsing)
- yfinance>=0.2.0 (Yahoo Finance API)
- python-dateutil>=2.8.0 (Date parsing)
- requests>=2.31.0 (HTTP requests)
- tenacity>=8.2.0 (Retry logic with exponential backoff)

### Optional Dependencies

- pdfplumber>=0.10.0 (PDF file support)

## License

MIT
