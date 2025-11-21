"""
Parser module for extracting symbols and dates from structured product filings.
"""

import logging
import re
from typing import Dict, List, Set, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


# Common index names and their Yahoo Finance symbols
INDEX_MAPPING = {
    # US Major Indices
    "S&P 500": "^GSPC",
    "SPX": "^GSPC",
    "S&P500": "^GSPC",
    "RUSSELL 2000": "^RUT",
    "RUSSELL2000": "^RUT",
    "RUT": "^RUT",
    "NASDAQ": "^IXIC",
    "NASDAQ-100": "^NDX",
    "NASDAQ 100": "^NDX",
    "NDX": "^NDX",
    "DOW JONES": "^DJI",
    "DJIA": "^DJI",
    "DOW": "^DJI",

    # US Volatility
    "VIX": "^VIX",
    "CBOE VIX": "^VIX",
    "VOLATILITY INDEX": "^VIX",

    # US Sector Indices (Select Sector SPDRs)
    "XLF": "XLF",  # Financials
    "XLE": "XLE",  # Energy
    "XLK": "XLK",  # Technology
    "XLV": "XLV",  # Health Care
    "XLI": "XLI",  # Industrials
    "XLP": "XLP",  # Consumer Staples
    "XLY": "XLY",  # Consumer Discretionary
    "XLU": "XLU",  # Utilities
    "XLB": "XLB",  # Materials
    "XLRE": "XLRE",  # Real Estate
    "XLC": "XLC",  # Communication Services

    # Europe
    "FTSE 100": "^FTSE",
    "FTSE": "^FTSE",
    "DAX": "^GDAXI",
    "CAC 40": "^FCHI",
    "CAC": "^FCHI",
    "IBEX 35": "^IBEX",
    "FTSE MIB": "FTSEMIB.MI",
    "SMI": "^SSMI",
    "SWISS MARKET INDEX": "^SSMI",
    "EURO STOXX 50": "^STOXX50E",
    "STOXX50E": "^STOXX50E",
    "STOXX 600": "^STOXX",

    # Asia-Pacific
    "NIKKEI": "^N225",
    "NIKKEI 225": "^N225",
    "HANG SENG": "^HSI",
    "HSI": "^HSI",
    "SHANGHAI COMPOSITE": "000001.SS",
    "CSI 300": "000300.SS",
    "CHINA A50": "^FTXIN9",
    "FTSE CHINA A50": "^FTXIN9",
    "KOSPI": "^KS11",
    "SENSEX": "^BSESN",
    "NIFTY": "^NSEI",
    "NIFTY 50": "^NSEI",
    "ASX 200": "^AXJO",
    "STI": "^STI",  # Straits Times Index

    # Emerging Markets
    "MSCI EM": "EEM",
    "MSCI EMERGING MARKETS": "EEM",
    "BRAZIL BOVESPA": "^BVSP",
    "BOVESPA": "^BVSP",
    "MEXICO IPC": "^MXX",
    "RUSSIA MOEX": "IMOEX.ME",
}

# Date-related keywords
DATE_KEYWORDS = [
    "pricing date",
    "trade date",
    "valuation date",
    "initial valuation date",
    "final valuation date",
    "maturity date",
    "settlement date",
    "issue date",
    "observation date",
]


def extract_text_from_html(html_content: str) -> str:
    """Extract plain text from HTML content."""
    logger.debug(f"Extracting text from HTML ({len(html_content)} characters)")
    soup = BeautifulSoup(html_content, "lxml")
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    text = soup.get_text(separator=" ")
    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = " ".join(chunk for chunk in chunks if chunk)
    logger.debug(f"Extracted {len(text)} characters of text")
    return text


