"""
Unit tests for validation module.
"""

import unittest
from structured_products.validation import (
    validate_dates,
    validate_symbols,
    validate_extraction_results,
    ValidationWarning
)


class TestDateValidation(unittest.TestCase):
    """Test date validation functionality."""

    def test_valid_dates(self):
        """Test validation of valid dates."""
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2027-01-15"
        }
        warnings = validate_dates(dates)

        # Should have no errors
        errors = [w for w in warnings if w.severity == "error"]
        self.assertEqual(len(errors), 0)

    def test_maturity_before_pricing(self):
        """Test that maturity before pricing is caught."""
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2020-01-15"  # Before pricing!
        }
        warnings = validate_dates(dates)

        # Should have error
        errors = [w for w in warnings if w.severity == "error"]
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("maturity" in w.message.lower() for w in errors))

    def test_settlement_before_trade(self):
        """Test that settlement before trade is caught."""
        dates = {
            "trade_date": "2024-01-18",
            "settlement_date": "2024-01-15"  # Before trade!
        }
        warnings = validate_dates(dates)

        errors = [w for w in warnings if w.severity == "error"]
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("settlement" in w.message.lower() for w in errors))

    def test_final_valuation_before_initial(self):
        """Test that final valuation before initial is caught."""
        dates = {
            "initial_valuation_date": "2024-01-15",
            "final_valuation_date": "2024-01-10"  # Before initial!
        }
        warnings = validate_dates(dates)

        errors = [w for w in warnings if w.severity == "error"]
        self.assertGreater(len(errors), 0)

    def test_very_short_maturity_warning(self):
        """Test warning for very short maturity."""
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2024-01-20"  # Only 5 days!
        }
        warnings = validate_dates(dates)

        # Should have warning (not error)
        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)
        self.assertTrue(any("short" in w.message.lower() for w in warning_msgs))

    def test_very_long_maturity_warning(self):
        """Test warning for very long maturity."""
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2055-01-15"  # 31 years!
        }
        warnings = validate_dates(dates)

        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)
        self.assertTrue(any("long" in w.message.lower() for w in warning_msgs))

    def test_trade_after_pricing_warning(self):
        """Test warning when trade is many days after pricing."""
        dates = {
            "pricing_date": "2024-01-15",
            "trade_date": "2024-01-25"  # 10 days later
        }
        warnings = validate_dates(dates)

        # Should have warning
        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)

    def test_invalid_date_format(self):
        """Test handling of invalid date format."""
        dates = {
            "pricing_date": "not-a-date",
            "maturity_date": "2027-01-15"
        }
        warnings = validate_dates(dates)

        errors = [w for w in warnings if w.severity == "error"]
        self.assertGreater(len(errors), 0)
        self.assertTrue(any("invalid date format" in w.message.lower() for w in errors))

    def test_empty_dates(self):
        """Test validation of empty dates."""
        warnings = validate_dates({})

        # Should have warning about no dates
        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)


class TestSymbolValidation(unittest.TestCase):
    """Test symbol validation functionality."""

    def test_valid_symbols(self):
        """Test validation of valid symbols."""
        symbols = ["^GSPC", "^RUT", "AAPL", "MSFT"]
        warnings = validate_symbols(symbols)

        # Should have no errors
        errors = [w for w in warnings if w.severity == "error"]
        self.assertEqual(len(errors), 0)

    def test_empty_symbols(self):
        """Test validation of empty symbol list."""
        warnings = validate_symbols([])

        # Should have warning
        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)

    def test_short_symbol_warning(self):
        """Test warning for very short symbol."""
        symbols = ["A"]  # 1 character
        warnings = validate_symbols(symbols)

        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)
        self.assertTrue(any("short" in w.message.lower() for w in warning_msgs))

    def test_long_symbol_warning(self):
        """Test warning for very long symbol."""
        symbols = ["VERYLONGSYMBOL"]  # Very long
        warnings = validate_symbols(symbols)

        warning_msgs = [w for w in warnings if w.severity == "warning"]
        self.assertGreater(len(warning_msgs), 0)
        self.assertTrue(any("long" in w.message.lower() for w in warning_msgs))


class TestValidationWarning(unittest.TestCase):
    """Test ValidationWarning class."""

    def test_create_warning(self):
        """Test creating a ValidationWarning."""
        warning = ValidationWarning("warning", "Test message", "test_field")

        self.assertEqual(warning.severity, "warning")
        self.assertEqual(warning.message, "Test message")
        self.assertEqual(warning.field, "test_field")

    def test_warning_string_representation(self):
        """Test string representation of warning."""
        warning = ValidationWarning("error", "Test error", "test_field")
        string = str(warning)

        self.assertIn("ERROR", string)
        self.assertIn("Test error", string)
        self.assertIn("test_field", string)

    def test_warning_to_dict(self):
        """Test converting warning to dictionary."""
        warning = ValidationWarning("warning", "Test message", "test_field")
        d = warning.to_dict()

        self.assertEqual(d["severity"], "warning")
        self.assertEqual(d["message"], "Test message")
        self.assertEqual(d["field"], "test_field")


class TestExtractionValidation(unittest.TestCase):
    """Test comprehensive extraction validation."""

    def test_valid_extraction(self):
        """Test validation of valid extraction results."""
        symbols = {
            "indices": ["S&P 500"],
            "yahoo_symbols": ["^GSPC"],
            "raw_tickers": ["SPX"]
        }
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2027-01-15"
        }

        result = validate_extraction_results(symbols, dates)

        self.assertFalse(result["has_errors"])
        self.assertEqual(result["error_count"], 0)
        self.assertTrue(result["is_valid"])
        self.assertGreater(result["confidence_score"], 0.8)

    def test_extraction_with_errors(self):
        """Test validation with errors."""
        symbols = {
            "indices": [],
            "yahoo_symbols": [],
            "raw_tickers": []
        }
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2020-01-15"  # Error: before pricing!
        }

        result = validate_extraction_results(symbols, dates)

        self.assertTrue(result["has_errors"])
        self.assertGreater(result["error_count"], 0)
        self.assertFalse(result["is_valid"])

    def test_extraction_with_warnings(self):
        """Test validation with warnings only."""
        symbols = {
            "indices": [],
            "yahoo_symbols": [],
            "raw_tickers": []
        }
        dates = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2024-01-20"  # Warning: very short
        }

        result = validate_extraction_results(symbols, dates)

        self.assertFalse(result["has_errors"])
        self.assertTrue(result["has_warnings"])
        self.assertTrue(result["is_valid"])  # Valid despite warnings

    def test_confidence_score_calculation(self):
        """Test confidence score decreases with issues."""
        # Perfect extraction
        symbols_perfect = {
            "indices": ["S&P 500"],
            "yahoo_symbols": ["^GSPC"],
            "raw_tickers": ["SPX"]
        }
        dates_perfect = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2027-01-15"
        }
        result_perfect = validate_extraction_results(symbols_perfect, dates_perfect)

        # Extraction with errors
        symbols_error = {
            "indices": [],
            "yahoo_symbols": [],
            "raw_tickers": []
        }
        dates_error = {
            "pricing_date": "2024-01-15",
            "maturity_date": "2020-01-15"
        }
        result_error = validate_extraction_results(symbols_error, dates_error)

        # Perfect should have higher confidence
        self.assertGreater(
            result_perfect["confidence_score"],
            result_error["confidence_score"]
        )


if __name__ == "__main__":
    unittest.main()
