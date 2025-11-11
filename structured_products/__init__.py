"""
Structured Products Toolkit

Utilities to extract referenced symbols/indices and key dates from structured note filings,
and fetch historical prices for those dates from Yahoo Finance.
"""

__version__ = "0.1.0"

from .parser import extract_symbols, extract_dates
from .fetcher import fetch_historical_prices

__all__ = ["extract_symbols", "extract_dates", "fetch_historical_prices"]
