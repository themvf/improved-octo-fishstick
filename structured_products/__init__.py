"""
Structured Products Toolkit

Utilities to extract referenced symbols/indices and key dates from structured note filings,
and fetch historical prices for those dates from Yahoo Finance.
"""

__version__ = "0.2.0"

from .parser import extract_symbols, extract_dates
from .fetcher import fetch_historical_prices, fetch_prices_for_multiple_symbols
from .validation import (
    validate_dates,
    validate_symbols,
    validate_extraction_results,
    ValidationWarning
)

__all__ = [
    "extract_symbols",
    "extract_dates",
    "fetch_historical_prices",
    "fetch_prices_for_multiple_symbols",
    "validate_dates",
    "validate_symbols",
    "validate_extraction_results",
    "ValidationWarning",
]
