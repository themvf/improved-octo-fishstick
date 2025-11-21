"""
PDF support for structured products toolkit.

Extracts text from PDF filings using pdfplumber (optional dependency).
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Try to import pdfplumber (optional dependency)
try:
    import pdfplumber
    PDF_SUPPORT_AVAILABLE = True
    logger.debug("pdfplumber available - PDF support enabled")
except ImportError:
    PDF_SUPPORT_AVAILABLE = False
    logger.debug("pdfplumber not available - PDF support disabled")


def is_pdf_supported() -> bool:
    """
    Check if PDF support is available.

    Returns:
        True if pdfplumber is installed
    """
    return PDF_SUPPORT_AVAILABLE


def extract_text_from_pdf(
    pdf_path: str,
    max_pages: Optional[int] = None
) -> str:
    """
    Extract text from PDF file.

    Requires pdfplumber to be installed:
    pip install pdfplumber

    Args:
        pdf_path: Path to PDF file
        max_pages: Maximum number of pages to extract (None = all)

    Returns:
        Extracted text

    Raises:
        ImportError: If pdfplumber is not installed
        FileNotFoundError: If PDF file doesn't exist
    """
    if not PDF_SUPPORT_AVAILABLE:
        raise ImportError(
            "PDF support requires pdfplumber. Install it with: pip install pdfplumber"
        )

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Extracting text from PDF: {pdf_path}")

    extracted_text = []
    page_count = 0

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            pages_to_process = min(total_pages, max_pages) if max_pages else total_pages

            logger.info(f"Processing {pages_to_process} of {total_pages} pages")

            for page_num, page in enumerate(pdf.pages, start=1):
                if max_pages and page_num > max_pages:
                    break

                # Extract text from page
                text = page.extract_text()
                if text:
                    extracted_text.append(text)
                    page_count += 1

                    # Extract tables if present
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            # Convert table to text
                            table_text = table_to_text(table)
                            if table_text:
                                extracted_text.append(table_text)

                if page_num % 10 == 0:
                    logger.debug(f"Processed {page_num} pages")

    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}", exc_info=True)
        raise

    result = "\n\n".join(extracted_text)
    logger.info(f"Extracted {len(result)} characters from {page_count} pages")

    return result


def table_to_text(table: list) -> str:
    """
    Convert extracted PDF table to text.

    Args:
        table: Table data from pdfplumber (list of lists)

    Returns:
        Text representation of table
    """
    if not table:
        return ""

    lines = []
    for row in table:
        if row:
            # Join cells with tabs, filter out None values
            line = "\t".join(str(cell) if cell is not None else "" for cell in row)
            if line.strip():
                lines.append(line)

    return "\n".join(lines)


def extract_pdf_metadata(pdf_path: str) -> Dict[str, Any]:
    """
    Extract metadata from PDF file.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Dictionary with PDF metadata

    Raises:
        ImportError: If pdfplumber is not installed
    """
    if not PDF_SUPPORT_AVAILABLE:
        raise ImportError(
            "PDF support requires pdfplumber. Install it with: pip install pdfplumber"
        )

    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            metadata = pdf.metadata or {}

            return {
                "num_pages": len(pdf.pages),
                "title": metadata.get("Title"),
                "author": metadata.get("Author"),
                "subject": metadata.get("Subject"),
                "creator": metadata.get("Creator"),
                "producer": metadata.get("Producer"),
                "creation_date": metadata.get("CreationDate"),
                "modification_date": metadata.get("ModDate"),
            }

    except Exception as e:
        logger.error(f"Error extracting PDF metadata: {e}", exc_info=True)
        return {"error": str(e)}


def detect_pdf_type(pdf_path: str) -> str:
    """
    Detect if PDF is text-based or image-based (scanned).

    Args:
        pdf_path: Path to PDF file

    Returns:
        "text" or "image" or "unknown"

    Raises:
        ImportError: If pdfplumber is not installed
    """
    if not PDF_SUPPORT_AVAILABLE:
        raise ImportError(
            "PDF support requires pdfplumber. Install it with: pip install pdfplumber"
        )

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Check first few pages
            pages_to_check = min(3, len(pdf.pages))
            text_chars = 0

            for page in pdf.pages[:pages_to_check]:
                text = page.extract_text()
                if text:
                    text_chars += len(text.strip())

            # If we got substantial text, it's text-based
            if text_chars > 100:
                return "text"
            else:
                return "image"

    except Exception as e:
        logger.error(f"Error detecting PDF type: {e}")
        return "unknown"


def read_filing_content(
    file_path: str,
    max_pdf_pages: Optional[int] = None
) -> tuple[str, bool]:
    """
    Read filing content from file (supports HTML, TXT, PDF).

    Automatically detects file type and extracts content.

    Args:
        file_path: Path to filing file
        max_pdf_pages: Maximum pages to extract from PDF (None = all)

    Returns:
        Tuple of (content, is_html)

    Raises:
        ValueError: If file type is not supported
        FileNotFoundError: If file doesn't exist
    """
    file = Path(file_path)

    if not file.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    suffix = file.suffix.lower()

    # PDF files
    if suffix == ".pdf":
        if not PDF_SUPPORT_AVAILABLE:
            raise ImportError(
                "PDF support requires pdfplumber. Install it with: pip install pdfplumber"
            )

        logger.info(f"Reading PDF file: {file_path}")
        content = extract_text_from_pdf(file_path, max_pdf_pages)
        return content, False  # PDF text is not HTML

    # HTML files
    elif suffix in [".html", ".htm"]:
        logger.info(f"Reading HTML file: {file_path}")
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return content, True

    # Text files
    elif suffix in [".txt", ".text"]:
        logger.info(f"Reading text file: {file_path}")
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return content, False

    # Unknown extension - try to detect
    else:
        logger.warning(f"Unknown file extension '{suffix}', attempting to read as text")
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Detect if HTML
        is_html = content.strip().startswith('<')
        return content, is_html
