"""
Data validation for structured products.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationWarning:
    """Represents a validation warning or error."""

    severity: str  # 'error', 'warning', 'info'
    message: str
    field: Optional[str] = None

    def __str__(self):
        field_str = f" [{self.field}]" if self.field else ""
        return f"[{self.severity.upper()}]{field_str} {self.message}"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "severity": self.severity,
            "message": self.message,
            "field": self.field
        }


def validate_dates(dates: Dict[str, str]) -> List[ValidationWarning]:
    """
    Validate date chronology and business logic.

    Checks:
    - Date format validity
    - Chronological order (pricing < maturity, etc.)
    - Reasonable time periods
    - Business day conventions

    Args:
        dates: Dictionary mapping date types to ISO-formatted date strings

    Returns:
        List of validation warnings
    """
    warnings = []

    if not dates:
        warnings.append(
            ValidationWarning("warning", "No dates extracted from filing")
        )
        return warnings

    try:
        # Parse all dates
        parsed_dates = {}
        for key, date_str in dates.items():
            try:
                parsed_dates[key] = datetime.strptime(date_str, "%Y-%m-%d")
            except ValueError as e:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Invalid date format: {date_str} ({e})",
                        key
                    )
                )

        if not parsed_dates:
            return warnings

        # Check chronological order: pricing < maturity
        if "pricing_date" in parsed_dates and "maturity_date" in parsed_dates:
            if parsed_dates["maturity_date"] <= parsed_dates["pricing_date"]:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Maturity date ({dates['maturity_date']}) must be after "
                        f"pricing date ({dates['pricing_date']})",
                        "maturity_date"
                    )
                )

        # Check trade date vs settlement date
        if "trade_date" in parsed_dates and "settlement_date" in parsed_dates:
            if parsed_dates["settlement_date"] < parsed_dates["trade_date"]:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Settlement date ({dates['settlement_date']}) cannot be before "
                        f"trade date ({dates['trade_date']})",
                        "settlement_date"
                    )
                )

        # Check pricing date vs trade date (usually same or trade is T+1)
        if "pricing_date" in parsed_dates and "trade_date" in parsed_dates:
            days_diff = (parsed_dates["trade_date"] - parsed_dates["pricing_date"]).days
            if days_diff < 0:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Trade date ({dates['trade_date']}) cannot be before "
                        f"pricing date ({dates['pricing_date']})",
                        "trade_date"
                    )
                )
            elif days_diff > 5:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Trade date is {days_diff} days after pricing date. "
                        f"This is unusual (typically T+0 or T+1)",
                        "trade_date"
                    )
                )

        # Check issue date vs settlement date (typically same)
        if "issue_date" in parsed_dates and "settlement_date" in parsed_dates:
            days_diff = abs((parsed_dates["issue_date"] - parsed_dates["settlement_date"]).days)
            if days_diff > 2:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Issue date and settlement date differ by {days_diff} days. "
                        f"They are typically the same or 1-2 days apart",
                        "issue_date"
                    )
                )

        # Check valuation dates
        if "initial_valuation_date" in parsed_dates and "final_valuation_date" in parsed_dates:
            if parsed_dates["final_valuation_date"] <= parsed_dates["initial_valuation_date"]:
                warnings.append(
                    ValidationWarning(
                        "error",
                        f"Final valuation date ({dates['final_valuation_date']}) must be after "
                        f"initial valuation date ({dates['initial_valuation_date']})",
                        "final_valuation_date"
                    )
                )

        # Check initial valuation vs pricing
        if "pricing_date" in parsed_dates and "initial_valuation_date" in parsed_dates:
            if parsed_dates["initial_valuation_date"] != parsed_dates["pricing_date"]:
                days_diff = abs((parsed_dates["initial_valuation_date"] - parsed_dates["pricing_date"]).days)
                if days_diff > 3:
                    warnings.append(
                        ValidationWarning(
                            "warning",
                            f"Initial valuation date differs from pricing date by {days_diff} days. "
                            f"They are typically the same",
                            "initial_valuation_date"
                        )
                    )

        # Check maturity is reasonable (not too short or too long)
        if "pricing_date" in parsed_dates and "maturity_date" in parsed_dates:
            days_to_maturity = (parsed_dates["maturity_date"] - parsed_dates["pricing_date"]).days
            years_to_maturity = days_to_maturity / 365.25

            if days_to_maturity < 30:  # Less than 1 month
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Very short maturity: {days_to_maturity} days ({years_to_maturity:.2f} years). "
                        f"Verify this is not an error.",
                        "maturity_date"
                    )
                )
            elif years_to_maturity > 30:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"Very long maturity: {years_to_maturity:.1f} years. "
                        f"Verify this is not an error.",
                        "maturity_date"
                    )
                )
            else:
                logger.info(f"Maturity period: {years_to_maturity:.2f} years")

        # Check dates aren't in the distant past or future
        now = datetime.now()
        for key, date_obj in parsed_dates.items():
            years_ago = (now - date_obj).days / 365.25

            if years_ago > 20:
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"{key.replace('_', ' ').title()} is {years_ago:.1f} years in the past. "
                        f"Verify this is correct.",
                        key
                    )
                )
            elif years_ago < -10:  # More than 10 years in future
                warnings.append(
                    ValidationWarning(
                        "warning",
                        f"{key.replace('_', ' ').title()} is {abs(years_ago):.1f} years in the future. "
                        f"Verify this is correct.",
                        key
                    )
                )

    except Exception as e:
        logger.error(f"Error during date validation: {e}", exc_info=True)
        warnings.append(
            ValidationWarning("error", f"Validation error: {e}")
        )

    return warnings


def validate_symbols(symbols: List[str]) -> List[ValidationWarning]:
    """
    Validate extracted symbols.

    Checks:
    - Symbol format
    - Symbol length
    - Common errors

    Args:
        symbols: List of extracted symbols

    Returns:
        List of validation warnings
    """
    warnings = []

    if not symbols:
        warnings.append(
            ValidationWarning(
                "warning",
                "No symbols detected in filing. This may indicate parsing issues."
            )
        )
        return warnings

    logger.info(f"Validating {len(symbols)} symbols")

    # Check for common errors
    for symbol in symbols:
        # Check length
        if len(symbol) < 1:
            warnings.append(
                ValidationWarning(
                    "error",
                    f"Empty symbol detected",
                    "symbols"
                )
            )
        elif len(symbol) == 1:
            warnings.append(
                ValidationWarning(
                    "warning",
                    f"Symbol '{symbol}' is unusually short (1 character)",
                    "symbols"
                )
            )
        elif len(symbol) > 6 and not symbol.startswith("^"):
            warnings.append(
                ValidationWarning(
                    "warning",
                    f"Symbol '{symbol}' is unusually long ({len(symbol)} characters)",
                    "symbols"
                )
            )

        # Check for invalid characters
        if not symbol.replace("^", "").replace("-", "").replace(".", "").isalnum():
            warnings.append(
                ValidationWarning(
                    "warning",
                    f"Symbol '{symbol}' contains unusual characters",
                    "symbols"
                )
            )

    logger.info(f"Symbol validation complete: {len(warnings)} warnings")
    return warnings


def validate_extraction_results(
    symbols: Dict[str, any],
    dates: Dict[str, str]
) -> Dict[str, any]:
    """
    Comprehensive validation of all extraction results.

    Args:
        symbols: Dictionary containing indices, yahoo_symbols, raw_tickers
        dates: Dictionary of extracted dates

    Returns:
        Dictionary with validation results and metadata
    """
    date_warnings = validate_dates(dates)
    symbol_warnings = validate_symbols(symbols.get("yahoo_symbols", []))

    all_warnings = date_warnings + symbol_warnings

    # Calculate confidence score
    error_count = sum(1 for w in all_warnings if w.severity == "error")
    warning_count = sum(1 for w in all_warnings if w.severity == "warning")

    # Simple scoring: start at 1.0, deduct for issues
    confidence = 1.0
    confidence -= error_count * 0.3  # Errors are serious
    confidence -= warning_count * 0.1  # Warnings are less serious
    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]

    has_errors = error_count > 0
    has_warnings = warning_count > 0

    validation_result = {
        "date_warnings": [w.to_dict() for w in date_warnings],
        "symbol_warnings": [w.to_dict() for w in symbol_warnings],
        "has_errors": has_errors,
        "has_warnings": has_warnings,
        "error_count": error_count,
        "warning_count": warning_count,
        "confidence_score": round(confidence, 2),
        "is_valid": not has_errors,  # Valid if no errors (warnings OK)
    }

    # Log summary
    if has_errors:
        logger.error(f"Validation failed: {error_count} errors, {warning_count} warnings")
    elif has_warnings:
        logger.warning(f"Validation passed with warnings: {warning_count} warnings")
    else:
        logger.info("Validation passed with no issues")

    return validation_result
