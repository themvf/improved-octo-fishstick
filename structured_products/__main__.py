"""
CLI entry point for structured products toolkit.
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Optional

from .parser import extract_symbols, extract_dates
from .fetcher import fetch_historical_prices


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Extract symbols and dates from structured product filings and fetch historical prices.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process HTML file
  python -m structured_products -i filing.html --pretty

  # Process from stdin
  cat filing.txt | python -m structured_products --pretty

  # Override/add symbols
  python -m structured_products -i filing.html -s ^GSPC -s ^RUT --pretty
        """
    )

    parser.add_argument(
        "-i", "--input",
        type=str,
        help="Path to input filing (HTML or text). If not provided, reads from stdin."
    )

    parser.add_argument(
        "-s", "--symbol",
        action="append",
        dest="symbols",
        help="Additional Yahoo Finance symbol to include (can be specified multiple times)"
    )

    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )

    parser.add_argument(
        "--lookback",
        type=int,
        default=7,
        help="Days to look back for historical prices (default: 7)"
    )

    args = parser.parse_args()

    # Read input content
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)

        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Detect if HTML based on file extension or content
        is_html = (
            input_path.suffix.lower() in ['.html', '.htm'] or
            content.strip().startswith('<')
        )
    else:
        # Read from stdin
        content = sys.stdin.read()
        # Simple heuristic to detect HTML
        is_html = content.strip().startswith('<')

    if not content.strip():
        print("Error: No input content provided", file=sys.stderr)
        sys.exit(1)

    # Extract symbols and dates
    symbol_data = extract_symbols(content, is_html=is_html, additional_symbols=args.symbols)
    date_data = extract_dates(content, is_html=is_html)

    # Prepare result
    result = {
        "indices": symbol_data["indices"],
        "yahoo_symbols": symbol_data["yahoo_symbols"],
        "raw_tickers": symbol_data["raw_tickers"],
        "dates": date_data,
        "prices": {}
    }

    # Fetch prices for the first Yahoo symbol if available
    if symbol_data["yahoo_symbols"] and date_data:
        primary_symbol = symbol_data["yahoo_symbols"][0]
        date_list = list(date_data.values())

        try:
            prices = fetch_historical_prices(primary_symbol, date_list, args.lookback)
            result["prices"] = {
                "symbol": primary_symbol,
                "data": prices
            }
        except Exception as e:
            print(f"Warning: Could not fetch prices for {primary_symbol}: {e}", file=sys.stderr)
            result["prices"] = {
                "symbol": primary_symbol,
                "error": str(e)
            }

    # Output result
    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