def extract_symbols(content: str, is_html: bool = False, additional_symbols: Optional[List[str]] = None) -> Dict[str, any]:
    """
    Extract index references and ticker symbols from filing content.

    Args:
        content: The filing content (HTML or plain text)
        is_html: Whether the content is HTML format
        additional_symbols: Optional list of additional symbols to include

    Returns:
        Dictionary containing:
        - indices: List of detected index names
        - yahoo_symbols: List of Yahoo Finance symbol codes
        - raw_tickers: List of raw ticker symbols found
    """
    logger.info(f"Extracting symbols from {'HTML' if is_html else 'text'} content")

    if is_html:
        text = extract_text_from_html(content)
    else:
        text = content

    detected_indices = set()
    yahoo_symbols = set()
    raw_tickers = set()

    # Search for known index names (case-insensitive)
    text_upper = text.upper()
    for index_name, yahoo_symbol in INDEX_MAPPING.items():
        if index_name.upper() in text_upper:
            detected_indices.add(index_name)
            yahoo_symbols.add(yahoo_symbol)
            logger.debug(f"Found index: {index_name} -> {yahoo_symbol}")

    logger.info(f"Detected {len(detected_indices)} known indices")

    # Extract ticker-like patterns (e.g., ^GSPC, AAPL, etc.)
    ticker_pattern = r'\b(\^?[A-Z]{2,5})\b'
    matches = re.findall(ticker_pattern, text)
    for match in matches:
        raw_tickers.add(match)
        # If it starts with ^, it's likely an index symbol
        if match.startswith("^"):
            yahoo_symbols.add(match)

    logger.info(f"Found {len(raw_tickers)} ticker-like patterns")

    # Add additional symbols if provided
    if additional_symbols:
        logger.info(f"Adding {len(additional_symbols)} user-provided symbols")
        for symbol in additional_symbols:
            yahoo_symbols.add(symbol)

    result = {
        "indices": sorted(list(detected_indices)),
        "yahoo_symbols": sorted(list(yahoo_symbols)),
        "raw_tickers": sorted(list(raw_tickers)),
    }

    logger.info(f"Symbol extraction complete: {len(result['yahoo_symbols'])} Yahoo symbols")
    return result


def extract_dates(content: str, is_html: bool = False) -> Dict[str, Optional[str]]:
    """
    Extract key dates from filing content.

    Args:
        content: The filing content (HTML or plain text)
        is_html: Whether the content is HTML format

    Returns:
        Dictionary mapping date types to ISO-formatted date strings
    """
    logger.info(f"Extracting dates from {'HTML' if is_html else 'text'} content")

    if is_html:
        text = extract_text_from_html(content)
    else:
        text = content

    dates = {}

    # Search for dates near keywords
    for keyword in DATE_KEYWORDS:
        # Look for the keyword followed by a date within the next 100 characters
        pattern = re.escape(keyword) + r'[:\s,]*([^\.]{0,100})'
        matches = re.finditer(pattern, text, re.IGNORECASE)

        for match in matches:
            context = match.group(1)
            # Try to extract a date from the context
            extracted_date = extract_date_from_text(context)
            if extracted_date:
                # Normalize the keyword for the dictionary key
                key = keyword.lower().replace(" ", "_")
                if key not in dates:  # Only store the first occurrence
                    dates[key] = extracted_date.strftime("%Y-%m-%d")
                    logger.debug(f"Found {keyword}: {dates[key]}")
                break

    logger.info(f"Date extraction complete: found {len(dates)} dates")
    return dates


def extract_date_from_text(text: str) -> Optional[datetime]:
    """
    Try to extract a date from a piece of text.

    Args:
        text: Text potentially containing a date

    Returns:
        datetime object if a date is found, None otherwise
    """
    # Common date patterns
    date_patterns = [
        r'\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b',  # MM/DD/YYYY or DD-MM-YYYY
        r'\b(\d{4}[/-]\d{1,2}[/-]\d{1,2})\b',  # YYYY-MM-DD
        r'\b([A-Za-z]+ \d{1,2},? \d{4})\b',  # Month DD, YYYY
        r'\b(\d{1,2} [A-Za-z]+ \d{4})\b',  # DD Month YYYY
    ]

    for pattern in date_patterns:
        matches = re.findall(pattern, text)
        for match in matches:
            try:
                # Try to parse the date
                parsed_date = date_parser.parse(match, fuzzy=False)
                return parsed_date
            except (ValueError, TypeError):
                continue

    # Fallback: try fuzzy parsing on the whole text
    try:
        parsed_date = date_parser.parse(text, fuzzy=True)
        return parsed_date
    except (ValueError, TypeError):
        return None
