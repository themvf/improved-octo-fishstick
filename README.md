# Structured Products Toolkit

Utilities to extract referenced symbols/indices and key dates from structured note filings (HTML or text),
and fetch historical prices for those dates from Yahoo Finance.

## Features

- **Symbol Extraction**: Automatically detects index names (S&P 500, Russell 2000, NASDAQ, etc.) and converts them to Yahoo Finance symbols
- **Date Extraction**: Finds key dates such as pricing date, trade date, valuation dates, maturity date, etc.
- **Price Fetching**: Retrieves historical OHLCV data from Yahoo Finance for detected symbols on specified dates
- **Flexible Input**: Supports both HTML and plain text filings, from files or stdin
- **Symbol Override**: Allows manual specification of additional symbols

## Install

```bash
pip install -r requirements.txt
```

## Quick start

Process an HTML filing:
```bash
python -m structured_products -i path/to/filing.html --pretty
```

Process a text filing:
```bash
python -m structured_products -i path/to/filing.txt --pretty
```

Read from stdin:
```bash
cat filing.txt | python -m structured_products --pretty
```

Alternative CLI entry point:
```bash
python -m structured_products.cli -i filing.html --pretty
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
        "volume": 3500000000
      },
      "2024-01-18": {
        "actual_date": "2024-01-18",
        "open": 4850.43,
        "high": 4890.67,
        "low": 4835.12,
        "close": 4878.23,
        "volume": 3200000000
      }
    }
  }
}
```

### Output Fields

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
    - **volume**: Trading volume

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
usage: python -m structured_products [-h] [-i INPUT] [-s SYMBOLS] [--pretty] [--lookback LOOKBACK]

options:
  -h, --help            show this help message and exit
  -i INPUT, --input INPUT
                        Path to input filing (HTML or text). If not provided, reads from stdin.
  -s SYMBOLS, --symbol SYMBOLS
                        Additional Yahoo Finance symbol to include (can be specified multiple times)
  --pretty              Pretty-print JSON output
  --lookback LOOKBACK   Days to look back for historical prices (default: 7)
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

- Python 3.7+
- beautifulsoup4 (HTML parsing)
- lxml (XML/HTML parsing)
- yfinance (Yahoo Finance API)
- python-dateutil (Date parsing)
- requests (HTTP requests)

## License

MIT
