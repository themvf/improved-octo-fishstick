"""
CLI entry point for structured products toolkit.
"""

import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Optional

from .parser import extract_symbols, extract_dates
from .fetcher import fetch_historical_prices
from .validation import validate_extraction_results
from .terms import extract_product_terms, summarize_product_terms
from .identifiers import extract_all_identifiers
from .pdf import is_pdf_supported, read_filing_content
from .analytics import generate_analytics_summary


def setup_logging(verbose: bool = False, log_file: Optional[str] = None):
    """
    Configure logging for the application.

    Args:
        verbose: Enable debug logging
        log_file: Optional path to log file
    """
    # Set log level
    level = logging.DEBUG if verbose else logging.INFO

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    simple_formatter = logging.Formatter('%(levelname)s: %(message)s')

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler (less verbose)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING if not verbose else logging.DEBUG)
    console_handler.setFormatter(simple_formatter)
    root_logger.addHandler(console_handler)

    # File handler (more detailed)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)
    elif verbose:
        # If verbose but no log file, add a default one
        default_log = 'structured_products.log'
        file_handler = logging.FileHandler(default_log)
        file_handler.setLevel(level)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)

    return root_logger


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

  # Extract terms, identifiers, and calculate analytics
  python -m structured_products -i filing.pdf --extract-terms --extract-identifiers --calculate-analytics --pretty

  # Calculate analytics with custom risk-free rate
  python -m structured_products -i filing.html --calculate-analytics --risk-free-rate 0.045 --pretty

  # Override/add symbols
  python -m structured_products -i filing.html -s ^GSPC -s ^RUT --pretty

  # Enable verbose logging
  python -m structured_products -i filing.html --pretty -v
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

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging (DEBUG level)"
    )

    parser.add_argument(
        "--log-file",
        type=str,
        help="Path to log file (default: structured_products.log if verbose)"
    )

    parser.add_argument(
        "--no-validation",
        action="store_true",
        help="Skip validation checks"
    )

    parser.add_argument(
        "--extract-terms",
        action="store_true",
        help="Extract product terms (barriers, caps, participation rates, etc.)"
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable price caching"
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear price cache and exit"
    )

    parser.add_argument(
        "--cache-stats",
        action="store_true",
        help="Show cache statistics and exit"
    )

    parser.add_argument(
        "--extract-identifiers",
        action="store_true",
        help="Extract security identifiers (CUSIP, ISIN, SEDOL)"
    )

    parser.add_argument(
        "--max-pdf-pages",
        type=int,
        help="Maximum pages to extract from PDF (default: all)"
    )

    parser.add_argument(
        "--check-pdf-support",
        action="store_true",
        help="Check if PDF support is available and exit"
    )

    parser.add_argument(
        "--calculate-analytics",
        action="store_true",
        help="Calculate volatility, Greeks, and risk metrics"
    )

    parser.add_argument(
        "--volatility-windows",
        type=str,
        default="20,60,252",
        help="Comma-separated volatility windows in days (default: 20,60,252)"
    )

    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.05,
        help="Risk-free rate for Greeks calculation (default: 0.05)"
    )

    args = parser.parse_args()

    # Handle utility commands
    if args.check_pdf_support:
        pdf_available = is_pdf_supported()
        status = {
            "pdf_support": pdf_available,
            "message": "PDF support is available" if pdf_available else "PDF support not available. Install with: pip install pdfplumber"
        }
        print(json.dumps(status, indent=2))
        sys.exit(0)

    if args.clear_cache:
        from .cache import get_cache
        cache = get_cache()
        cleared = cache.clear()
        print(f"Cleared {cleared} cache entries")
        sys.exit(0)

    if args.cache_stats:
        from .cache import get_cache
        cache = get_cache()
        stats = cache.get_stats()
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    # Setup logging
    logger = setup_logging(verbose=args.verbose, log_file=args.log_file)
    logger.info("Starting structured products extraction")

    # Read input content
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            logger.error(f"Input file not found: {args.input}")
            print(f"Error: Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)

        logger.info(f"Reading input from: {args.input}")

        # Use read_filing_content which supports PDF, HTML, and text
        try:
            content, is_html = read_filing_content(
                str(input_path),
                max_pdf_pages=args.max_pdf_pages
            )
        except ImportError as e:
            logger.error(f"PDF support not available: {e}")
            print(f"Error: {e}", file=sys.stderr)
            print("Install pdfplumber for PDF support: pip install pdfplumber", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error reading file: {e}", exc_info=True)
            print(f"Error: Could not read file: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Read from stdin
        logger.info("Reading input from stdin")
        content = sys.stdin.read()
        # Simple heuristic to detect HTML
        is_html = content.strip().startswith('<')

    if not content.strip():
        logger.error("No input content provided")
        print("Error: No input content provided", file=sys.stderr)
        sys.exit(1)

    logger.info(f"Processing {'HTML' if is_html else 'text'} content ({len(content)} characters)")

    # Extract symbols and dates
    try:
        symbol_data = extract_symbols(content, is_html=is_html, additional_symbols=args.symbols)
        date_data = extract_dates(content, is_html=is_html)
    except Exception as e:
        logger.error(f"Error during extraction: {e}", exc_info=True)
        print(f"Error: Extraction failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Extract product terms if requested
    product_terms = None
    terms_summary = None
    if args.extract_terms:
        try:
            logger.info("Extracting product terms")
            product_terms = extract_product_terms(content, is_html=is_html)
            terms_summary = summarize_product_terms(product_terms)
            logger.info(f"Extracted {len(product_terms)} product terms")
        except Exception as e:
            logger.error(f"Error extracting product terms: {e}", exc_info=True)
            product_terms = {"error": str(e)}

    # Extract identifiers if requested
    identifiers = None
    if args.extract_identifiers:
        try:
            logger.info("Extracting security identifiers")
            identifiers = extract_all_identifiers(content, is_html=is_html)
            if identifiers:
                logger.info(f"Found identifiers: {', '.join(identifiers.keys())}")
            else:
                logger.warning("No identifiers found")
        except Exception as e:
            logger.error(f"Error extracting identifiers: {e}", exc_info=True)
            identifiers = {"error": str(e)}

    # Prepare result
    result = {
        "indices": symbol_data["indices"],
        "yahoo_symbols": symbol_data["yahoo_symbols"],
        "raw_tickers": symbol_data["raw_tickers"],
        "dates": date_data,
        "prices": {}
    }

    # Add product terms if extracted
    if args.extract_terms:
        result["product_terms"] = product_terms
        if terms_summary:
            result["terms_summary"] = terms_summary

    # Add identifiers if extracted
    if args.extract_identifiers and identifiers:
        result["identifiers"] = identifiers

    # Validate extraction results (unless disabled)
    if not args.no_validation:
        logger.info("Running validation checks")
        try:
            validation_result = validate_extraction_results(symbol_data, date_data)
            result["validation"] = validation_result

            # Log validation summary
            if validation_result["has_errors"]:
                logger.error(
                    f"Validation errors found: {validation_result['error_count']} errors, "
                    f"{validation_result['warning_count']} warnings"
                )
                # Print errors to stderr
                for warning in validation_result["date_warnings"] + validation_result["symbol_warnings"]:
                    if warning["severity"] == "error":
                        print(f"ERROR: {warning['message']}", file=sys.stderr)
            elif validation_result["has_warnings"]:
                logger.warning(f"Validation warnings: {validation_result['warning_count']}")
        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            result["validation"] = {"error": str(e)}

    # Fetch prices for the first Yahoo symbol if available
    if symbol_data["yahoo_symbols"] and date_data:
        primary_symbol = symbol_data["yahoo_symbols"][0]
        date_list = list(date_data.values())

        logger.info(f"Fetching prices for primary symbol: {primary_symbol}")

        try:
            use_cache = not args.no_cache
            prices = fetch_historical_prices(
                primary_symbol,
                date_list,
                args.lookback,
                use_cache=use_cache
            )
            result["prices"] = {
                "symbol": primary_symbol,
                "data": prices
            }
            logger.info(f"Successfully fetched prices for {primary_symbol}")
        except Exception as e:
            logger.error(f"Could not fetch prices for {primary_symbol}: {e}", exc_info=True)
            print(f"Warning: Could not fetch prices for {primary_symbol}: {e}", file=sys.stderr)
            result["prices"] = {
                "symbol": primary_symbol,
                "error": str(e)
            }
    elif not symbol_data["yahoo_symbols"]:
        logger.warning("No symbols detected - skipping price fetch")
    elif not date_data:
        logger.warning("No dates detected - skipping price fetch")

    # Calculate analytics if requested
    if args.calculate_analytics and result.get("prices", {}).get("data"):
        logger.info("Calculating analytics (volatility, Greeks, risk metrics)")
        try:
            # Parse volatility windows
            vol_windows = [int(w.strip()) for w in args.volatility_windows.split(",")]

            # Generate analytics summary
            analytics_result = generate_analytics_summary(
                prices_data=result["prices"],
                product_terms=product_terms if args.extract_terms else None,
                dates=date_data,
                risk_free_rate=args.risk_free_rate,
                volatility_windows=vol_windows
            )

            result["analytics"] = analytics_result
            logger.info("Analytics calculation complete")

        except Exception as e:
            logger.error(f"Analytics calculation failed: {e}", exc_info=True)
            print(f"Warning: Analytics calculation failed: {e}", file=sys.stderr)
            result["analytics"] = {"error": str(e)}

    # Output result
    logger.info("Extraction complete - outputting results")
    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))

    # Exit with appropriate code
    if not args.no_validation and result.get("validation", {}).get("has_errors", False):
        logger.warning("Exiting with code 2 due to validation errors")
        sys.exit(2)  # Validation errors

    logger.info("Completed successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
