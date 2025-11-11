"""
Unit tests for parser module.
"""

import unittest
from datetime import datetime
from structured_products.parser import (
    extract_symbols,
    extract_dates,
    extract_text_from_html,
    extract_date_from_text
)


class TestSymbolExtraction(unittest.TestCase):
    """Test symbol extraction functionality."""

    def test_extract_sp500_from_text(self):
        """Test extraction of S&P 500 index."""
        content = "This product is linked to the S&P 500 Index."
        result = extract_symbols(content, is_html=False)

        self.assertIn("S&P 500", result["indices"])
        self.assertIn("^GSPC", result["yahoo_symbols"])

    def test_extract_russell_2000(self):
        """Test extraction of Russell 2000 index."""
        content = "Performance based on Russell 2000 Index."
        result = extract_symbols(content, is_html=False)

        self.assertIn("RUSSELL 2000", result["indices"])
        self.assertIn("^RUT", result["yahoo_symbols"])

    def test_extract_multiple_indices(self):
        """Test extraction of multiple indices."""
        content = "Linked to S&P 500 and Russell 2000 indices."
        result = extract_symbols(content, is_html=False)

        self.assertEqual(len(result["indices"]), 2)
        self.assertIn("^GSPC", result["yahoo_symbols"])
        self.assertIn("^RUT", result["yahoo_symbols"])

    def test_extract_ticker_symbols(self):
        """Test extraction of ticker symbols."""
        content = "Symbols: ^GSPC, AAPL, MSFT, TSLA"
        result = extract_symbols(content, is_html=False)

        self.assertIn("^GSPC", result["raw_tickers"])
        self.assertIn("AAPL", result["raw_tickers"])
        self.assertIn("MSFT", result["raw_tickers"])

    def test_additional_symbols(self):
        """Test adding additional symbols."""
        content = "Product linked to SPX."
        result = extract_symbols(
            content,
            is_html=False,
            additional_symbols=["^IXIC", "^DJI"]
        )

        self.assertIn("^IXIC", result["yahoo_symbols"])
        self.assertIn("^DJI", result["yahoo_symbols"])

    def test_case_insensitivity(self):
        """Test that extraction is case-insensitive."""
        content = "linked to the s&p 500 index"
        result = extract_symbols(content, is_html=False)

        self.assertIn("S&P 500", result["indices"])

    def test_empty_content(self):
        """Test extraction from empty content."""
        result = extract_symbols("", is_html=False)

        self.assertEqual(len(result["indices"]), 0)
        self.assertEqual(len(result["yahoo_symbols"]), 0)

    def test_html_extraction(self):
        """Test extraction from HTML content."""
        html = "<html><body><h1>S&P 500 Product</h1><p>Russell 2000</p></body></html>"
        result = extract_symbols(html, is_html=True)

        self.assertIn("S&P 500", result["indices"])
        self.assertIn("RUSSELL 2000", result["indices"])


class TestDateExtraction(unittest.TestCase):
    """Test date extraction functionality."""

    def test_extract_pricing_date(self):
        """Test extraction of pricing date."""
        content = "Pricing Date: January 15, 2024"
        result = extract_dates(content, is_html=False)

        self.assertIn("pricing_date", result)
        self.assertEqual(result["pricing_date"], "2024-01-15")

    def test_extract_maturity_date(self):
        """Test extraction of maturity date."""
        content = "Maturity Date: 01/15/2027"
        result = extract_dates(content, is_html=False)

        self.assertIn("maturity_date", result)
        # Should parse MM/DD/YYYY format
        self.assertIsNotNone(result["maturity_date"])

    def test_extract_multiple_dates(self):
        """Test extraction of multiple dates."""
        content = """
        Pricing Date: January 15, 2024
        Trade Date: January 18, 2024
        Maturity Date: January 15, 2027
        """
        result = extract_dates(content, is_html=False)

        self.assertIn("pricing_date", result)
        self.assertIn("trade_date", result)
        self.assertIn("maturity_date", result)

    def test_extract_valuation_dates(self):
        """Test extraction of valuation dates."""
        content = """
        Initial Valuation Date: 2024-01-15
        Final Valuation Date: 2027-01-15
        """
        result = extract_dates(content, is_html=False)

        self.assertIn("initial_valuation_date", result)
        self.assertIn("final_valuation_date", result)

    def test_various_date_formats(self):
        """Test extraction of various date formats."""
        formats = [
            ("Trade Date: 01/15/2024", "trade_date"),
            ("Trade Date: 2024-01-15", "trade_date"),
            ("Trade Date: January 15, 2024", "trade_date"),
            ("Trade Date: 15 January 2024", "trade_date"),
        ]

        for content, key in formats:
            result = extract_dates(content, is_html=False)
            self.assertIn(key, result, f"Failed to extract from: {content}")

    def test_empty_content(self):
        """Test extraction from empty content."""
        result = extract_dates("", is_html=False)
        self.assertEqual(len(result), 0)

    def test_no_dates_found(self):
        """Test when no dates are found."""
        content = "This is a product description with no dates."
        result = extract_dates(content, is_html=False)
        self.assertEqual(len(result), 0)


class TestDateParsing(unittest.TestCase):
    """Test date parsing utility."""

    def test_parse_us_date_format(self):
        """Test parsing MM/DD/YYYY format."""
        date = extract_date_from_text("01/15/2024")
        self.assertIsNotNone(date)
        self.assertEqual(date.year, 2024)
        self.assertEqual(date.month, 1)
        self.assertEqual(date.day, 15)

    def test_parse_iso_date_format(self):
        """Test parsing YYYY-MM-DD format."""
        date = extract_date_from_text("2024-01-15")
        self.assertIsNotNone(date)
        self.assertEqual(date.year, 2024)
        self.assertEqual(date.month, 1)
        self.assertEqual(date.day, 15)

    def test_parse_long_date_format(self):
        """Test parsing 'Month DD, YYYY' format."""
        date = extract_date_from_text("January 15, 2024")
        self.assertIsNotNone(date)
        self.assertEqual(date.year, 2024)
        self.assertEqual(date.month, 1)
        self.assertEqual(date.day, 15)

    def test_parse_invalid_date(self):
        """Test parsing invalid date."""
        date = extract_date_from_text("not a date")
        # May return None or a fuzzy-parsed date
        # Just ensure it doesn't crash
        self.assertTrue(date is None or isinstance(date, datetime))


class TestHTMLExtraction(unittest.TestCase):
    """Test HTML text extraction."""

    def test_extract_text_from_simple_html(self):
        """Test extracting text from simple HTML."""
        html = "<html><body><p>Test content</p></body></html>"
        text = extract_text_from_html(html)

        self.assertIn("Test content", text)
        self.assertNotIn("<p>", text)
        self.assertNotIn("</p>", text)

    def test_remove_script_tags(self):
        """Test that script tags are removed."""
        html = """
        <html>
        <head><script>alert('test');</script></head>
        <body><p>Real content</p></body>
        </html>
        """
        text = extract_text_from_html(html)

        self.assertIn("Real content", text)
        self.assertNotIn("alert", text)

    def test_remove_style_tags(self):
        """Test that style tags are removed."""
        html = """
        <html>
        <head><style>.class { color: red; }</style></head>
        <body><p>Real content</p></body>
        </html>
        """
        text = extract_text_from_html(html)

        self.assertIn("Real content", text)
        self.assertNotIn("color:", text)


if __name__ == "__main__":
    unittest.main()
