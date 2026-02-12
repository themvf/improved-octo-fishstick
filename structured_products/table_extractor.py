"""
HTML table key-value extractor for EDGAR structured product filings.

Parses HTML tables into structured label-value pairs *before* any regex runs,
taking advantage of the fact that EDGAR term sheets consistently encode key
parameters (initial price, threshold, coupon, etc.) as label-value pairs
inside <table> elements.

Handles 4 common EDGAR table patterns:
  1. Simple 2-column:  <td>Initial share price</td><td>$237.52</td>
  2. 3-column w/spacer: <td>Initial Value</td><td></td><td>$198.35</td>
  3. Inline label-value: <td><b>Initial price:</b> $237.52</td>
  4. Compound values:   <td>$166.264 (70.00% of the initial share price)</td>
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical field names → label patterns (issuer-agnostic)
# ---------------------------------------------------------------------------
# Each key is a canonical field name used throughout the pipeline.
# Each value is a list of regex patterns that match the *label* text found in
# table cells across Goldman Sachs, JP Morgan, UBS, Morgan Stanley, and
# Bank of America term sheets.
LABEL_MAP: Dict[str, List[str]] = {
    "initial_price": [
        r"initial\s+(?:share\s+)?price",
        r"initial\s+(?:underlier\s+)?value",
        r"initial\s+(?:stock\s+)?price",
        r"initial\s+level",
        r"initial\s+closing\s+(?:price|value|level)",
        r"(?:price|value)\s+on\s+(?:the\s+)?pricing\s+date",
    ],
    "threshold_dollar": [
        r"downside\s+threshold\s+level",
        r"threshold\s+level",
        r"(?:downside\s+)?threshold\s+(?:price|value|amount)",
        r"interest\s+barrier",
        r"trigger\s+(?:value|price|level)",
        r"coupon\s+barrier",
        r"barrier\s+level",
        r"(?:knock[- ]?in)\s+(?:barrier\s+)?(?:level|price|value)",
    ],
    "threshold_pct": [
        r"downside\s+threshold\s+level.*%",
        r"threshold\s+level.*%",
        r"barrier\s+(?:level|percentage).*%",
    ],
    "autocall_level": [
        r"call\s+threshold\s+level",
        r"(?:early\s+)?redemption\s+(?:threshold|level|price|trigger)",
        r"autocall\s+(?:trigger\s+)?(?:level|price|value)",
        r"call\s+level",
        r"call\s+price",
    ],
    "coupon_payment": [
        r"contingent\s+(?:quarterly|monthly|semi[- ]?annual|annual)\s+(?:coupon|payment)",
        r"contingent\s+interest\s+payment",
        r"contingent\s+coupon\s+(?:payment|amount)",
        r"coupon\s+(?:payment|amount)\s+per\s+(?:security|note)",
        r"interest\s+(?:payment|amount)\s+per\s+(?:security|note)",
    ],
    "coupon_rate_pct": [
        r"contingent\s+coupon\s+rate",
        r"contingent\s+interest\s+rate",
        r"coupon\s+rate",
        r"annual\s+coupon\s+rate",
        r"interest\s+rate\s+per\s+annum",
    ],
    "notional": [
        r"(?:stated\s+)?principal\s+amount\s+per\s+(?:security|note)",
        r"(?:stated\s+)?principal\s+amount(?:/original\s+issue\s+price)?",
        r"denomination",
        r"face\s+(?:amount|value)",
        r"notional\s+amount",
    ],
    "maturity_date": [
        r"maturity\s+date",
        r"final\s+(?:valuation|payment)\s+date",
    ],
    "pricing_date": [
        r"pricing\s+date",
        r"(?:initial\s+)?valuation\s+date",
        r"trade\s+date",
        r"strike\s+date",
    ],
    "issue_date": [
        r"(?:original\s+)?issue\s+date",
        r"settlement\s+date",
    ],
    "issuer": [
        r"issuer",
    ],
    "underlying": [
        r"underlying(?:\s+(?:stock|security|asset|index))?",
        r"reference\s+(?:stock|asset|index|security)",
    ],
    "cusip": [
        r"cusip",
    ],
    "isin": [
        r"isin",
    ],
    "payment_frequency": [
        r"(?:coupon\s+)?payment\s+frequency",
        r"(?:interest\s+)?payment\s+(?:period|frequency|schedule)",
        r"observation\s+frequency",
    ],
}


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------
_MONEY_RE = re.compile(r"\$\s*([0-9]{1,3}(?:,?[0-9]{3})*(?:\.[0-9]+)?)")
_PCT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")
_DATE_RE = re.compile(
    r"(?:(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
    r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})",
    re.IGNORECASE,
)
_PURE_NUMBER_RE = re.compile(r"^[\s$]*([0-9]{1,3}(?:,?[0-9]{3})*(?:\.[0-9]+)?)[\s%$]*$")


def parse_value(raw: str) -> Dict:
    """
    Parse a raw cell value into typed data.

    Returns a dict with keys:
      - raw: original string
      - dollar: float or None (dollar amounts)
      - pct: float or None (percentage values)
      - date: str or None (ISO date string)
      - text: cleaned text
      - compound_pct: float or None (percentage extracted from compound values
                      like "$166.264 (70.00% of the initial share price)")
    """
    result = {"raw": raw, "dollar": None, "pct": None, "date": None,
              "text": raw.strip(), "compound_pct": None}

    if not raw or not raw.strip():
        return result

    cleaned = raw.strip()

    # Dollar amount
    m_dollar = _MONEY_RE.search(cleaned)
    if m_dollar:
        try:
            result["dollar"] = float(m_dollar.group(1).replace(",", ""))
        except ValueError:
            pass

    # Percentage
    m_pct = _PCT_RE.search(cleaned)
    if m_pct:
        try:
            result["pct"] = float(m_pct.group(1))
        except ValueError:
            pass

    # Compound value: "$166.264 (70.00% of the initial share price)"
    # If we found both dollar and pct, mark the pct as compound
    if result["dollar"] is not None and result["pct"] is not None:
        result["compound_pct"] = result["pct"]

    # Date
    m_date = _DATE_RE.search(cleaned)
    if m_date:
        try:
            from dateutil import parser as date_parser
            parsed = date_parser.parse(m_date.group(0), fuzzy=False)
            result["date"] = parsed.strftime("%Y-%m-%d")
        except (ValueError, TypeError, OverflowError, Exception):
            pass

    # Pure number without $ or % (might be a dollar amount contextually)
    if result["dollar"] is None and result["pct"] is None and result["date"] is None:
        m_num = _PURE_NUMBER_RE.match(cleaned)
        if m_num:
            try:
                result["dollar"] = float(m_num.group(1).replace(",", ""))
            except ValueError:
                pass

    return result


# ---------------------------------------------------------------------------
# Skip-detection for example/hypothetical tables
# ---------------------------------------------------------------------------
_SKIP_TABLE_RE = re.compile(
    r"(example|hypothetical|illustrative|for\s+illustration|scenario|assumed|"
    r"historical|past\s+performance|quarterly\s+(?:high|low|close))",
    re.IGNORECASE,
)


def _should_skip_table(rows: List[List[str]]) -> bool:
    """Return True if table appears to be example/hypothetical/historical data."""
    full_text = " ".join(" ".join(row) for row in rows[:3])  # check first 3 rows
    return bool(_SKIP_TABLE_RE.search(full_text))


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------
def extract_table_key_value_pairs(html: str) -> List[Dict]:
    """
    Iterate all <table> elements in *html*, identify label-value rows, and
    return a list of dicts:
      {
        "label": str,          # cleaned label text
        "value": dict,         # output of parse_value()
        "table_index": int,    # which table (0-based)
        "row_index": int,      # which row within that table
        "pattern": str,        # "2col" | "3col_spacer" | "inline" | "compound"
      }
    """
    soup = BeautifulSoup(html, "lxml")
    pairs: List[Dict] = []

    for tbl_idx, tbl in enumerate(soup.find_all("table")):
        rows = []
        for tr in tbl.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if cells:
                rows.append(cells)

        if not rows:
            continue

        # Get text version for skip detection
        text_rows = [[c.get_text(strip=True) for c in row] for row in rows]
        if _should_skip_table(text_rows):
            logger.debug(f"Skipping table {tbl_idx}: example/hypothetical")
            continue

        for row_idx, cell_elements in enumerate(rows):
            texts = [c.get_text(strip=True) for c in cell_elements]
            num_cells = len(texts)

            # Skip rows with too many cells (likely data tables, not label-value)
            if num_cells > 4:
                continue

            # Skip entirely empty rows
            if all(not t for t in texts):
                continue

            # --- Pattern 1: Simple 2-column label-value ---
            if num_cells == 2:
                label, val_text = texts[0], texts[1]
                if label and val_text and _looks_like_label(label):
                    pairs.append({
                        "label": _clean_label(label),
                        "value": parse_value(val_text),
                        "table_index": tbl_idx,
                        "row_index": row_idx,
                        "pattern": "2col",
                    })
                    continue

            # --- Pattern 2: 3-column with spacer (middle cell empty) ---
            if num_cells == 3:
                label, spacer, val_text = texts[0], texts[1], texts[2]
                if label and not spacer and val_text and _looks_like_label(label):
                    pairs.append({
                        "label": _clean_label(label),
                        "value": parse_value(val_text),
                        "table_index": tbl_idx,
                        "row_index": row_idx,
                        "pattern": "3col_spacer",
                    })
                    continue
                # Also try: first two are label, third is value (some Morgan Stanley)
                if label and spacer and val_text:
                    combined_label = f"{label} {spacer}".strip()
                    if _looks_like_label(combined_label):
                        pairs.append({
                            "label": _clean_label(combined_label),
                            "value": parse_value(val_text),
                            "table_index": tbl_idx,
                            "row_index": row_idx,
                            "pattern": "3col_spacer",
                        })
                        continue

            # --- Pattern 3: Inline label-value in a single cell ---
            # e.g. <td><b>Initial price:</b> $237.52</td>
            if num_cells >= 1:
                for cell_el in cell_elements:
                    # Check if cell has a bold/strong element followed by text
                    bold = cell_el.find(["b", "strong"])
                    if bold:
                        bold_text = bold.get_text(strip=True)
                        full_text = cell_el.get_text(strip=True)
                        # Value is the part after the bold text
                        remainder = full_text[len(bold_text):].strip().lstrip(":").strip()
                        if bold_text and remainder and _looks_like_label(bold_text):
                            pairs.append({
                                "label": _clean_label(bold_text),
                                "value": parse_value(remainder),
                                "table_index": tbl_idx,
                                "row_index": row_idx,
                                "pattern": "inline",
                            })
                            break

            # --- Pattern 4: Single cell with "Label: Value" or "Label ... $Value" ---
            if num_cells == 1:
                cell_text = texts[0]
                # Try splitting on colon
                if ":" in cell_text:
                    parts = cell_text.split(":", 1)
                    if len(parts) == 2 and _looks_like_label(parts[0].strip()):
                        pairs.append({
                            "label": _clean_label(parts[0].strip()),
                            "value": parse_value(parts[1].strip()),
                            "table_index": tbl_idx,
                            "row_index": row_idx,
                            "pattern": "inline",
                        })

    logger.info(f"Extracted {len(pairs)} key-value pairs from {tbl_idx + 1 if soup.find_all('table') else 0} tables")
    return pairs


# ---------------------------------------------------------------------------
# Label matching
# ---------------------------------------------------------------------------
def match_labels_to_fields(
    pairs: List[Dict],
    label_map: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Dict]:
    """
    Match extracted label-value pairs to canonical field names using LABEL_MAP.

    Returns a dict keyed by canonical field name, with values:
      {
        "value": <parsed value dict from parse_value()>,
        "label": str,            # original label text
        "confidence": float,     # 0.0-1.0
        "source": "table",
        "pattern": str,          # extraction pattern used
        "table_index": int,
        "row_index": int,
      }
    """
    if label_map is None:
        label_map = LABEL_MAP

    # Labels to EXCLUDE per field (e.g., "aggregate principal" is total offering, not per-security)
    LABEL_EXCLUSIONS: Dict[str, List[str]] = {
        "notional": [r"aggregate"],
    }

    matched: Dict[str, Dict] = {}

    for field_name, patterns in label_map.items():
        exclusions = LABEL_EXCLUSIONS.get(field_name, [])
        for pair in pairs:
            label_lower = pair["label"].lower()

            # Skip if label matches any exclusion pattern for this field
            if any(re.search(ex, label_lower, re.IGNORECASE) for ex in exclusions):
                continue

            for pat_idx, pattern in enumerate(patterns):
                if re.search(pattern, label_lower, re.IGNORECASE):
                    # Confidence: first pattern in list = highest confidence
                    confidence = 1.0 - (pat_idx * 0.1)
                    confidence = max(0.5, confidence)

                    # Only replace if higher confidence
                    if field_name not in matched or confidence > matched[field_name]["confidence"]:
                        matched[field_name] = {
                            "value": pair["value"],
                            "label": pair["label"],
                            "confidence": confidence,
                            "source": "table",
                            "pattern": pair["pattern"],
                            "table_index": pair["table_index"],
                            "row_index": pair["row_index"],
                        }
                    break  # matched this pair to this field, move on

    logger.info(f"Matched {len(matched)} fields from table pairs")
    return matched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _clean_label(label: str) -> str:
    """Normalize label text: strip footnote markers, trailing colons, extra whitespace."""
    label = label.strip()
    # Strip footnote/superscript markers: *, †, ‡, §, ¶, numbers in parens like (1)
    label = re.sub(r'[*†‡§¶\u2020\u2021\u0197\u00a7\u00b6]+', '', label)
    label = re.sub(r"[:\s]+$", "", label)
    label = re.sub(r"\s+", " ", label)
    return label.strip()


def _looks_like_label(text: str) -> bool:
    """
    Heuristic: does *text* look like a label (not a value)?

    Labels are typically:
      - 2+ words or a known single-word term
      - Not purely numeric / dollar / percentage
      - Not excessively long (>120 chars is likely a paragraph)
    """
    text = text.strip().rstrip(":")
    if not text:
        return False
    if len(text) > 120:
        return False
    # Pure numbers / dollar amounts / percentages are values, not labels
    if re.match(r"^[\s$]*[0-9,]+(?:\.[0-9]+)?\s*[%$]?\s*$", text):
        return False
    # Single character is not a label
    if len(text) <= 1:
        return False
    return True
