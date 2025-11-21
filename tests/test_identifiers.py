"""
Unit tests for security identifiers module.
"""

import pytest
from structured_products.identifiers import (
    validate_cusip,
    validate_isin,
    validate_sedol,
    extract_cusip,
    extract_isin,
    extract_sedol,
    extract_all_identifiers,
    cusip_to_isin,
    format_cusip,
    format_isin,
)


class TestCUSIPValidation:
    """Test CUSIP validation and check digit calculation."""

    def test_valid_cusip_apple(self):
        """Test valid CUSIP for Apple Inc."""
        assert validate_cusip("037833100")

    def test_valid_cusip_microsoft(self):
        """Test valid CUSIP for Microsoft."""
        assert validate_cusip("594918104")

    def test_valid_cusip_google(self):
        """Test valid CUSIP for Google/Alphabet."""
        assert validate_cusip("02079K107")

    def test_invalid_cusip_wrong_length(self):
        """Test CUSIP with wrong length is invalid."""
        assert not validate_cusip("12345")
        assert not validate_cusip("1234567890")

    def test_invalid_cusip_wrong_check_digit(self):
        """Test CUSIP with wrong check digit is invalid."""
        assert not validate_cusip("037833109")  # Should be 037833100

    def test_invalid_cusip_special_chars(self):
        """Test CUSIP with special characters is invalid."""
        assert not validate_cusip("037833-00")

    def test_cusip_lowercase_converted(self):
        """Test that lowercase CUSIP is accepted and validated."""
        assert validate_cusip("037833100")
        assert validate_cusip("02079k107")  # lowercase k


class TestISINValidation:
    """Test ISIN validation and check digit calculation."""

    def test_valid_isin_apple(self):
        """Test valid ISIN for Apple Inc."""
        assert validate_isin("US0378331005")

    def test_valid_isin_microsoft(self):
        """Test valid ISIN for Microsoft."""
        assert validate_isin("US5949181045")

    def test_valid_isin_uk_security(self):
        """Test valid ISIN for UK security."""
        assert validate_isin("GB0002374006")  # British Airways

    def test_invalid_isin_wrong_length(self):
        """Test ISIN with wrong length is invalid."""
        assert not validate_isin("US037833100")  # Too short
        assert not validate_isin("US03783310055")  # Too long

    def test_invalid_isin_wrong_format(self):
        """Test ISIN with wrong format is invalid."""
        assert not validate_isin("1S0378331005")  # First char must be letter
        assert not validate_isin("U10378331005")  # Second char must be letter

    def test_invalid_isin_wrong_check_digit(self):
        """Test ISIN with wrong check digit is invalid."""
        assert not validate_isin("US0378331006")  # Should be US0378331005

    def test_isin_lowercase_converted(self):
        """Test that lowercase ISIN is accepted and validated."""
        assert validate_isin("us0378331005")


class TestSEDOLValidation:
    """Test SEDOL validation."""

    def test_valid_sedol(self):
        """Test valid SEDOL."""
        assert validate_sedol("0263494")  # British Airways

    def test_valid_sedol_with_letters(self):
        """Test valid SEDOL with letters."""
        assert validate_sedol("B0WNLY7")

    def test_invalid_sedol_wrong_length(self):
        """Test SEDOL with wrong length is invalid."""
        assert not validate_sedol("12345")
        assert not validate_sedol("12345678")

    def test_invalid_sedol_special_chars(self):
        """Test SEDOL with special characters is invalid."""
        assert not validate_sedol("026-494")


