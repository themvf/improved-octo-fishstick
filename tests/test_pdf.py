"""
Unit tests for PDF extraction module.
"""

import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
from structured_products.pdf import (
    is_pdf_supported,
    extract_text_from_pdf,
    extract_pdf_metadata,
    detect_pdf_type,
    read_filing_content,
)


class TestPDFSupport:
    """Test PDF support detection."""

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    def test_pdf_support_available(self):
        """Test PDF support detection when pdfplumber is available."""
        assert is_pdf_supported()

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', False)
    def test_pdf_support_not_available(self):
        """Test PDF support detection when pdfplumber is not available."""
        assert not is_pdf_supported()


class TestPDFTextExtraction:
    """Test PDF text extraction."""

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_extract_text_from_single_page(self, mock_pdfplumber):
        """Test text extraction from single-page PDF."""
        # Mock PDF with one page
        mock_page = Mock()
        mock_page.extract_text.return_value = "Test PDF content"
        mock_page.extract_tables.return_value = []

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        text = extract_text_from_pdf("test.pdf")
        assert "Test PDF content" in text

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_extract_text_from_multi_page(self, mock_pdfplumber):
        """Test text extraction from multi-page PDF."""
        # Mock PDF with multiple pages
        mock_page1 = Mock()
        mock_page1.extract_text.return_value = "Page 1 content"
        mock_page1.extract_tables.return_value = []

        mock_page2 = Mock()
        mock_page2.extract_text.return_value = "Page 2 content"
        mock_page2.extract_tables.return_value = []

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page1, mock_page2]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        text = extract_text_from_pdf("test.pdf")
        assert "Page 1 content" in text
        assert "Page 2 content" in text
        assert "[Page 1]" in text
        assert "[Page 2]" in text

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_extract_text_with_max_pages(self, mock_pdfplumber):
        """Test text extraction with max_pages limit."""
        # Mock PDF with 3 pages
        mock_pages = []
        for i in range(3):
            mock_page = Mock()
            mock_page.extract_text.return_value = f"Page {i+1} content"
            mock_page.extract_tables.return_value = []
            mock_pages.append(mock_page)

        mock_pdf = Mock()
        mock_pdf.pages = mock_pages
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        # Extract only 2 pages
        text = extract_text_from_pdf("test.pdf", max_pages=2)
        assert "Page 1 content" in text
        assert "Page 2 content" in text
        assert "Page 3 content" not in text

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_extract_text_with_tables(self, mock_pdfplumber):
        """Test text extraction includes table data."""
        # Mock PDF with table
        mock_page = Mock()
        mock_page.extract_text.return_value = "Header text"
        mock_page.extract_tables.return_value = [
            [["Name", "Value"], ["Rate", "5%"], ["Cap", "10%"]]
        ]

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        text = extract_text_from_pdf("test.pdf")
        assert "Header text" in text
        assert "[Table:" in text
        assert "Name | Value" in text
        assert "Rate | 5%" in text

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', False)
    def test_extract_text_no_pdfplumber(self):
        """Test extraction raises error when pdfplumber not available."""
        with pytest.raises(ImportError, match="pdfplumber"):
            extract_text_from_pdf("test.pdf")


class TestPDFMetadataExtraction:
    """Test PDF metadata extraction."""

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_extract_metadata(self, mock_pdfplumber):
        """Test metadata extraction from PDF."""
        # Mock PDF with metadata
        mock_pdf = Mock()
        mock_pdf.metadata = {
            "Title": "Test Document",
            "Author": "Test Author",
            "CreationDate": "D:20240101120000",
        }
        mock_pdf.pages = [Mock(), Mock()]  # 2 pages
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        metadata = extract_pdf_metadata("test.pdf")
        assert metadata["title"] == "Test Document"
        assert metadata["author"] == "Test Author"
        assert metadata["num_pages"] == 2

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_extract_metadata_empty(self, mock_pdfplumber):
        """Test metadata extraction when no metadata present."""
        # Mock PDF without metadata
        mock_pdf = Mock()
        mock_pdf.metadata = {}
        mock_pdf.pages = [Mock()]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        metadata = extract_pdf_metadata("test.pdf")
        assert metadata["title"] is None
        assert metadata["author"] is None
        assert metadata["num_pages"] == 1

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', False)
    def test_extract_metadata_no_pdfplumber(self):
        """Test metadata extraction raises error when pdfplumber not available."""
        with pytest.raises(ImportError, match="pdfplumber"):
            extract_pdf_metadata("test.pdf")


