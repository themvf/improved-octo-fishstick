"""
Structured Products Toolkit

Utilities to extract referenced symbols/indices and key dates from structured note filings,
and fetch historical prices for those dates from Yahoo Finance.
"""

__version__ = "0.5.0"

from .parser import extract_symbols, extract_dates
from .fetcher import fetch_historical_prices, fetch_prices_for_multiple_symbols
from .validation import (
    validate_dates,
    validate_symbols,
    validate_extraction_results,
    ValidationWarning
)
from .terms import (
    extract_product_terms,
    extract_basket_information,
    summarize_product_terms
)
from .cache import PriceCache, get_cache, clear_global_cache
from .calendar import (
    Market,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    get_settlement_date,
    adjust_to_trading_day,
    infer_market_from_symbol
)
from .identifiers import (
    extract_all_identifiers,
    extract_cusip,
    extract_isin,
    validate_cusip,
    validate_isin
)
from .pdf import (
    is_pdf_supported,
    extract_text_from_pdf,
    read_filing_content
)
from .analytics import (
    calculate_realized_volatility,
    calculate_rolling_volatilities,
    calculate_greeks,
    analyze_structured_product_greeks,
    calculate_breakeven_levels,
    calculate_risk_metrics,
    generate_analytics_summary
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
    "extract_product_terms",
    "extract_basket_information",
    "summarize_product_terms",
    "PriceCache",
    "get_cache",
    "clear_global_cache",
    "Market",
    "is_trading_day",
    "next_trading_day",
    "previous_trading_day",
    "get_settlement_date",
    "adjust_to_trading_day",
    "infer_market_from_symbol",
    "extract_all_identifiers",
    "extract_cusip",
    "extract_isin",
    "validate_cusip",
    "validate_isin",
    "is_pdf_supported",
    "extract_text_from_pdf",
    "read_filing_content",
    "calculate_realized_volatility",
    "calculate_rolling_volatilities",
    "calculate_greeks",
    "analyze_structured_product_greeks",
    "calculate_breakeven_levels",
    "calculate_risk_metrics",
    "generate_analytics_summary",
]