class TestCUSIPExtraction:
    """Test CUSIP extraction from text."""

    def test_extract_cusip_standard_format(self):
        """Test extraction of CUSIP in standard format."""
        text = "CUSIP: 037833100"
        cusip = extract_cusip(text)
        assert cusip == "037833100"

    def test_extract_cusip_no_colon(self):
        """Test extraction of CUSIP without colon."""
        text = "CUSIP 037833100"
        cusip = extract_cusip(text)
        assert cusip == "037833100"

    def test_extract_cusip_with_no(self):
        """Test extraction of CUSIP with 'No.' label."""
        text = "CUSIP No.: 037833100"
        cusip = extract_cusip(text)
        assert cusip == "037833100"

    def test_extract_cusip_in_sentence(self):
        """Test extraction of CUSIP embedded in sentence."""
        text = "The security has CUSIP 037833100 and trades on NYSE."
        cusip = extract_cusip(text)
        assert cusip == "037833100"

    def test_extract_cusip_multiple_finds_first(self):
        """Test extraction finds first valid CUSIP when multiple present."""
        text = "CUSIP: 037833100, also see CUSIP: 594918104"
        cusip = extract_cusip(text)
        assert cusip == "037833100"

    def test_extract_cusip_invalid_check_digit_skipped(self):
        """Test that CUSIP with invalid check digit is skipped."""
        text = "CUSIP: 037833109"  # Invalid check digit
        cusip = extract_cusip(text)
        assert cusip is None

    def test_extract_cusip_not_found(self):
        """Test extraction returns None when no CUSIP found."""
        text = "This text has no CUSIP"
        cusip = extract_cusip(text)
        assert cusip is None

    def test_extract_cusip_lowercase(self):
        """Test extraction handles lowercase CUSIP."""
        text = "cusip: 02079k107"
        cusip = extract_cusip(text)
        assert cusip == "02079K107"  # Returns uppercase


class TestISINExtraction:
    """Test ISIN extraction from text."""

    def test_extract_isin_standard_format(self):
        """Test extraction of ISIN in standard format."""
        text = "ISIN: US0378331005"
        isin = extract_isin(text)
        assert isin == "US0378331005"

    def test_extract_isin_no_colon(self):
        """Test extraction of ISIN without colon."""
        text = "ISIN US0378331005"
        isin = extract_isin(text)
        assert isin == "US0378331005"

    def test_extract_isin_in_sentence(self):
        """Test extraction of ISIN embedded in sentence."""
        text = "The security ISIN US0378331005 is listed on NYSE."
        isin = extract_isin(text)
        assert isin == "US0378331005"

    def test_extract_isin_invalid_check_digit_skipped(self):
        """Test that ISIN with invalid check digit is skipped."""
        text = "ISIN: US0378331006"  # Invalid check digit
        isin = extract_isin(text)
        assert isin is None

    def test_extract_isin_not_found(self):
        """Test extraction returns None when no ISIN found."""
        text = "This text has no ISIN"
        isin = extract_isin(text)
        assert isin is None

    def test_extract_isin_lowercase(self):
        """Test extraction handles lowercase ISIN."""
        text = "isin: us0378331005"
        isin = extract_isin(text)
        assert isin == "US0378331005"  # Returns uppercase


class TestSEDOLExtraction:
    """Test SEDOL extraction from text."""

    def test_extract_sedol_standard_format(self):
        """Test extraction of SEDOL in standard format."""
        text = "SEDOL: 0263494"
        sedol = extract_sedol(text)
        assert sedol == "0263494"

    def test_extract_sedol_in_sentence(self):
        """Test extraction of SEDOL embedded in sentence."""
        text = "The UK security SEDOL 0263494 trades on LSE."
        sedol = extract_sedol(text)
        assert sedol == "0263494"

    def test_extract_sedol_not_found(self):
        """Test extraction returns None when no SEDOL found."""
        text = "This text has no SEDOL"
        sedol = extract_sedol(text)
        assert sedol is None