class TestPDFTypeDetection:
    """Test PDF type detection."""

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_detect_text_pdf(self, mock_pdfplumber):
        """Test detection of text-based PDF."""
        # Mock PDF with substantial text
        mock_page = Mock()
        mock_page.extract_text.return_value = "This is a text-based PDF with substantial content."

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        pdf_type = detect_pdf_type("test.pdf")
        assert pdf_type == "text"

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_detect_image_pdf(self, mock_pdfplumber):
        """Test detection of image-based PDF."""
        # Mock PDF with minimal text (image-based)
        mock_page = Mock()
        mock_page.extract_text.return_value = ""

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        pdf_type = detect_pdf_type("test.pdf")
        assert pdf_type == "image"

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', False)
    def test_detect_type_no_pdfplumber(self):
        """Test type detection raises error when pdfplumber not available."""
        with pytest.raises(ImportError, match="pdfplumber"):
            detect_pdf_type("test.pdf")


class TestReadFilingContent:
    """Test universal file reading function."""

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_read_pdf_file(self, mock_pdfplumber):
        """Test reading PDF file."""
        # Mock PDF
        mock_page = Mock()
        mock_page.extract_text.return_value = "PDF content"
        mock_page.extract_tables.return_value = []

        mock_pdf = Mock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        content, is_html = read_filing_content("test.pdf")
        assert "PDF content" in content
        assert not is_html

    @patch('builtins.open', new_callable=mock_open, read_data="<html><body>HTML content</body></html>")
    def test_read_html_file(self, mock_file):
        """Test reading HTML file."""
        content, is_html = read_filing_content("test.html")
        assert "HTML content" in content
        assert is_html

    @patch('builtins.open', new_callable=mock_open, read_data="<html><body>HTML content</body></html>")
    def test_read_htm_file(self, mock_file):
        """Test reading HTM file."""
        content, is_html = read_filing_content("test.htm")
        assert "HTML content" in content
        assert is_html

    @patch('builtins.open', new_callable=mock_open, read_data="Plain text content")
    def test_read_text_file(self, mock_file):
        """Test reading plain text file."""
        content, is_html = read_filing_content("test.txt")
        assert "Plain text content" in content
        assert not is_html

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', False)
    def test_read_pdf_no_support(self):
        """Test reading PDF raises error when pdfplumber not available."""
        with pytest.raises(ImportError, match="pdfplumber"):
            read_filing_content("test.pdf")

    def test_read_nonexistent_file(self):
        """Test reading non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            read_filing_content("nonexistent.txt")

    @patch('builtins.open', new_callable=mock_open, read_data="")
    def test_read_empty_file(self, mock_file):
        """Test reading empty file."""
        content, is_html = read_filing_content("empty.txt")
        assert content == ""
        assert not is_html


class TestHTMLDetection:
    """Test HTML content detection."""

    @patch('builtins.open', new_callable=mock_open, read_data="<html>Content</html>")
    def test_html_detected_from_tags(self, mock_file):
        """Test HTML detected from tags."""
        content, is_html = read_filing_content("file.txt")
        assert is_html

    @patch('builtins.open', new_callable=mock_open, read_data="<HTML>Content</HTML>")
    def test_html_detected_uppercase(self, mock_file):
        """Test HTML detected with uppercase tags."""
        content, is_html = read_filing_content("file.txt")
        assert is_html

    @patch('builtins.open', new_callable=mock_open, read_data="Plain text without HTML tags")
    def test_text_not_detected_as_html(self, mock_file):
        """Test plain text not detected as HTML."""
        content, is_html = read_filing_content("file.txt")
        assert not is_html


class TestPDFMaxPages:
    """Test max_pages parameter handling."""

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_read_pdf_with_max_pages(self, mock_pdfplumber):
        """Test reading PDF with max_pages limit."""
        # Mock PDF with 5 pages
        mock_pages = []
        for i in range(5):
            mock_page = Mock()
            mock_page.extract_text.return_value = f"Page {i+1}"
            mock_page.extract_tables.return_value = []
            mock_pages.append(mock_page)

        mock_pdf = Mock()
        mock_pdf.pages = mock_pages
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        # Read only 2 pages
        content, is_html = read_filing_content("test.pdf", max_pdf_pages=2)
        assert "Page 1" in content
        assert "Page 2" in content
        assert "Page 3" not in content
        assert not is_html

    @patch('structured_products.pdf.PDF_SUPPORT_AVAILABLE', True)
    @patch('pdfplumber.open')
    def test_read_pdf_no_max_pages(self, mock_pdfplumber):
        """Test reading PDF without max_pages limit (all pages)."""
        # Mock PDF with 3 pages
        mock_pages = []
        for i in range(3):
            mock_page = Mock()
            mock_page.extract_text.return_value = f"Page {i+1}"
            mock_page.extract_tables.return_value = []
            mock_pages.append(mock_page)

        mock_pdf = Mock()
        mock_pdf.pages = mock_pages
        mock_pdf.__enter__ = Mock(return_value=mock_pdf)
        mock_pdf.__exit__ = Mock(return_value=False)

        mock_pdfplumber.return_value = mock_pdf

        content, is_html = read_filing_content("test.pdf")
        assert "Page 1" in content
        assert "Page 2" in content
        assert "Page 3" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
