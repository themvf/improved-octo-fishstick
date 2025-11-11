"""
Security identifier extraction and validation.

Extracts CUSIP, ISIN, and other security identifiers from filings.
"""

import logging
import re
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


def extract_cusip(text: str) -> Optional[str]:
    """
    Extract CUSIP from text.

    CUSIP format: 9 characters (alphanumeric)
    - First 6: Issuer
    - Next 2: Issue
    - Last 1: Check digit

    Args:
        text: Text to search

    Returns:
        CUSIP string or None if not found
    """
    # CUSIP pattern: 9 alphanumeric characters
    # Often labeled as "CUSIP:", "CUSIP No:", etc.
    patterns = [
        r'CUSIP\s*(?:No\.?|Number)?:?\s*([A-Z0-9]{9})\b',
        r'CUSIP\s+([A-Z0-9]{9})\b',
        r'\bCUSIP:\s*([A-Z0-9]{9})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            cusip = match.group(1).upper()
            if validate_cusip(cusip):
                logger.debug(f"Found CUSIP: {cusip}")
                return cusip

    # Try finding any 9-character alphanumeric sequence near "CUSIP"
    cusip_context = re.search(
        r'CUSIP.{0,50}?([A-Z0-9]{9})\b',
        text,
        re.IGNORECASE
    )
    if cusip_context:
        cusip = cusip_context.group(1).upper()
        if validate_cusip(cusip):
            logger.debug(f"Found CUSIP in context: {cusip}")
            return cusip

    return None


def validate_cusip(cusip: str) -> bool:
    """
    Validate CUSIP format and check digit.

    Args:
        cusip: CUSIP string to validate

    Returns:
        True if valid CUSIP
    """
    if len(cusip) != 9:
        return False

    if not cusip.isalnum():
        return False

    # Check digit validation (Luhn algorithm with modifications)
    try:
        # Convert letters to numbers (A=10, B=11, ..., Z=35)
        values = []
        for char in cusip[:-1]:  # Exclude check digit
            if char.isdigit():
                values.append(int(char))
            else:
                # A=10, B=11, etc.
                values.append(ord(char) - ord('A') + 10)

        # Double every second digit
        total = 0
        for i, val in enumerate(values):
            if i % 2 == 1:
                val *= 2
            # Add digits of the value
            total += val // 10 + val % 10

        # Check digit should make total divisible by 10
        check_digit = (10 - (total % 10)) % 10
        return str(check_digit) == cusip[-1]

    except Exception as e:
        logger.debug(f"CUSIP validation error: {e}")
        return False


def extract_isin(text: str) -> Optional[str]:
    """
    Extract ISIN from text.

    ISIN format: 12 characters
    - First 2: Country code (letters)
    - Next 9: National identifier
    - Last 1: Check digit

    Args:
        text: Text to search

    Returns:
        ISIN string or None if not found
    """
    # ISIN pattern: 2 letters + 10 alphanumeric
    patterns = [
        r'ISIN\s*(?:No\.?|Number)?:?\s*([A-Z]{2}[A-Z0-9]{10})\b',
        r'ISIN\s+([A-Z]{2}[A-Z0-9]{10})\b',
        r'\bISIN:\s*([A-Z]{2}[A-Z0-9]{10})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            isin = match.group(1).upper()
            if validate_isin(isin):
                logger.debug(f"Found ISIN: {isin}")
                return isin

    # Try finding any valid ISIN near "ISIN" keyword
    isin_context = re.search(
        r'ISIN.{0,50}?([A-Z]{2}[A-Z0-9]{10})\b',
        text,
        re.IGNORECASE
    )
    if isin_context:
        isin = isin_context.group(1).upper()
        if validate_isin(isin):
            logger.debug(f"Found ISIN in context: {isin}")
            return isin

    return None


def validate_isin(isin: str) -> bool:
    """
    Validate ISIN format and check digit.

    Args:
        isin: ISIN string to validate

    Returns:
        True if valid ISIN
    """
    if len(isin) != 12:
        return False

    # First 2 characters must be letters (country code)
    if not isin[:2].isalpha():
        return False

    # Rest must be alphanumeric
    if not isin[2:].isalnum():
        return False

    # Validate check digit (Luhn algorithm)
    try:
        # Convert to numeric string (A=10, B=11, ..., Z=35)
        numeric = ""
        for char in isin[:-1]:  # Exclude check digit
            if char.isdigit():
                numeric += char
            else:
                numeric += str(ord(char) - ord('A') + 10)

        # Apply Luhn algorithm
        total = 0
        for i, digit in enumerate(reversed(numeric)):
            n = int(digit)
            if i % 2 == 0:
                n *= 2
                if n > 9:
                    n -= 9
            total += n

        # Check digit should make total divisible by 10
        check_digit = (10 - (total % 10)) % 10
        return str(check_digit) == isin[-1]

    except Exception as e:
        logger.debug(f"ISIN validation error: {e}")
        return False


def extract_sedol(text: str) -> Optional[str]:
    """
    Extract SEDOL from text.

    SEDOL format: 7 characters (alphanumeric, no vowels except in check digit)

    Args:
        text: Text to search

    Returns:
        SEDOL string or None if not found
    """
    patterns = [
        r'SEDOL\s*(?:No\.?|Number)?:?\s*([A-Z0-9]{7})\b',
        r'SEDOL\s+([A-Z0-9]{7})\b',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            sedol = match.group(1).upper()
            logger.debug(f"Found SEDOL: {sedol}")
            return sedol

    return None


def extract_all_identifiers(content: str, is_html: bool = False) -> Dict[str, Optional[str]]:
    """
    Extract all security identifiers from content.

    Args:
        content: Filing content (HTML or plain text)
        is_html: Whether content is HTML format

    Returns:
        Dictionary with extracted identifiers
    """
    from .parser import extract_text_from_html

    logger.info("Extracting security identifiers")

    if is_html:
        text = extract_text_from_html(content)
    else:
        text = content

    identifiers = {}

    # Extract CUSIP
    cusip = extract_cusip(text)
    if cusip:
        identifiers["cusip"] = cusip
        logger.info(f"Found CUSIP: {cusip}")

    # Extract ISIN
    isin = extract_isin(text)
    if isin:
        identifiers["isin"] = isin
        logger.info(f"Found ISIN: {isin}")

        # Extract country from ISIN
        if isin:
            country_code = isin[:2]
            identifiers["country_code"] = country_code

    # Extract SEDOL
    sedol = extract_sedol(text)
    if sedol:
        identifiers["sedol"] = sedol
        logger.info(f"Found SEDOL: {sedol}")

    if not identifiers:
        logger.warning("No security identifiers found in content")

    return identifiers


def cusip_to_isin(cusip: str, country_code: str = "US") -> Optional[str]:
    """
    Convert CUSIP to ISIN.

    Args:
        cusip: 9-character CUSIP
        country_code: 2-letter country code (default: US)

    Returns:
        12-character ISIN or None if invalid
    """
    if not validate_cusip(cusip):
        logger.error(f"Invalid CUSIP: {cusip}")
        return None

    # ISIN = Country Code + CUSIP + Check Digit
    base = country_code.upper() + cusip

    # Calculate check digit
    numeric = ""
    for char in base:
        if char.isdigit():
            numeric += char
        else:
            numeric += str(ord(char) - ord('A') + 10)

    # Luhn algorithm
    total = 0
    for i, digit in enumerate(reversed(numeric)):
        n = int(digit)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n

    check_digit = (10 - (total % 10)) % 10
    isin = base + str(check_digit)

    logger.debug(f"Converted CUSIP {cusip} to ISIN {isin}")
    return isin


def format_identifier(identifier: str, identifier_type: str) -> str:
    """
    Format identifier for display.

    Args:
        identifier: Raw identifier
        identifier_type: Type (cusip, isin, sedol)

    Returns:
        Formatted identifier
    """
    identifier = identifier.upper().strip()

    if identifier_type.lower() == "cusip":
        # Format: XXX XXX XXX
        if len(identifier) == 9:
            return f"{identifier[:3]} {identifier[3:6]} {identifier[6:]}"

    elif identifier_type.lower() == "isin":
        # Format: XX XXXX XXXX XX
        if len(identifier) == 12:
            return f"{identifier[:2]} {identifier[2:6]} {identifier[6:10]} {identifier[10:]}"

    return identifier