class TestExtractAllIdentifiers:
    """Test extraction of all identifiers from text."""

    def test_extract_all_from_text(self):
        """Test extraction of all identifiers from plain text."""
        text = """
        Security Information:
        CUSIP: 037833100
        ISIN: US0378331005
        SEDOL: 2046251
        """
        identifiers = extract_all_identifiers(text, is_html=False)
        assert identifiers["cusip"] == "037833100"
        assert identifiers["isin"] == "US0378331005"
        assert identifiers["sedol"] == "2046251"

    def test_extract_all_partial(self):
        """Test extraction when only some identifiers are present."""
        text = "CUSIP: 037833100"
        identifiers = extract_all_identifiers(text, is_html=False)
        assert identifiers["cusip"] == "037833100"
        assert identifiers["isin"] is None
        assert identifiers["sedol"] is None

    def test_extract_all_none_found(self):
        """Test extraction when no identifiers are found."""
        text = "This text has no identifiers"
        identifiers = extract_all_identifiers(text, is_html=False)
        assert identifiers["cusip"] is None
        assert identifiers["isin"] is None
        assert identifiers["sedol"] is None

    def test_extract_all_from_html(self):
        """Test extraction from HTML content."""
        html = """
        <html>
        <body>
            <div class="security-info">
                <p>CUSIP: 037833100</p>
                <p>ISIN: US0378331005</p>
            </div>
        </body>
        </html>
        """
        identifiers = extract_all_identifiers(html, is_html=True)
        assert identifiers["cusip"] == "037833100"
        assert identifiers["isin"] == "US0378331005"


class TestCUSIPToISIN:
    """Test CUSIP to ISIN conversion."""

    def test_cusip_to_isin_apple(self):
        """Test conversion of Apple CUSIP to ISIN."""
        isin = cusip_to_isin("037833100", country_code="US")
        assert isin == "US0378331005"

    def test_cusip_to_isin_microsoft(self):
        """Test conversion of Microsoft CUSIP to ISIN."""
        isin = cusip_to_isin("594918104", country_code="US")
        assert isin == "US5949181045"

    def test_cusip_to_isin_canada(self):
        """Test conversion with Canada country code."""
        cusip = "000360206"  # Example Canadian CUSIP
        isin = cusip_to_isin(cusip, country_code="CA")
        assert isin.startswith("CA")
        assert len(isin) == 12

    def test_cusip_to_isin_invalid_cusip(self):
        """Test conversion with invalid CUSIP returns None."""
        isin = cusip_to_isin("12345", country_code="US")
        assert isin is None

    def test_cusip_to_isin_invalid_country(self):
        """Test conversion with invalid country code returns None."""
        isin = cusip_to_isin("037833100", country_code="USA")  # 3 chars invalid
        assert isin is None


class TestFormatting:
    """Test identifier formatting functions."""

    def test_format_cusip_valid(self):
        """Test CUSIP formatting."""
        formatted = format_cusip("037833100")
        assert formatted == "037833-10-0"

    def test_format_cusip_invalid(self):
        """Test CUSIP formatting with invalid input."""
        formatted = format_cusip("12345")
        assert formatted == "12345"  # Returns as-is if invalid

    def test_format_isin_valid(self):
        """Test ISIN formatting."""
        formatted = format_isin("US0378331005")
        assert formatted == "US 0378331005"

    def test_format_isin_invalid(self):
        """Test ISIN formatting with invalid input."""
        formatted = format_isin("12345")
        assert formatted == "12345"  # Returns as-is if invalid


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_extract_cusip_from_empty_string(self):
        """Test extraction from empty string."""
        cusip = extract_cusip("")
        assert cusip is None

    def test_extract_isin_from_empty_string(self):
        """Test extraction from empty string."""
        isin = extract_isin("")
        assert isin is None

    def test_validate_cusip_none(self):
        """Test validation with None input."""
        assert not validate_cusip(None)

    def test_validate_isin_none(self):
        """Test validation with None input."""
        assert not validate_isin(None)

    def test_extract_all_from_none(self):
        """Test extraction from None."""
        identifiers = extract_all_identifiers(None, is_html=False)
        assert identifiers["cusip"] is None
        assert identifiers["isin"] is None
        assert identifiers["sedol"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
