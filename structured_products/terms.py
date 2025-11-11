"""
Product terms extraction module for structured products.

Extracts key financial terms such as barriers, caps, participation rates,
knock-in/knock-out levels, autocall triggers, and coupon rates.
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


# Product term keywords and patterns
PRODUCT_TERM_PATTERNS = {
    "participation_rate": [
        r"participation\s+(?:rate\s+)?(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+participation",
        r"participates?\s+at\s+(\d+(?:\.\d+)?)\s*%",
    ],
    "cap": [
        r"(?:capped\s+at|cap\s+of|maximum\s+return\s+of|cap\s+level\s+of)\s+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+cap",
        r"cap:\s*(\d+(?:\.\d+)?)\s*%",
    ],
    "floor": [
        r"(?:floor\s+of|minimum\s+return\s+of|floor\s+at)\s+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+floor",
        r"floor:\s*(\d+(?:\.\d+)?)\s*%",
    ],
    "barrier": [
        r"(?:barrier\s+(?:at|of|level)?|protection\s+(?:at|of|level)?)\s+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+barrier",
        r"barrier:\s*(\d+(?:\.\d+)?)\s*%",
    ],
    "knock_in": [
        r"knock[- ]?in\s+(?:barrier\s+)?(?:at\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+knock[- ]?in",
    ],
    "knock_out": [
        r"knock[- ]?out\s+(?:barrier\s+)?(?:at\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+knock[- ]?out",
    ],
    "autocall": [
        r"autocall\s+(?:trigger\s+)?(?:at\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(?:early\s+redemption|callable)\s+at\s+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+autocall",
    ],
    "coupon": [
        r"(?:coupon\s+(?:rate\s+)?(?:of\s+)?|pays\s+|payment\s+of\s+)(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+(?:per\s+)?(?:annum|annual|coupon)",
    ],
    "gearing": [
        r"gearing\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+gearing",
        r"gearing:\s*(\d+(?:\.\d+)?)\s*%",
    ],
    "leverage": [
        r"leverage\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*x",
        r"(\d+(?:\.\d+)?)\s*x\s+leverage",
    ],
    "buffer": [
        r"buffer\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+buffer",
        r"downside\s+protection\s+of\s+(\d+(?:\.\d+)?)\s*%",
    ],
}


def extract_product_terms(content: str, is_html: bool = False) -> Dict[str, any]:
    """
    Extract structured product terms from filing content.

    Args:
        content: The filing content (HTML or plain text)
        is_html: Whether the content is HTML format

    Returns:
        Dictionary containing extracted product terms with values
    """
    from .parser import extract_text_from_html

    logger.info("Extracting product terms from content")

    if is_html:
        text = extract_text_from_html(content)
    else:
        text = content

    terms = {}

    # Extract each term type
    for term_type, patterns in PRODUCT_TERM_PATTERNS.items():
        value = extract_term_value(text, patterns, term_type)
        if value is not None:
            terms[term_type] = value
            logger.debug(f"Found {term_type}: {value}")

    # Extract additional structured information
    terms.update(extract_protection_level(text))
    terms.update(extract_maturity_terms(text))
    terms.update(extract_observation_frequency(text))

    logger.info(f"Product term extraction complete: found {len(terms)} terms")
    return terms


def extract_term_value(
    text: str,
    patterns: List[str],
    term_name: str
) -> Optional[Dict[str, any]]:
    """
    Extract a specific term value using regex patterns.

    Args:
        text: Text to search
        patterns: List of regex patterns to try
        term_name: Name of the term being extracted

    Returns:
        Dictionary with value and metadata, or None if not found
    """
    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                value_str = match.group(1)
                value = float(value_str)

                # Validate reasonable ranges
                if not is_reasonable_value(term_name, value):
                    logger.warning(
                        f"Extracted {term_name} value {value} seems unreasonable, skipping"
                    )
                    continue

                return {
                    "value": value,
                    "unit": "%" if "leverage" not in term_name else "x",
                    "raw_text": match.group(0),
                    "confidence": "high" if pattern == patterns[0] else "medium"
                }
            except (ValueError, IndexError) as e:
                logger.debug(f"Failed to parse {term_name} from '{match.group(0)}': {e}")
                continue

    return None


def is_reasonable_value(term_name: str, value: float) -> bool:
    """
    Check if extracted value is within reasonable range for the term type.

    Args:
        term_name: Name of the term
        value: Extracted numeric value

    Returns:
        True if value is reasonable, False otherwise
    """
    # Define reasonable ranges for each term
    ranges = {
        "participation_rate": (0, 500),    # 0-500%
        "cap": (0, 500),                   # 0-500%
        "floor": (-100, 100),              # -100% to 100%
        "barrier": (0, 100),               # 0-100%
        "knock_in": (0, 100),              # 0-100%
        "knock_out": (100, 500),           # 100-500%
        "autocall": (100, 200),            # 100-200%
        "coupon": (0, 50),                 # 0-50%
        "gearing": (0, 500),               # 0-500%
        "leverage": (0, 20),               # 0-20x
        "buffer": (0, 100),                # 0-100%
    }

    if term_name in ranges:
        min_val, max_val = ranges[term_name]
        return min_val <= value <= max_val

    # If no range defined, accept any positive value
    return value >= 0


def extract_protection_level(text: str) -> Dict[str, any]:
    """
    Extract principal protection information.

    Args:
        text: Text to search

    Returns:
        Dictionary with protection information
    """
    result = {}

    # Principal protection patterns
    protection_patterns = [
        r"(\d+(?:\.\d+)?)\s*%\s+principal\s+protection",
        r"principal\s+protection\s+of\s+(\d+(?:\.\d+)?)\s*%",
        r"(\d+(?:\.\d+)?)\s*%\s+protected",
        r"capital\s+protection\s+of\s+(\d+(?:\.\d+)?)\s*%",
    ]

    for pattern in protection_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                value = float(match.group(1))
                if 0 <= value <= 100:
                    result["principal_protection"] = {
                        "value": value,
                        "unit": "%",
                        "raw_text": match.group(0)
                    }
                    logger.debug(f"Found principal protection: {value}%")
                    break
            except ValueError:
                continue

    # Check for conditional protection
    conditional_patterns = [
        r"conditional\s+protection",
        r"contingent\s+protection",
        r"protection\s+(?:is\s+)?contingent\s+(?:on|upon)",
    ]

    for pattern in conditional_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            result["protection_type"] = "conditional"
            logger.debug("Found conditional protection")
            break
    else:
        if "principal_protection" in result:
            result["protection_type"] = "unconditional"

    return result


def extract_maturity_terms(text: str) -> Dict[str, any]:
    """
    Extract maturity-related terms.

    Args:
        text: Text to search

    Returns:
        Dictionary with maturity terms
    """
    result = {}

    # Extract term length
    term_patterns = [
        r"(\d+)[- ]year\s+term",
        r"term\s+of\s+(\d+)\s+years?",
        r"(\d+)[- ]month\s+term",
        r"term\s+of\s+(\d+)\s+months?",
    ]

    for pattern in term_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = int(match.group(1))
            unit = "years" if "year" in pattern else "months"
            result["term_length"] = {
                "value": value,
                "unit": unit,
                "raw_text": match.group(0)
            }
            logger.debug(f"Found term length: {value} {unit}")
            break

    # Check for autocallable feature
    autocall_patterns = [
        r"autocallable",
        r"auto[- ]?callable",
        r"early\s+redemption",
        r"callable",
    ]

    for pattern in autocall_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            result["is_autocallable"] = True
            logger.debug("Product is autocallable")
            break

    return result


def extract_observation_frequency(text: str) -> Dict[str, any]:
    """
    Extract observation frequency for barrier/autocall checks.

    Args:
        text: Text to search

    Returns:
        Dictionary with observation information
    """
    result = {}

    # Observation frequency patterns
    frequency_patterns = {
        "daily": r"daily\s+observation",
        "weekly": r"weekly\s+observation",
        "monthly": r"monthly\s+observation",
        "quarterly": r"quarterly\s+observation",
        "annual": r"annual(?:ly)?\s+observation",
        "at_maturity": r"observation\s+at\s+maturity",
        "european": r"european\s+(?:style|barrier)",
    }

    for freq, pattern in frequency_patterns.items():
        if re.search(pattern, text, re.IGNORECASE):
            result["observation_frequency"] = freq
            logger.debug(f"Found observation frequency: {freq}")
            break

    # Check for continuous observation
    if re.search(r"continuous(?:ly)?\s+observed", text, re.IGNORECASE):
        result["observation_frequency"] = "continuous"
        logger.debug("Found continuous observation")

    return result


def extract_basket_information(text: str) -> Dict[str, any]:
    """
    Extract information about basket structures (worst-of, best-of, etc.).

    Args:
        text: Text to search

    Returns:
        Dictionary with basket information
    """
    result = {}

    # Basket type patterns
    basket_patterns = {
        "worst_of": [
            r"worst[- ]of",
            r"worst\s+performing",
            r"lowest\s+performing",
        ],
        "best_of": [
            r"best[- ]of",
            r"best\s+performing",
            r"highest\s+performing",
        ],
        "average": [
            r"average\s+performance",
            r"equally[- ]weighted",
            r"basket\s+average",
        ],
    }

    for basket_type, patterns in basket_patterns.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                result["basket_type"] = basket_type
                logger.debug(f"Found basket type: {basket_type}")
                return result

    # Check for number of underlyings
    num_underlying_patterns = [
        r"basket\s+of\s+(\d+)\s+(?:stocks|indices|underlyings)",
        r"(\d+)\s+underlyings?",
        r"linked\s+to\s+(\d+)\s+(?:stocks|indices)",
    ]

    for pattern in num_underlying_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                num = int(match.group(1))
                if 2 <= num <= 100:  # Reasonable range
                    result["num_underlyings"] = num
                    logger.debug(f"Found {num} underlyings in basket")
                    break
            except ValueError:
                continue

    return result


def calculate_payoff_type(terms: Dict[str, any]) -> str:
    """
    Infer the payoff type based on extracted terms.

    Args:
        terms: Dictionary of extracted product terms

    Returns:
        String describing the likely payoff type
    """
    has_cap = "cap" in terms
    has_floor = "floor" in terms
    has_barrier = "barrier" in terms
    has_participation = "participation_rate" in terms
    has_autocall = "autocall" in terms or terms.get("is_autocallable", False)
    has_coupon = "coupon" in terms
    has_buffer = "buffer" in terms

    # Determine payoff type
    if has_autocall and has_coupon:
        return "autocallable_coupon"
    elif has_autocall:
        return "autocallable"
    elif has_buffer and has_participation:
        return "buffered_participation"
    elif has_barrier and has_participation:
        return "barrier_participation"
    elif has_cap and has_floor:
        return "range_accrual"
    elif has_cap and has_participation:
        return "capped_participation"
    elif has_coupon and has_barrier:
        return "reverse_convertible"
    elif has_participation and not has_cap:
        return "leveraged_participation"
    elif terms.get("principal_protection", {}).get("value", 0) == 100:
        return "principal_protected"
    else:
        return "unknown"


def summarize_product_terms(terms: Dict[str, any]) -> Dict[str, any]:
    """
    Create a summary of the extracted product terms.

    Args:
        terms: Dictionary of extracted product terms

    Returns:
        Dictionary with summary information
    """
    summary = {
        "payoff_type": calculate_payoff_type(terms),
        "has_downside_protection": (
            "barrier" in terms or
            "buffer" in terms or
            terms.get("principal_protection", {}).get("value", 0) > 0
        ),
        "has_upside_cap": "cap" in terms,
        "has_leverage": (
            "participation_rate" in terms and
            terms.get("participation_rate", {}).get("value", 100) > 100
        ) or "gearing" in terms or "leverage" in terms,
        "is_path_dependent": (
            "knock_in" in terms or
            "knock_out" in terms or
            terms.get("observation_frequency") not in [None, "at_maturity", "european"]
        ),
        "terms_extracted": len(terms),
        "confidence": "high" if len(terms) >= 3 else "medium" if len(terms) >= 1 else "low",
    }

    logger.info(f"Product summary: {summary['payoff_type']}, {summary['terms_extracted']} terms")
    return summary
