"""
Improved Streamlit Web Application for Structured Products Analysis

Enhanced with sophisticated parsing logic from single_autocall_local_fixed.py
"""

import streamlit as st
import json
import tempfile
import pandas as pd
import plotly.graph_objects as go
import re
import datetime as dt
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dateutil import parser as dp

from structured_products.pdf import read_filing_content, is_pdf_supported
from structured_products.parser import extract_text_from_html
from structured_products.filing_parser import (
    parse_filing,
    ParsedFiling,
    detect_issuer,
    ISSUER_CONFIGS,
)


# Page configuration
st.set_page_config(
    page_title="Structured Products Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ========== IMPROVED PARSING FUNCTIONS (from reference code) ==========

def parse_date(ds: str) -> Optional[dt.date]:
    """Parse date string with fuzzy matching."""
    try:
        return dp.parse(ds, fuzzy=True).date()
    except Exception:
        return None


DATE_REGEX = re.compile(r"""(?ix)
\b(?:
 (?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|
 Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)
 \s+\d{1,2},\s+\d{4}
 | \d{4}-\d{2}-\d{2}
 | \d{1,2}/\d{1,2}/\d{2,4}
)\b""")


MONEY_RE = re.compile(r"\$?\s*([0-9]{1,3}(?:[,][0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)")
PCT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")


def html_to_text(raw: str) -> str:
    """Convert HTML to plain text using the structured_products parser."""
    try:
        return extract_text_from_html(raw)
    except Exception:
        return raw


def extract_observation_dates_from_tables(html: str, issuer: Optional[str] = None) -> Tuple[List[dt.date], List[str]]:
    """
    Extract observation dates from HTML tables - much more accurate than regex.

    Args:
        html: HTML content to parse
        issuer: Optional issuer name to use issuer-specific date column patterns

    Returns: (dates, debug_info) where debug_info contains details about extraction
    """
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        dates: List[dt.date] = []
        debug_info: List[str] = []

        # Get issuer-specific date column patterns if available
        issuer_patterns = []
        if issuer and issuer in ISSUER_CONFIGS:
            issuer_patterns = ISSUER_CONFIGS[issuer].get("date_column_patterns", [])
            if issuer_patterns:
                debug_info.append(f"Using {issuer}-specific date column patterns: {issuer_patterns}")

        for tbl_idx, tbl in enumerate(soup.find_all("table")):
            rows = []
            for tr in tbl.find_all("tr"):
                cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                if cells:
                    rows.append(cells)

            if not rows:
                continue

            # Check if table looks like an example, hypothetical, or historical data
            # Look for keywords in the entire table text
            table_text = " ".join([" ".join(row) for row in rows])
            if re.search(r"(example|hypothetical|illustrative|for\s+illustration|scenario|assumed|historical|past\s+performance)", table_text, flags=re.I):
                debug_info.append(f"Table {tbl_idx + 1}: Skipping - appears to be example/hypothetical/historical data")
                continue

            # Check for historical price tables by looking at headers
            header_text = " ".join(rows[0])
            if re.search(r"(quarterly\s+(high|low|close)|historical\s+(price|information)|past\s+performance)", header_text, flags=re.I):
                debug_info.append(f"Table {tbl_idx + 1}: Skipping - appears to be historical price table")
                continue

            header = rows[0]
            date_col_idx = None
            matched_header = None

            # Special case: Single-row tables where the row itself contains dates
            # Check if the "header" row contains parseable dates
            if len(rows) == 1:
                found_dates_in_row = []
                for cell in header:
                    d = parse_date(cell)
                    if d:
                        found_dates_in_row.append(d)

                if found_dates_in_row:
                    # Apply validation
                    min_date = min(found_dates_in_row)
                    max_date = max(found_dates_in_row)
                    today = dt.date.today()
                    current_year = today.year

                    # Reject if dates are absurdly old (>20 years) - clearly not observation dates
                    if min_date < today.replace(year=today.year - 20):
                        debug_info.append(f"Table {tbl_idx + 1}: Skipping single-row table - dates too old (earliest: {min_date.isoformat()})")
                        continue

                    # Reject if dates are too far in the future (likely hypothetical/examples)
                    if max_date.year > current_year + 10:
                        debug_info.append(f"Table {tbl_idx + 1}: Skipping single-row table - dates too far in future (year {max_date.year})")
                        continue

                    # Valid single-row table with dates
                    debug_info.append(f"Table {tbl_idx + 1}: Single-row table with dates: {[d.strftime('%m-%d-%Y') for d in found_dates_in_row]}")
                    dates.extend(found_dates_in_row)
                    continue  # Skip normal processing for this table

            # First pass: Try issuer-specific patterns if available
            if issuer_patterns:
                for j, h in enumerate(header):
                    # Skip headers that are paragraph-length text (descriptions, not column names)
                    if len(h) > 80:
                        continue

                    # Skip payment date columns
                    if re.search(r"(contingent\s+payment|coupon\s+payment|payment\s+date)", h, flags=re.I):
                        debug_info.append(f"Table {tbl_idx + 1}: Skipping payment date column: '{h}'")
                        continue

                    # Check against issuer-specific patterns
                    # Strip asterisks and other special characters from header for matching
                    h_clean = h.replace('*', '').strip()
                    for pattern in issuer_patterns:
                        if re.search(pattern, h_clean, flags=re.I):
                            date_col_idx = j
                            matched_header = h
                            debug_info.append(f"Table {tbl_idx + 1}: Matched {issuer} pattern '{pattern}' in column '{h}' (cleaned: '{h_clean}')")
                            break
                    if date_col_idx is not None:
                        break

            # Second pass: Generic patterns if no issuer match
            if date_col_idx is None:
                for j, h in enumerate(header):
                    # Skip headers that are paragraph-length text (descriptions, not column names)
                    if len(h) > 80:
                        continue

                    # Skip contingent payment dates AND coupon payment dates - we only want observation/determination dates
                    if re.search(r"(contingent\s+payment|coupon\s+payment|payment\s+date)", h, flags=re.I):
                        debug_info.append(f"Table {tbl_idx + 1}: Skipping payment date column: '{h}'")
                        continue

                    # Match observation/determination date columns
                    # Strip asterisks and other special characters from header for matching
                    h_clean = h.replace('*', '').strip()
                    if re.search(r"(coupon\s+determination\s+date|observation\s+date|valuation\s+date|"
                               r"determination\s+date|pricing\s+date|observation\s+period|"
                               r"autocall\s+observation|autocall\s+valuation|review\s+date|"
                               r"monitoring\s+date|fixing\s+date)", h_clean, flags=re.I):
                        date_col_idx = j
                        matched_header = h
                        debug_info.append(f"Table {tbl_idx + 1}: Matched observation date column '{h}' (cleaned: '{h_clean}')")
                        break

            # Third pass: Any column with "date"
            if date_col_idx is None:
                # Try to find any column with "date" in the header
                for j, h in enumerate(header):
                    # Skip paragraph-length headers (descriptions, not column names)
                    if len(h) > 80:
                        continue
                    # Explicitly exclude payment dates, trade dates, maturity dates, and historical quarter dates
                    if "date" in h.lower():
                        if any(exclude in h.lower() for exclude in ["contingent", "payment", "trade", "maturity", "settlement", "quarter"]):
                            continue
                        date_col_idx = j
                        matched_header = h
                        break

            if date_col_idx is None:
                debug_info.append(f"Table {tbl_idx + 1}: No date column found. Headers: {header[:5]}")
                continue

            debug_info.append(f"Table {tbl_idx + 1}: Found date column '{matched_header}' at index {date_col_idx}")

            # For UBS, verify this is the correct table by checking for "Contingent Coupon" or "Contingent Interest" in headers
            if issuer == "UBS":
                has_coupon_column = any(
                    re.search(r"contingent\s+(coupon|interest|payment)", h, flags=re.I)
                    for h in header
                )
                if not has_coupon_column:
                    debug_info.append(f"Table {tbl_idx + 1}: Skipping - UBS table missing 'Contingent Coupon' column")
                    continue
                else:
                    debug_info.append(f"Table {tbl_idx + 1}: ✓ Verified UBS observation table structure")

            # Extract dates from that column
            found_in_table = 0
            extracted_dates = []
            table_dates = []  # Store dates for this table only

            for r in rows[1:]:
                if date_col_idx < len(r):
                    cell_text = r[date_col_idx]
                    # Strip footnote/special characters that EDGAR appends (†, ‡, Ɨ, §, etc.)
                    cell_text = re.sub(r'[†‡Ɨ§¶\u2020\u2021\u0197\u00a7\u00b6]+', '', cell_text)
                    # Remove trailing parenthetical notes like "(determination date)"
                    cell_text = re.sub(r'\s*\([^)]*\)\s*$', '', cell_text).strip()
                    d = parse_date(cell_text)
                    if d:
                        table_dates.append(d)
                        extracted_dates.append(d.isoformat())
                        found_in_table += 1

            # Validate dates before accepting this table
            if table_dates:
                min_date = min(table_dates)
                max_date = max(table_dates)
                today = dt.date.today()
                current_year = today.year
                date_span_years = (max_date - min_date).days / 365.25

                # Reject if dates are absurdly old (>20 years) - clearly not observation dates
                if min_date < today.replace(year=today.year - 20):
                    debug_info.append(f"Table {tbl_idx + 1}: Skipping - dates too old (earliest: {min_date.isoformat()})")
                    continue

                # Reject if dates span >4 years with many dates (likely historical price table)
                # Observation dates typically span 1-3 years with 4-12 dates
                if date_span_years > 4 and len(table_dates) > 15:
                    debug_info.append(f"Table {tbl_idx + 1}: Skipping - appears to be historical table (span: {date_span_years:.1f} years, {len(table_dates)} dates)")
                    continue

                # Reject if dates are too far in the future (likely hypothetical/examples)
                if max_date.year > current_year + 10:
                    debug_info.append(f"Table {tbl_idx + 1}: Skipping - contains dates too far in future (year {max_date.year})")
                    continue

                # If we get here, dates are valid - add them to the main list
                dates.extend(table_dates)
                debug_info.append(f"Table {tbl_idx + 1}: Extracted {found_in_table} dates: {', '.join(extracted_dates[:5])}" +
                                (" ..." if len(extracted_dates) > 5 else ""))

                # For UBS and other issuers, use ONLY the first valid table found
                # This prevents mixing real observation dates with hypothetical examples
                if issuer in ["UBS", "JP Morgan", "Morgan Stanley", "Goldman Sachs", "Bank of America"] and len(table_dates) >= 3:
                    debug_info.append(f"Table {tbl_idx + 1}: Using this table as primary source (found {len(table_dates)} dates for {issuer})")
                    break  # Stop looking for more tables

        unique_dates = sorted(set(dates))
        debug_info.append(f"Total unique dates found: {len(unique_dates)}")

        if unique_dates:
            debug_info.append(f"Date range: {unique_dates[0].isoformat()} to {unique_dates[-1].isoformat()}")

        return unique_dates, debug_info
    except Exception as e:
        return [], [f"Error during extraction: {str(e)}"]


def extract_review_dates_from_text(text: str, issuer: Optional[str] = None) -> Tuple[List[dt.date], List[str]]:
    """
    Extract review/observation dates from text when table extraction fails.
    Looks for patterns like "Review Dates: Jan 1, 2024, Feb 1, 2024, ..."

    Args:
        text: Text content to parse
        issuer: Optional issuer name for issuer-specific patterns

    Returns:
        Tuple of (dates list, debug info list)
    """
    dates = []
    debug_info = []

    # Build patterns based on issuer
    base_patterns = []

    if issuer == "UBS":
        # UBS uses "Determination dates:" (note: lowercase 'd' and often tab after colon)
        base_patterns = [
            r"Determination\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
            r"Observation\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
        ]
        debug_info.append("Using UBS-specific text date patterns")
    elif issuer == "Morgan Stanley":
        # Morgan Stanley uses similar format to UBS: "Determination dates:" with tab
        # Also uses "Redemption determination dates:"
        base_patterns = [
            r"Redemption\s+determination\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
            r"Determination\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
            r"Observation\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
        ]
        debug_info.append("Using Morgan Stanley-specific text date patterns")
    elif issuer == "Goldman Sachs":
        # Goldman Sachs uses "Coupon determination dates:"
        base_patterns = [
            r"Coupon\s+determination\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|$)",
            r"Observation\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|$)",
        ]
        debug_info.append("Using Goldman Sachs-specific text date patterns")
    elif issuer == "JP Morgan":
        # JP Morgan uses "Review dates:"
        base_patterns = [
            r"Review\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|$)",
            r"Observation\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|$)",
        ]
        debug_info.append("Using JP Morgan-specific text date patterns")
    elif issuer == "Bank of America":
        # Bank of America uses "Observation dates:"
        base_patterns = [
            r"Observation\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
            r"Determination\s+dates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to\s+postponement|,?\s+subject\s+to|$)",
        ]
        debug_info.append("Using Bank of America-specific text date patterns")
    else:
        # Generic patterns for all other issuers
        base_patterns = [
            r"Review\s+[Dd]ates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|Interest\s+Payment|Maturity\s+Date|\*?\s*[Ss]ubject|$)",
            r"Observation\s+[Dd]ates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|Interest\s+Payment|Maturity\s+Date|\*?\s*[Ss]ubject|$)",
            r"Determination\s+[Dd]ates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|Interest\s+Payment|Maturity\s+Date|\*?\s*[Ss]ubject|$)",
            r"Coupon\s+[Dd]etermination\s+[Dd]ates[\s:]*[:\t\s]+([^\.]+?)(?:,?\s+subject\s+to|Interest\s+Payment|Maturity\s+Date|\*?\s*[Ss]ubject|$)"
        ]

    for pattern in base_patterns:
        match = re.search(pattern, text, flags=re.I | re.DOTALL)
        if match:
            dates_text = match.group(1)
            debug_info.append(f"Matched pattern: {pattern[:50]}...")
            debug_info.append(f"Extracted text: {dates_text[:100]}...")

            # Find all dates in this text
            date_matches = DATE_REGEX.findall(dates_text)
            debug_info.append(f"Found {len(date_matches)} date strings in text")

            for date_str in date_matches:
                d = parse_date(date_str)
                if d:
                    dates.append(d)

            if dates:
                debug_info.append(f"Successfully parsed {len(dates)} dates from text")
                break  # Found dates, no need to try other patterns

    if not dates:
        debug_info.append("No dates found in text extraction")

    return sorted(set(dates)), debug_info


def parse_dates_comprehensive(raw_content: str, is_html: bool, issuer: Optional[str] = None) -> Dict[str, Any]:
    """Comprehensive date parsing with table extraction.

    Args:
        raw_content: HTML or text content to parse
        is_html: Whether content is HTML
        issuer: Optional issuer name for issuer-specific date extraction
    """
    dates = {}
    debug_info = []

    # Try table extraction first (most accurate)
    if is_html:
        obs_dates, extraction_debug = extract_observation_dates_from_tables(raw_content, issuer)
        debug_info.extend(extraction_debug)
        if obs_dates:
            dates["observation_dates"] = [d.isoformat() for d in obs_dates]
            # For UBS and some other issuers, don't use first observation date as pricing date
            # They have a separate Trade Date field that should be used instead
            if issuer not in ["UBS", "Credit Suisse"]:
                dates["pricing_date"] = obs_dates[0].isoformat()
            dates["maturity_date"] = obs_dates[-1].isoformat()

    # Fallback to text parsing for observation dates if table extraction failed
    text = html_to_text(raw_content) if is_html else raw_content

    if "observation_dates" not in dates or not dates["observation_dates"]:
        debug_info.append("Table extraction found no dates, trying text parsing...")
        text_dates, text_debug = extract_review_dates_from_text(text, issuer)
        debug_info.extend(text_debug)
        if text_dates:
            dates["observation_dates"] = [d.isoformat() for d in text_dates]
            # For UBS and some other issuers, don't use first observation date as pricing date
            if not dates.get("pricing_date") and issuer not in ["UBS", "Credit Suisse"]:
                dates["pricing_date"] = text_dates[0].isoformat()
            if not dates.get("maturity_date"):
                dates["maturity_date"] = text_dates[-1].isoformat()
            debug_info.append(f"Text parsing found {len(text_dates)} observation/review dates")

    # Store debug info
    dates["extraction_debug"] = debug_info

    # Continue with other date parsing
    # (Fallback to text parsing for other dates remains below)

    # Pricing date
    if "pricing_date" not in dates:
        m_pricing = re.search(r"pricing\s+date[^:\n]*[:\-\s]\s*(.+)", text, flags=re.I)
        if m_pricing:
            d = parse_date(m_pricing.group(1))
            if d:
                dates["pricing_date"] = d.isoformat()

    # Trade date
    m_trade = re.search(r"trade\s+date[^:\n]*[:\-\s]\s*(.+)", text, flags=re.I)
    if m_trade:
        d = parse_date(m_trade.group(1))
        if d:
            dates["trade_date"] = d.isoformat()
            # For UBS and other issuers, if no pricing_date found, use trade_date as pricing_date
            if "pricing_date" not in dates and issuer in ["UBS", "Credit Suisse", "Barclays"]:
                dates["pricing_date"] = d.isoformat()
                debug_info.append(f"Using Trade Date as Pricing Date for {issuer}")

    # Maturity date
    if "maturity_date" not in dates:
        m_maturity = re.search(r"maturity\s+date[^:\n]*[:\-\s]\s*(.+)", text, flags=re.I)
        if m_maturity:
            d = parse_date(m_maturity.group(1))
            if d:
                dates["maturity_date"] = d.isoformat()

    # Settlement date
    m_settlement = re.search(r"settlement\s+date[^:\n]*[:\-\s]\s*(.+)", text, flags=re.I)
    if m_settlement:
        d = parse_date(m_settlement.group(1))
        if d:
            dates["settlement_date"] = d.isoformat()

    return dates


def detect_underlying_ticker(text: str, html: Optional[str] = None) -> Optional[str]:
    """
    Detect underlying ticker symbol using multiple strategies.

    Args:
        text: Plain text content
        html: Optional HTML content for table extraction

    Returns:
        Ticker symbol or None
    """
    # Common ETF and fund name to ticker mappings
    ETF_MAPPING = {
        # SPDR ETFs
        "SPDR S&P 500": "SPY",
        "SPDR S&P OIL & GAS EXPLORATION & PRODUCTION": "XOP",
        "SPDR S&P OIL & GAS EXPLORATION": "XOP",
        "SPDR GOLD": "GLD",
        "SPDR GOLD SHARES": "GLD",
        "SPDR S&P BIOTECH": "XBI",
        "SPDR S&P RETAIL": "XRT",
        "SPDR S&P REGIONAL BANKING": "KRE",
        "SPDR S&P HOMEBUILDERS": "XHB",
        # iShares ETFs
        "ISHARES RUSSELL 2000": "IWM",
        "ISHARES MSCI EMERGING MARKETS": "EEM",
        "ISHARES MSCI EAFE": "EFA",
        "ISHARES 20+ YEAR TREASURY": "TLT",
        "ISHARES CORE S&P 500": "IVV",
        "ISHARES BIOTECHNOLOGY": "IBB",
        # Invesco ETFs
        "INVESCO QQQ": "QQQ",
        "POWERSHARES QQQ": "QQQ",
        "INVESCO S&P 500": "SPY",
        # Vanguard ETFs
        "VANGUARD S&P 500": "VOO",
        "VANGUARD TOTAL STOCK MARKET": "VTI",
        "VANGUARD FTSE EMERGING MARKETS": "VWO",
        # Sector ETFs
        "ENERGY SELECT SECTOR SPDR": "XLE",
        "FINANCIAL SELECT SECTOR SPDR": "XLF",
        "TECHNOLOGY SELECT SECTOR SPDR": "XLK",
        "HEALTH CARE SELECT SECTOR SPDR": "XLV",
        "CONSUMER DISCRETIONARY SELECT SECTOR": "XLY",
        "CONSUMER STAPLES SELECT SECTOR": "XLP",
        "INDUSTRIAL SELECT SECTOR": "XLI",
        "UTILITIES SELECT SECTOR": "XLU",
        "MATERIALS SELECT SECTOR": "XLB",
        "REAL ESTATE SELECT SECTOR": "XLRE",
        "COMMUNICATION SERVICES SELECT SECTOR": "XLC",
        # Leveraged/Inverse ETFs (common in structured products)
        "PROSHARES ULTRA S&P500": "SSO",
        "PROSHARES ULTRASHORT S&P500": "SDS",
        "DIREXION DAILY SEMICONDUCTOR": "SOXL",
        # ARK ETFs
        "ARK INNOVATION": "ARKK",
        "ARK GENOMIC REVOLUTION": "ARKG",
        "ARK FINTECH INNOVATION": "ARKF",
    }

    # Strategy 1: Check ETF/fund name mappings
    text_upper = text.upper()
    for fund_name, ticker in ETF_MAPPING.items():
        if fund_name in text_upper:
            return ticker

    # Strategy 2: Look for explicit "Underlying: TICKER" patterns
    patterns = [
        r"underlying[^:\n]*:\s*([A-Z]{1,5})\b",
        r"ticker[^:\n]*:\s*([A-Z]{1,5})\b",
        r"symbol[^:\n]*:\s*([A-Z]{1,5})\b",
        r"(?:common\s+)?stock\s+of\s+([A-Z]{1,5})\b",
        r"\(ticker:\s*([A-Z]{1,5})\)",
        r"\(symbol:\s*([A-Z]{1,5})\)",
    ]

    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            ticker = m.group(1).upper()
            # Filter out common false positives
            if ticker not in ["THE", "AND", "FOR", "EACH", "PER", "DATE", "PRICE", "LEVEL", "VALUE", "FROM", "WILL"]:
                return ticker

    # Strategy 3: Extract from tables (if HTML provided)
    if html:
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")

            for tbl in soup.find_all("table"):
                rows = []
                for tr in tbl.find_all("tr"):
                    cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
                    if cells:
                        rows.append(cells)

                if not rows:
                    continue

                # Look for ticker/symbol column
                header = rows[0]
                ticker_col_idx = None

                for j, h in enumerate(header):
                    if re.search(r"(ticker|symbol|underlying)", h, flags=re.I):
                        ticker_col_idx = j
                        break

                if ticker_col_idx is not None and len(rows) > 1:
                    # Extract from first data row
                    if ticker_col_idx < len(rows[1]):
                        ticker_candidate = rows[1][ticker_col_idx].strip()
                        # Check if it looks like a ticker (1-5 uppercase letters)
                        if re.match(r'^[A-Z]{1,5}$', ticker_candidate):
                            return ticker_candidate
        except:
            pass  # Fall through to next strategy

    # Strategy 4: Look for common stock patterns like "shares of AAPL" or "Apple Inc. (AAPL)"
    m = re.search(r'\(([A-Z]{1,5})\)', text)
    if m:
        ticker = m.group(1).upper()
        if ticker not in ["THE", "AND", "FOR", "EACH", "PER", "NYSE", "NASDAQ"]:
            return ticker

    # Strategy 5: Use structured_products library as fallback
    try:
        from structured_products.parser import extract_symbols
        symbols = extract_symbols(text, is_html=False)

        # Prefer raw_tickers that aren't indices (no ^ prefix)
        for ticker in symbols.get("raw_tickers", []):
            if not ticker.startswith("^") and len(ticker) <= 5:
                # Filter out common false positives
                if ticker not in ["THE", "AND", "FOR", "EACH", "PER", "DATE", "PRICE", "LEVEL", "VALUE", "FROM", "WILL", "USD", "HTML"]:
                    return ticker
    except:
        pass

    return None


# ========== STREAMLIT UI FUNCTIONS ==========

def display_header():
    """Display application header."""
    st.markdown('<div class="main-header">📊 Structured Products Analyzer (Enhanced)</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Advanced parsing with table extraction and context-aware logic</div>',
        unsafe_allow_html=True
    )


def display_sidebar():
    """Display sidebar with options."""
    st.sidebar.header("📊 About")

    st.sidebar.markdown("""
    **Structured Products Analyzer**

    Upload EDGAR filing (HTML/PDF) to analyze:
    - Initial price & thresholds
    - Autocall/early redemption levels
    - Observation dates
    - Coupon payments
    - Price history & triggers
    """)

    st.sidebar.divider()

    st.sidebar.subheader("📁 File Support")
    if is_pdf_supported():
        st.sidebar.success("✅ PDF & HTML supported")
        max_pdf_pages = st.sidebar.number_input(
            "Max PDF Pages",
            min_value=1,
            max_value=1000,
            value=50,
            help="Limit pages to read from PDF files"
        )
    else:
        st.sidebar.info("✅ HTML files supported")
        st.sidebar.caption("💡 Install pdfplumber for PDF support:\n`pip install pdfplumber`")
        max_pdf_pages = None

    st.sidebar.divider()

    # Bank terminology reference
    st.sidebar.subheader("📖 Bank Terminology Reference")
    with st.sidebar.expander("View terminology differences across banks"):
        st.caption("**How different banks refer to the same concepts:**")

        # Create terminology comparison
        terminology_data = {
            "Concept": ["Initial Price", "Downside Threshold", "Autocall Trigger", "Coupon Payment", "Observation Dates"],
            "Goldman Sachs": [
                "Initial share price",
                "Downside threshold level",
                "≥ initial share price",
                "Contingent quarterly coupon",
                "Coupon determination date"
            ],
            "JP Morgan": [
                "Initial Value",
                "Interest Barrier / Trigger Value",
                "Automatically called",
                "Contingent Interest Payment",
                "Review date"
            ],
            "UBS": [
                "Initial price",
                "Downside threshold level",
                "Call threshold level",
                "Contingent Interest Payment",
                "Determination date"
            ],
            "Morgan Stanley": [
                "Initial price / Value",
                "Threshold level",
                "Redemption threshold",
                "Contingent Interest Payment",
                "Redemption determination date"
            ],
            "Bank of America": [
                "Initial price / Value",
                "Threshold level",
                "Call threshold / Autocall",
                "Contingent Interest Payment",
                "Observation dates"
            ],
            "Other Banks": [
                "Various formats",
                "Threshold level / Barrier",
                "Early redemption / Call",
                "Payment per period",
                "Determination date"
            ]
        }

        df_terms = pd.DataFrame(terminology_data)
        st.dataframe(df_terms, hide_index=True, use_container_width=True)

        st.caption("💡 **Tip:** Select the correct issuer above for more accurate parsing!")

    st.sidebar.divider()

    st.sidebar.caption("Advanced parsing with context-aware logic, table extraction, and multi-issuer support.")

    return {
        "use_advanced_parsing": True,  # Always use advanced parsing
        "analysis_type": "Autocallable Note Analysis",  # Always autocallable
        "max_pdf_pages": max_pdf_pages
    }


@st.cache_data(show_spinner=False)
def _cached_parse_filing(content: str, is_html: bool, issuer: str) -> Dict[str, Any]:
    """Cached wrapper around parse_filing to avoid re-parsing the same content."""
    filing = parse_filing(content, is_html, issuer)
    return filing.to_dict()


def analyze_filing_advanced(content: str, is_html: bool, options: Dict[str, Any], issuer: str = "Auto-detect") -> Dict[str, Any]:
    """Analyze filing with the unified 3-tier parsing pipeline.

    Tier 1: HTML table extraction (highest confidence)
    Tier 2: Issuer-specific regex
    Tier 3: Generic regex fallbacks
    """
    result = {}

    with st.spinner("Parsing with table-first pipeline..."):
        # Run the unified pipeline (cached by content + issuer)
        parsed = _cached_parse_filing(content, is_html, issuer)

        # Report issuer detection
        detected_issuer = parsed.get("issuer")
        if detected_issuer:
            if detected_issuer in ISSUER_CONFIGS:
                st.success(f"Detected issuer: **{detected_issuer}** (issuer-specific patterns active)")
            else:
                st.info(f"Detected issuer: **{detected_issuer}** (using generic parsing)")
        else:
            st.info("Using generic parsing (issuer not detected)")

        # Copy core fields to result
        result["initial_price"] = parsed.get("initial_price")
        result["threshold_dollar"] = parsed.get("threshold_dollar")
        result["threshold_pct"] = parsed.get("threshold_pct")
        result["autocall_level"] = parsed.get("autocall_level")
        result["coupon_rate_annual"] = parsed.get("coupon_rate_annual")
        result["coupon_payment_per_period"] = parsed.get("coupon_payment_per_period")
        result["contingent_payment_pct"] = parsed.get("contingent_payment_pct")
        result["notional"] = parsed.get("notional")
        result["issuer"] = detected_issuer

        # Parse dates (stays in streamlit_app.py — specialized logic)
        text = html_to_text(content) if is_html else content
        dates = parse_dates_comprehensive(
            content, is_html, detected_issuer if detected_issuer else None
        )
        result["dates"] = dates

        # Ticker detection (stays here — uses multi-strategy chain)
        ticker = detect_underlying_ticker(text, html=content if is_html else None)
        result["ticker"] = ticker

        # Show extraction sources in an expander
        sources = parsed.get("extraction_sources", {})
        warnings = parsed.get("validation_warnings", [])
        if sources or warnings:
            with st.expander("Extraction metadata"):
                if sources:
                    st.caption("**Field sources** (where each value was extracted from):")
                    for field_name, source in sorted(sources.items()):
                        st.text(f"  {field_name}: {source}")
                if warnings:
                    st.caption("**Validation warnings:**")
                    for w in warnings:
                        st.warning(w)

        st.success("Parsing complete")

    return result


def format_date_us(date_str: str) -> str:
    """Format ISO date (YYYY-MM-DD) to US format (MM-DD-YYYY)."""
    if not date_str or date_str == "N/A":
        return "N/A"
    try:
        date_obj = dt.datetime.fromisoformat(date_str).date()
        return date_obj.strftime("%m-%d-%Y")
    except:
        return date_str


def display_parsing_results(result: Dict[str, Any]):
    """Display parsed results with edit capability."""
    # Header with Clear button
    col1, col2 = st.columns([5, 1])
    with col1:
        st.header("📋 Parsed Information")
    with col2:
        st.write("")  # Spacing
        if st.button("🗑️ Clear All", help="Clear all parsed data and start over"):
            # Clear all session state
            st.session_state.clear()
            st.rerun()

    # Display extraction debug info at the top, separated from data inputs
    dates = result.get("dates", {})
    if dates.get("extraction_debug"):
        with st.expander("🔍 Date Extraction Debug Information (Advanced)"):
            st.caption("This section shows technical details about how dates were extracted from the filing.")
            for info in dates["extraction_debug"]:
                st.text(info)

    # Product Type Selector
    st.subheader("🧩 Product Type")
    product_type = st.radio(
        "Select the autocallable structure:",
        ["Single Stock", "Worst-Of (2 Assets)"],
        help="Choose 'Worst-Of' if the note is linked to 2 stocks where the worst performer determines the payout"
    )

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Pricing Parameters")

        initial = st.number_input(
            "Initial Share Price ($)",
            value=float(result.get("initial_price") or 0),
            format="%.4f",
            help="Extracted initial price"
        )

        # Threshold inputs with automatic calculation
        st.write("**Threshold Level**")

        threshold_dollar = st.number_input(
            "Threshold ($)",
            value=float(result.get("threshold_dollar") or 0),
            format="%.4f",
            help="Threshold in dollars",
            key="threshold_dollar_input"
        )

        # Display calculated threshold percentage
        if initial > 0 and threshold_dollar > 0:
            threshold_pct = (threshold_dollar / initial) * 100
            st.caption(f"**Threshold %:** {threshold_pct:.2f}% (${threshold_dollar:.2f} = {threshold_pct:.2f}% of ${initial:.2f})")
        else:
            threshold_pct = 0.0
            st.caption("**Threshold %:** Enter Threshold $ and Initial Price to calculate")

        st.divider()

        autocall = st.number_input(
            "Autocall Level ($)",
            value=float(result.get("autocall_level") or initial or 0),
            format="%.4f",
            help="Autocall trigger level"
        )

        # Show autocall as % of initial
        if initial > 0 and autocall > 0:
            autocall_pct = (autocall / initial) * 100
            st.caption(f"Autocall: {autocall_pct:.2f}% of initial")

    with col2:
        st.subheader("Product Details")

        if product_type == "Single Stock":
            ticker = st.text_input(
                "Underlying Ticker",
                value=result.get("ticker") or "TICKER",
                help="Stock ticker symbol"
            ).upper()
            ticker_b = None
            initial_b = None
        else:  # Worst-Of (2 Assets)
            col_a, col_b = st.columns(2)
            with col_a:
                ticker = st.text_input(
                    "Stock A Ticker",
                    value=result.get("ticker") or "TICKER",
                    help="First stock ticker symbol"
                ).upper()
            with col_b:
                ticker_b = st.text_input(
                    "Stock B Ticker",
                    value="TICKER",
                    help="Second stock ticker symbol"
                ).upper()

            # Initial prices for both stocks (worst-of needs both)
            col_a, col_b = st.columns(2)
            with col_a:
                st.caption(f"**Stock A ({ticker}) Initial Price:**")
                # Use the parsed initial price for Stock A
            with col_b:
                initial_b = st.number_input(
                    f"Stock B ({ticker_b}) Initial ($)",
                    value=100.0,
                    format="%.4f",
                    help="Initial price for Stock B",
                    key="initial_b"
                )

        # Use detected notional if available, otherwise default to 1000.0
        detected_notional = result.get("notional") or 1000.0
        notional = st.number_input(
            "Notional Amount ($)",
            value=float(detected_notional),
            format="%.2f",
            help="Investment amount (auto-detected from filing if available)"
        )

        # Show info if notional was detected
        if result.get("notional"):
            st.info(f"📊 **Detected notional:** ${result.get('notional'):,.2f} from filing")

        # Calculate default contingent payment percentage from parsed dollar amount if available
        default_contingent_pct = 0.0
        if result.get("coupon_payment_per_period") and notional > 0:
            default_contingent_pct = (result["coupon_payment_per_period"] / notional) * 100.0

        # Contingent payment percentage per period
        contingent_payment_pct = st.number_input(
            "Contingent Payment (%)",
            value=float(result.get("contingent_payment_pct") or default_contingent_pct),
            format="%.4f",
            help="Percentage payment per period (e.g., 2.625% per period)"
        )

        # Convert to decimal for calculations
        coupon_rate_decimal = contingent_payment_pct / 100.0

        # Default to quarterly payments for backwards compatibility
        payments_per_year = 4

    # Dates
    st.subheader("Key Dates")
    dates = result.get("dates", {})

    col1, col2, col3 = st.columns(3)
    col1.metric("Pricing Date", format_date_us(dates.get("pricing_date", "N/A")))
    col2.metric("Settlement Date", format_date_us(dates.get("settlement_date", "N/A")))
    col3.metric("Maturity Date", format_date_us(dates.get("maturity_date", "N/A")))

    # Editable Observation Dates
    st.subheader("📅 Observation Dates (Editable)")

    # Initialize session state for observation dates if not present
    if "edited_observation_dates" not in st.session_state:
        if "observation_dates" in dates:
            st.session_state["edited_observation_dates"] = [
                dt.datetime.fromisoformat(d).date() for d in dates["observation_dates"]
            ]
        else:
            st.session_state["edited_observation_dates"] = []

    # Display info about detected dates
    if "observation_dates" in dates:
        st.info(f"ℹ️ Detected {len(dates['observation_dates'])} observation dates from filing. You can edit, add, or remove dates below.")

    # Check if any date should be removed (button clicks set this)
    remove_idx = None
    for idx in range(len(st.session_state["edited_observation_dates"])):
        if st.session_state.get(f"remove_flag_{idx}", False):
            remove_idx = idx
            st.session_state[f"remove_flag_{idx}"] = False  # Reset flag
            break

    # If a removal was requested, remove it, clear all text input states, and rerun
    if remove_idx is not None:
        st.session_state["edited_observation_dates"].pop(remove_idx)
        # Clear all text input widget states to force fresh render
        keys_to_clear = [k for k in st.session_state.keys() if k.startswith("obs_date_text_") or k.startswith("remove_")]
        for k in keys_to_clear:
            del st.session_state[k]
        st.rerun()

    # Display each date as an editable line item with text input
    # Use a unique key that includes the date value to prevent key reuse issues
    for idx, obs_date in enumerate(st.session_state["edited_observation_dates"]):
        col1, col2 = st.columns([4, 0.5])

        # Create unique key based on index and date value hash
        date_key = f"obs_date_{idx}_{hash(obs_date)}"

        # Text input for easy date entry (format: MM-DD-YYYY)
        with col1:
            date_str = st.text_input(
                f"Observation Date #{idx + 1}",
                value=obs_date.strftime("%m-%d-%Y"),
                key=date_key,
                help="Format: MM-DD-YYYY or YYYY-MM-DD or MM/DD/YYYY"
            )

        # Remove button
        with col2:
            if st.button("🗑️", key=f"remove_{idx}", help="Remove this date"):
                # Set flag to remove this specific index
                st.session_state[f"remove_flag_{idx}"] = True
                st.rerun()

        # Parse text input and update in place
        if date_str != obs_date.strftime("%m-%d-%Y"):
            try:
                parsed_date = parse_date(date_str)
                if parsed_date:
                    st.session_state["edited_observation_dates"][idx] = parsed_date
                else:
                    st.error(f"Could not parse date: {date_str}")
            except Exception as e:
                st.error(f"Invalid date format: {date_str}")

    # Add new date button
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("➕ Add Date"):
            # Add today's date as default
            st.session_state["edited_observation_dates"].append(dt.date.today())
            st.rerun()
    with col2:
        if st.button("🔄 Reset to Detected Dates"):
            if "observation_dates" in dates:
                st.session_state["edited_observation_dates"] = [
                    dt.datetime.fromisoformat(d).date() for d in dates["observation_dates"]
                ]
                st.rerun()

    # Store edited dates in proper format
    dates["observation_dates"] = [d.isoformat() for d in st.session_state["edited_observation_dates"]]

    # Return updated values
    return {
        "product_type": product_type,
        "initial": initial,
        "threshold_dollar": threshold_dollar,
        "threshold_pct": threshold_pct,
        "autocall_level": autocall,
        "coupon_rate": coupon_rate_decimal,  # Already in decimal form
        "contingent_payment_pct": contingent_payment_pct,
        "ticker": ticker,
        "ticker_b": ticker_b,
        "initial_b": initial_b,
        "notional": notional,
        "payments_per_year": payments_per_year,
        "dates": dates
    }


def main():
    """Main application."""
    display_header()

    # Sidebar options
    options = display_sidebar()

    # File upload
    st.header("📁 Upload Filing")

    uploaded_file = st.file_uploader(
        "Choose a filing file",
        type=["html", "htm", "txt", "pdf"],
        help="Upload an EDGAR filing"
    )

    if uploaded_file is not None:
        # Read file
        file_extension = Path(uploaded_file.name).suffix.lower()

        try:
            if file_extension == ".pdf":
                if not is_pdf_supported():
                    st.error("PDF support not available. Install: pip install pdfplumber")
                    return

                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_path = tmp_file.name

                content, is_html = read_filing_content(tmp_path, max_pdf_pages=options["max_pdf_pages"])
                Path(tmp_path).unlink()
            else:
                # Try multiple encodings
                raw_bytes = uploaded_file.read()
                encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
                content = None

                for encoding in encodings_to_try:
                    try:
                        content = raw_bytes.decode(encoding)
                        st.info(f"✅ File decoded using {encoding} encoding")
                        break
                    except UnicodeDecodeError:
                        continue

                if content is None:
                    content = raw_bytes.decode('utf-8', errors='replace')
                    st.warning("⚠️ Some characters may be replaced")

                is_html = file_extension in [".html", ".htm"] or content.strip().startswith("<")

            st.success(f"✅ Loaded {uploaded_file.name} ({len(content):,} characters)")

            # Issuer selection
            st.subheader("🏦 Select Issuer")
            issuer = st.selectbox(
                "Choose the issuing bank (or let the system auto-detect):",
                ["Auto-detect", "Goldman Sachs", "JP Morgan", "UBS", "Morgan Stanley",
                 "Credit Suisse", "HSBC", "Citigroup", "Barclays", "Bank of America",
                 "Royal Bank of Canada", "Bank of Montreal", "CIBC"],
                help="Select the investment bank that issued this structured product for more accurate parsing"
            )

            # Analyze with advanced parsing
            if st.button("🚀 Analyze Filing", type="primary", use_container_width=True):
                result = analyze_filing_advanced(content, is_html, options, issuer=issuer)

                # Store in session state
                st.session_state["parsed_result"] = result
                st.session_state["content"] = content
                st.session_state["is_html"] = is_html

        except Exception as e:
            st.error(f"Error loading file: {e}")
            return

    # Display results if available
    if "parsed_result" in st.session_state:
        st.markdown("---")

        # Display and allow editing
        confirmed_params = display_parsing_results(st.session_state["parsed_result"])

        # Store confirmed params
        st.session_state["confirmed_params"] = confirmed_params

        st.markdown("---")

        # Analysis buttons
        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 Download Parsed Data", use_container_width=True):
                json_str = json.dumps(confirmed_params, indent=2)
                st.download_button(
                    label="📥 Download JSON",
                    data=json_str,
                    file_name="parsed_data.json",
                    mime="application/json"
                )

        with col2:
            if st.button("📊 Run Full Analysis", use_container_width=True, type="primary"):
                if confirmed_params.get("product_type") == "Worst-Of (2 Assets)":
                    run_worst_of_analysis(confirmed_params)
                else:
                    run_full_analysis(confirmed_params)


@st.cache_data(ttl=300, show_spinner=False)
def _cached_yf_download(ticker: str, start: str, end: str):
    """Cached yfinance download (5-minute TTL) to avoid repeated API calls."""
    import yfinance as yf
    return yf.download(ticker, start=start, end=end, progress=False, auto_adjust=False)


def run_full_analysis(params: Dict[str, Any]):
    """Run full analysis with price fetching and visualization."""
    import yfinance as yf

    ticker = params.get("ticker")
    dates_dict = params.get("dates", {})
    observation_dates = dates_dict.get("observation_dates", [])

    if not ticker or ticker == "TICKER":
        st.error("❌ Please specify a valid ticker symbol")
        return

    if not observation_dates:
        st.warning("⚠️ No observation dates found. Using key dates instead...")
        # Use other dates if available
        date_keys = ["pricing_date", "trade_date", "settlement_date", "maturity_date"]
        observation_dates = [dates_dict[k] for k in date_keys if k in dates_dict and dates_dict[k]]

    if not observation_dates:
        st.error("❌ No dates available for analysis")
        return

    # Convert to date objects
    date_objects = [dt.datetime.fromisoformat(d).date() for d in observation_dates]
    date_objects.sort()

    st.header("💰 Price Analysis")

    with st.spinner(f"Fetching prices for {ticker}..."):
        try:
            # Fetch prices for date range
            start_date = date_objects[0] - dt.timedelta(days=14)
            end_date = date_objects[-1] + dt.timedelta(days=2)

            df_prices = _cached_yf_download(
                ticker,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )

            if df_prices.empty:
                st.error(f"No price data found for {ticker}")
                return

            st.success(f"Fetched {len(df_prices)} price records")

            # Build observation table
            obs_data = []
            for obs_date in date_objects:
                # Find close on or before obs_date
                prices_before = df_prices[df_prices.index.date <= obs_date]
                if not prices_before.empty:
                    close_price = float(prices_before['Close'].iloc[-1])
                    actual_date = prices_before.index[-1].date()

                    row = {
                        "Observation Date": obs_date.strftime("%m-%d-%Y"),
                        "Actual Date": actual_date.strftime("%m-%d-%Y"),
                        "Close": close_price,
                        "Initial": params.get("initial", 0),
                        "Threshold": params.get("threshold_dollar", 0),
                        "Autocall Level": params.get("autocall_level", 0)
                    }

                    # Checks
                    if params.get("threshold_dollar"):
                        row["Above Threshold"] = close_price >= params["threshold_dollar"]
                    if params.get("autocall_level"):
                        # EXPLICIT: Autocall triggers when price >= autocall level (greater than or equal to)
                        row["Autocall Triggered"] = close_price >= params["autocall_level"]
                    if params.get("initial"):
                        row["% of Initial"] = f"{(close_price / params['initial']) * 100:.2f}%"

                    obs_data.append(row)

            if not obs_data:
                st.error("❌ Could not match prices to observation dates")
                return

            df_obs = pd.DataFrame(obs_data)

            # Display table
            st.subheader("📊 Observation Schedule")
            st.dataframe(df_obs, use_container_width=True)

            # Price chart
            st.subheader("📈 Price History")
            fig = go.Figure()

            fig.add_trace(go.Candlestick(
                x=df_prices.index,
                open=df_prices['Open'],
                high=df_prices['High'],
                low=df_prices['Low'],
                close=df_prices['Close'],
                name=ticker
            ))

            # Add threshold line
            if params.get("threshold_dollar"):
                fig.add_hline(
                    y=params["threshold_dollar"],
                    line_dash="dash",
                    line_color="red",
                    annotation_text="Threshold"
                )

            # Add autocall line
            if params.get("autocall_level"):
                fig.add_hline(
                    y=params["autocall_level"],
                    line_dash="dash",
                    line_color="green",
                    annotation_text="Autocall Level"
                )

            # Add initial price line
            if params.get("initial"):
                fig.add_hline(
                    y=params["initial"],
                    line_dash="dot",
                    line_color="blue",
                    annotation_text="Initial"
                )

            # Add observation date markers showing actual stock prices
            obs_dates_for_chart = []
            obs_prices_for_chart = []
            obs_labels = []

            for idx, row in enumerate(obs_data):
                # Parse date from MM-DD-YYYY format
                actual_date = parse_date(row["Actual Date"])
                close_price = row["Close"]
                obs_dates_for_chart.append(actual_date)
                obs_prices_for_chart.append(close_price)

                # Create label with price and autocall status (date already in MM-DD-YYYY format)
                label = f"Obs #{idx+1}<br>Date: {row['Observation Date']}<br>Price: ${close_price:.2f}"
                if row.get("Autocall Triggered"):
                    label += "<br>✅ AUTOCALLED"
                elif row.get("Above Threshold") is not None:
                    label += "<br>✓ Above Threshold" if row["Above Threshold"] else "<br>✗ Below Threshold"
                obs_labels.append(label)

            fig.add_trace(go.Scatter(
                x=obs_dates_for_chart,
                y=obs_prices_for_chart,
                mode='markers+text',
                marker=dict(
                    size=12,
                    color=['green' if obs_data[i].get("Autocall Triggered") else 'orange'
                           for i in range(len(obs_data))],
                    symbol='diamond',
                    line=dict(width=2, color='white')
                ),
                text=[f"#{i+1}" for i in range(len(obs_data))],
                textposition="top center",
                textfont=dict(size=10, color='black'),
                name='Observation Dates',
                hovertext=obs_labels,
                hoverinfo='text'
            ))

            fig.update_layout(
                title=f"{ticker} Price Chart with Observation Dates",
                yaxis_title="Price ($)",
                xaxis_title="Date",
                height=500,
                xaxis_rangeslider_visible=False,
                showlegend=True
            )

            st.plotly_chart(fig, use_container_width=True)

            # Autocall analysis
            st.subheader("🔔 Autocall Analysis")

            # Explicit explanation of autocall trigger logic
            st.info(
                "ℹ️ **Autocall Trigger Logic:** The product is automatically called when the "
                f"closing price is **greater than or equal to (≥)** the autocall level "
                f"(${params.get('autocall_level', 0):.2f}). The first observation date is typically "
                "not eligible for autocall."
            )

            autocalled = False
            call_date = None

            for idx, row in df_obs.iterrows():
                if idx > 0 and row.get("Autocall Triggered"):  # First observation usually not eligible
                    autocalled = True
                    call_date = row["Observation Date"]
                    break

            # Get parameters early for use in all sections
            coupon_rate = params.get("coupon_rate", 0)
            notional = params.get("notional", 1000)
            payments_per_year = params.get("payments_per_year", 4)
            threshold = params.get("threshold_dollar", 0)
            initial = params.get("initial", 1)

            if autocalled:
                st.success(f"✅ **AUTOCALLED** on {call_date}")
                st.write(f"Product would be called early. Investor receives principal plus accrued coupons.")
            else:
                st.info("ℹ️ **Not Autocalled** - Product runs to maturity")

                final_price = obs_data[-1]["Close"]

                if final_price >= threshold:
                    st.success(f"✅ Final price (${final_price:.2f}) ≥ Threshold (${threshold:.2f})")
                    st.write("Investor receives 100% of principal plus all coupons")
                else:
                    loss_pct = ((final_price - initial) / initial) * 100
                    st.error(f"❌ Final price (${final_price:.2f}) < Threshold (${threshold:.2f})")

                    # Show principal loss prominently
                    st.subheader("⚠️ Principal Loss (Downside Participation)")
                    principal_loss_dollars = notional * (loss_pct / 100)
                    principal_returned_downside = notional + principal_loss_dollars

                    col1, col2, col3 = st.columns(3)
                    col1.metric(
                        "Principal Loss %",
                        f"{loss_pct:.2f}%",
                        delta=f"{loss_pct:.2f}%",
                        delta_color="inverse"
                    )
                    col2.metric(
                        "Principal Loss $",
                        f"${abs(principal_loss_dollars):.2f}",
                        delta=f"-${abs(principal_loss_dollars):.2f}",
                        delta_color="inverse"
                    )
                    col3.metric(
                        "Principal Returned",
                        f"${principal_returned_downside:.2f}",
                        delta=f"${principal_loss_dollars:.2f}",
                        delta_color="inverse"
                    )

            # Coupon summary
            st.subheader("💵 Contingent Payment Summary")

            if coupon_rate > 0:
                coupon_per_period = notional * (coupon_rate / payments_per_year)

                eligible_periods = 0
                for idx, row in df_obs.iterrows():
                    if autocalled and idx > df_obs[df_obs["Observation Date"] == call_date].index[0]:
                        break
                    if row.get("Above Threshold"):
                        eligible_periods += 1

                total_coupons = eligible_periods * coupon_per_period

                col1, col2, col3 = st.columns(3)
                col1.metric("Contingent Payment per Period", f"${coupon_per_period:.2f}")
                col2.metric("Eligible Periods", eligible_periods)
                col3.metric("Total Payments", f"${total_coupons:.2f}")

                # Total return
                st.subheader("📊 Total Return (Principal + Contingent Payments)")

                if autocalled:
                    principal_return = notional
                    total_return = principal_return + total_coupons
                    return_pct = ((total_return - notional) / notional) * 100

                    col1, col2, col3 = st.columns(3)
                    col1.metric("Principal Returned", f"${principal_return:.2f}")
                    col2.metric("Total Return", f"${total_return:.2f}")
                    col3.metric("Return %", f"{return_pct:.2f}%")
                else:
                    final_price = obs_data[-1]["Close"]

                    if final_price >= threshold:
                        principal_return = notional
                    else:
                        principal_return = notional * (final_price / initial)

                    total_return = principal_return + total_coupons
                    return_pct = ((total_return - notional) / notional) * 100

                    col1, col2, col3 = st.columns(3)
                    col1.metric("Principal Returned", f"${principal_return:.2f}",
                              delta=f"{principal_return - notional:.2f}" if principal_return != notional else None)
                    col2.metric("Total Return", f"${total_return:.2f}")
                    col3.metric("Return %", f"{return_pct:.2f}%",
                              delta_color="inverse" if return_pct < 0 else "normal")

                    # Add explanation if there's downside participation
                    if final_price < threshold:
                        principal_loss_pct = ((principal_return - notional) / notional) * 100
                        payment_offset_pct = return_pct - principal_loss_pct
                        st.info(
                            f"💡 **Explanation:** The contingent payments (${total_coupons:.2f}) offset "
                            f"**{abs(payment_offset_pct):.2f}%** of your principal loss. "
                            f"Principal loss: {principal_loss_pct:.2f}% + Payments: +{payment_offset_pct:.2f}% = "
                            f"Total return: {return_pct:.2f}%"
                        )

            # Download results
            st.subheader("💾 Download Results")

            results_dict = {
                "ticker": ticker,
                "parameters": params,
                "observation_schedule": df_obs.to_dict(orient="records"),
                "autocalled": autocalled,
                "call_date": call_date,
                "summary": {
                    "eligible_coupon_periods": eligible_periods if coupon_rate > 0 else None,
                    "total_coupons": float(total_coupons) if coupon_rate > 0 else None,
                    "principal_return": float(principal_return) if coupon_rate > 0 else None,
                    "total_return": float(total_return) if coupon_rate > 0 else None,
                    "return_pct": float(return_pct) if coupon_rate > 0 else None
                }
            }

            json_str = json.dumps(results_dict, indent=2, default=str)
            st.download_button(
                label="📥 Download Complete Analysis",
                data=json_str,
                file_name=f"{ticker}_analysis_{dt.datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )

        except Exception as e:
            st.error(f"❌ Error fetching prices: {e}")
            import traceback
            st.code(traceback.format_exc())


def run_worst_of_analysis(params: Dict[str, Any]):
    """Run worst-of autocallable analysis for 2 assets."""
    import yfinance as yf

    ticker_a = params.get("ticker")
    ticker_b = params.get("ticker_b")
    initial_a = params.get("initial")
    initial_b = params.get("initial_b")
    dates_dict = params.get("dates", {})
    observation_dates = dates_dict.get("observation_dates", [])

    # Validation
    if not ticker_a or ticker_a == "TICKER":
        st.error("❌ Please specify a valid ticker for Stock A")
        return
    if not ticker_b or ticker_b == "TICKER":
        st.error("❌ Please specify a valid ticker for Stock B")
        return
    if not initial_a or initial_a <= 0:
        st.error("❌ Please specify a valid initial price for Stock A")
        return
    if not initial_b or initial_b <= 0:
        st.error("❌ Please specify a valid initial price for Stock B")
        return

    if not observation_dates:
        st.warning("⚠️ No observation dates found. Using key dates instead...")
        date_keys = ["pricing_date", "trade_date", "settlement_date", "maturity_date"]
        observation_dates = [dates_dict[k] for k in date_keys if k in dates_dict and dates_dict[k]]

    if not observation_dates:
        st.error("❌ No dates available for analysis")
        return

    # Convert to date objects
    date_objects = [dt.datetime.fromisoformat(d).date() for d in observation_dates]
    date_objects.sort()

    st.header("💰 Worst-Of Autocallable Analysis (2 Assets)")

    # Explain worst-of structure
    with st.expander("🧩 What is a Worst-Of Autocallable? (Click to expand)"):
        st.markdown("""
        ### How Worst-Of Autocallables Work

        A **worst-of autocallable** linked to two stocks pays coupons and determines outcomes based on the **worst performer**:

        #### 🟢 During the Life (Monthly/Quarterly Checks)

        **Coupon Payment:**
        - You receive the coupon **only if BOTH stocks are at or above the coupon barrier**
        - If either stock drops below the barrier, no coupon that period

        **Autocall (Early Redemption):**
        - The note autocalls **only if BOTH stocks are at or above the autocall level**
        - If autocalled, you get your principal back plus the coupon for that period

        #### 🔴 At Maturity (If Not Autocalled)

        The **worst performer** (the stock with the lowest % of initial) controls your final payout:

        - **If worst performer ≥ final barrier:** You get 100% of principal back
        - **If worst performer < final barrier:** You lose money proportional to the worst stock's decline

        **Example:**
        - Stock A: +5% (105% of initial)
        - Stock B: -40% (60% of initial) ← **Worst performer**
        - Final barrier: 70% of initial
        - **Result:** You lose 40% of your principal, even though Stock A performed well

        #### 💡 Why "Worst-Of"?

        You're taking on **double the risk** because both stocks must perform well for you to:
        - Receive coupons
        - Get autocalled early
        - Avoid losses at maturity

        In exchange, these notes typically offer **higher coupon rates** than single-stock autocallables.
        """)

    with st.spinner(f"Fetching prices for {ticker_a} and {ticker_b}..."):
        try:
            # Fetch prices for both stocks
            start_date = date_objects[0] - dt.timedelta(days=14)
            end_date = date_objects[-1] + dt.timedelta(days=2)

            # Fetch Stock A (cached)
            df_a = _cached_yf_download(
                ticker_a,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )

            # Fetch Stock B (cached)
            df_b = _cached_yf_download(
                ticker_b,
                start=start_date.isoformat(),
                end=end_date.isoformat(),
            )

            if df_a.empty or df_b.empty:
                st.error(f"❌ Could not fetch price data for one or both tickers")
                return

            st.success(f"✅ Fetched {len(df_a)} price records for {ticker_a} and {len(df_b)} for {ticker_b}")

            # Build observation table
            obs_data = []
            for obs_date in date_objects:
                # Find close on or before obs_date for Stock A
                prices_a_before = df_a[df_a.index.date <= obs_date]
                prices_b_before = df_b[df_b.index.date <= obs_date]

                if not prices_a_before.empty and not prices_b_before.empty:
                    price_a = float(prices_a_before['Close'].iloc[-1])
                    price_b = float(prices_b_before['Close'].iloc[-1])
                    actual_date = prices_a_before.index[-1].date()

                    # Calculate % of initial
                    pct_a = (price_a / initial_a) * 100
                    pct_b = (price_b / initial_b) * 100

                    # Worst performer
                    worst_pct = min(pct_a, pct_b)
                    worst_ticker = ticker_a if pct_a < pct_b else ticker_b

                    row = {
                        "Observation Date": obs_date.strftime("%m-%d-%Y"),
                        "Actual Date": actual_date.strftime("%m-%d-%Y"),
                        f"{ticker_a} Price": price_a,
                        f"{ticker_a} % of Initial": f"{pct_a:.2f}%",
                        f"{ticker_b} Price": price_b,
                        f"{ticker_b} % of Initial": f"{pct_b:.2f}%",
                        "Worst Performer": worst_ticker,
                        "Worst %": f"{worst_pct:.2f}%",
                    }

                    # Check barriers
                    threshold_pct = params.get("threshold_pct", 70)
                    autocall_pct = (params.get("autocall_level", initial_a) / initial_a) * 100

                    # Coupon: BOTH must be above threshold
                    both_above_threshold = (pct_a >= threshold_pct) and (pct_b >= threshold_pct)
                    row["Both Above Coupon Barrier"] = both_above_threshold

                    # Autocall: BOTH must be above autocall level
                    both_above_autocall = (pct_a >= autocall_pct) and (pct_b >= autocall_pct)
                    row["Both Above Autocall"] = both_above_autocall

                    obs_data.append(row)

            if not obs_data:
                st.error("❌ Could not match prices to observation dates")
                return

            df_obs = pd.DataFrame(obs_data)

            # Display table
            st.subheader("📊 Worst-Of Observation Schedule")
            st.dataframe(df_obs, use_container_width=True)

            # Autocall analysis
            st.subheader("🔔 Autocall Analysis")

            autocalled = False
            call_date = None

            for idx, row in df_obs.iterrows():
                if idx > 0 and row.get("Both Above Autocall"):
                    autocalled = True
                    call_date = row["Observation Date"]
                    break

            threshold_pct = params.get("threshold_pct", 70)
            coupon_rate = params.get("coupon_rate", 0)
            notional = params.get("notional", 1000)
            payments_per_year = params.get("payments_per_year", 4)

            if autocalled:
                st.success(f"✅ **AUTOCALLED** on {call_date}")
                st.write("Both stocks were above the autocall level. Product called early.")
                st.write("Investor receives: Principal + accrued coupons")
            else:
                st.info("ℹ️ **Not Autocalled** - Product runs to maturity")

                final_row = obs_data[-1]
                final_worst_pct = float(final_row["Worst %"].rstrip('%'))
                worst_ticker = final_row["Worst Performer"]

                st.write(f"**Worst Performer at Maturity:** {worst_ticker} at {final_worst_pct:.2f}% of initial")

                if final_worst_pct >= threshold_pct:
                    st.success(f"✅ Worst performer ({final_worst_pct:.2f}%) ≥ Final Barrier ({threshold_pct:.2f}%)")
                    st.write("**Outcome:** Investor receives 100% of principal plus all coupons earned")
                else:
                    st.error(f"❌ Worst performer ({final_worst_pct:.2f}%) < Final Barrier ({threshold_pct:.2f}%)")

                    # Calculate loss based on worst performer
                    loss_pct = final_worst_pct - 100  # Negative number

                    st.subheader("⚠️ Principal Loss (Based on Worst Performer)")
                    principal_loss_dollars = notional * (loss_pct / 100)
                    principal_returned = notional + principal_loss_dollars

                    col1, col2, col3 = st.columns(3)
                    col1.metric(
                        "Worst Performer Return",
                        f"{loss_pct:.2f}%",
                        delta=f"{loss_pct:.2f}%",
                        delta_color="inverse"
                    )
                    col2.metric(
                        "Principal Loss $",
                        f"${abs(principal_loss_dollars):.2f}",
                        delta=f"-${abs(principal_loss_dollars):.2f}",
                        delta_color="inverse"
                    )
                    col3.metric(
                        "Principal Returned",
                        f"${principal_returned:.2f}",
                        delta=f"${principal_loss_dollars:.2f}",
                        delta_color="inverse"
                    )

            # Coupon summary
            st.subheader("💵 Contingent Payment Summary")

            if coupon_rate > 0:
                coupon_per_period = notional * coupon_rate

                eligible_periods = 0
                for idx, row in df_obs.iterrows():
                    if autocalled and idx > df_obs[df_obs["Observation Date"] == call_date].index[0]:
                        break
                    if row.get("Both Above Coupon Barrier"):
                        eligible_periods += 1

                total_coupons = eligible_periods * coupon_per_period

                col1, col2, col3 = st.columns(3)
                col1.metric("Contingent Payment per Period", f"${coupon_per_period:.2f}")
                col2.metric("Eligible Periods (Both Above Barrier)", eligible_periods)
                col3.metric("Total Payments", f"${total_coupons:.2f}")

                # Total return
                st.subheader("📊 Total Return (Principal + Contingent Payments)")

                if autocalled:
                    principal_return = notional
                    total_return = principal_return + total_coupons
                    return_pct = ((total_return - notional) / notional) * 100

                    col1, col2, col3 = st.columns(3)
                    col1.metric("Principal Returned", f"${principal_return:.2f}")
                    col2.metric("Total Return", f"${total_return:.2f}")
                    col3.metric("Return %", f"{return_pct:.2f}%")
                else:
                    final_worst_pct = float(obs_data[-1]["Worst %"].rstrip('%'))

                    if final_worst_pct >= threshold_pct:
                        principal_return = notional
                    else:
                        # Loss based on worst performer
                        loss_pct = final_worst_pct - 100
                        principal_return = notional * (1 + loss_pct / 100)

                    total_return = principal_return + total_coupons
                    return_pct = ((total_return - notional) / notional) * 100

                    col1, col2, col3 = st.columns(3)
                    col1.metric("Principal Returned", f"${principal_return:.2f}",
                              delta=f"{principal_return - notional:.2f}" if principal_return != notional else None,
                              delta_color="inverse" if principal_return < notional else "normal")
                    col2.metric("Total Return", f"${total_return:.2f}")
                    col3.metric("Return %", f"{return_pct:.2f}%",
                              delta_color="inverse" if return_pct < 0 else "normal")

                    # Add explanation if there's downside
                    if principal_return < notional:
                        payment_offset = total_coupons
                        st.info(
                            f"💡 **Explanation:** The worst performer ({worst_ticker}) declined {abs(loss_pct):.2f}%, "
                            f"causing a principal loss of ${abs(principal_return - notional):.2f}. "
                            f"The contingent payments (${total_coupons:.2f}) partially offset this loss. "
                            f"Net return: {return_pct:.2f}%"
                        )

            # Download results
            st.subheader("💾 Download Results")

            results_dict = {
                "product_type": "worst_of_2_assets",
                "ticker_a": ticker_a,
                "ticker_b": ticker_b,
                "initial_a": initial_a,
                "initial_b": initial_b,
                "parameters": params,
                "observation_schedule": df_obs.to_dict(orient="records"),
                "autocalled": autocalled,
                "call_date": call_date,
                "summary": {
                    "worst_performer": worst_ticker if not autocalled else None,
                    "worst_pct": final_worst_pct if not autocalled else None,
                    "eligible_coupon_periods": eligible_periods if coupon_rate > 0 else None,
                    "total_coupons": float(total_coupons) if coupon_rate > 0 else None,
                    "principal_return": float(principal_return) if coupon_rate > 0 else None,
                    "total_return": float(total_return) if coupon_rate > 0 else None,
                    "return_pct": float(return_pct) if coupon_rate > 0 else None
                }
            }

            json_str = json.dumps(results_dict, indent=2, default=str)
            st.download_button(
                label="📥 Download Worst-Of Analysis",
                data=json_str,
                file_name=f"worst_of_{ticker_a}_{ticker_b}_analysis_{dt.datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json"
            )

        except Exception as e:
            st.error(f"❌ Error during worst-of analysis: {e}")
            import traceback
            st.code(traceback.format_exc())


if __name__ == "__main__":
    main()
