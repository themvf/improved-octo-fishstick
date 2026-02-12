"""
Unified filing parsing pipeline for EDGAR structured product filings.

Implements a 3-tier extraction strategy:
  Tier 1 - HTML Tables (highest confidence): Structured label-value pairs
  Tier 2 - Issuer-specific regex (medium confidence): Per-issuer patterns
  Tier 3 - Generic regex (lowest confidence): Broad fallback patterns

After extraction, derives computed fields (threshold_pct, contingent_payment_pct),
cross-validates values, and tracks where each value came from for debugging.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple

from .table_extractor import (
    extract_table_key_value_pairs,
    match_labels_to_fields,
    LABEL_MAP,
)
from .parser import extract_text_from_html

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Regex helpers (shared by Tier 2 and Tier 3)
# ---------------------------------------------------------------------------
MONEY_RE = re.compile(
    r"\$?\s*([0-9]{1,3}(?:[,][0-9]{3})*(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?)"
)
PCT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*%")


# ---------------------------------------------------------------------------
# Issuer-specific regex configurations  (Tier 2)
# Moved from streamlit_app.py ISSUER_CONFIGS
# ---------------------------------------------------------------------------
ISSUER_CONFIGS: Dict[str, Dict[str, List[str]]] = {
    "Goldman Sachs": {
        "initial_patterns": [
            r"Initial\s+share\s+price[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "threshold_patterns": [
            r"Downside\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "autocall_patterns": [
            r"greater\s+than\s+or\s+equal\s+to\s+the\s+initial\s+(?:share\s+)?price",
        ],
        "coupon_patterns": [
            r"Contingent\s+(?:quarterly|monthly|semi-annual|annual)\s+coupon[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "notional_patterns": [
            r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
            r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "date_column_patterns": [
            "coupon determination date",
            "observation date",
        ],
    },
    "JP Morgan": {
        "initial_patterns": [
            r"Initial\s+Value[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "threshold_patterns": [
            r"(?:Interest\s+Barrier|Trigger\s+Value)[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "autocall_patterns": [
            r"automatic(?:ally)?\s+call(?:ed)?",
        ],
        "coupon_patterns": [
            r"Contingent\s+Interest\s+Payment[^$]{0,200}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "notional_patterns": [
            r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
            r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"each\s+security\s+has\s+a\s+(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "date_column_patterns": [
            "autocall observation",
            "review date",
            "observation date",
        ],
    },
    "UBS": {
        "initial_patterns": [
            r"Initial\s+[Pp]rice[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "threshold_patterns": [
            r"Trigger\s+[Pp]rice[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Coupon\s+[Bb]arrier[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Downside\s+threshold\s+level[:\s]+\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Downside\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "autocall_patterns": [
            r"equal\s+to\s+or\s+greater\s+than\s+the\s+initial\s+price",
            r"Call\s+threshold\s+level[:\s]+\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Call\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "coupon_patterns": [
            r"Contingent\s+[Cc]oupon\s+[Rr]ate[^0-9]{0,50}([0-9]+(?:\.[0-9]+)?)\s*%\s*per\s+annum",
            r"Contingent\s+Interest\s+Payment[^$]{0,200}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "notional_patterns": [
            r"\$\s*([0-9,]+(?:\.[0-9]+)?)\s+per\s+security",
            r"[Pp]rincipal\s+[Aa]mount[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)\s+per\s+security",
            r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
            r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "date_column_patterns": [
            "observation date",
            "determination date",
        ],
    },
    "Morgan Stanley": {
        "initial_patterns": [
            r"Initial\s+(?:share\s+)?price[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Initial\s+Value[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "threshold_patterns": [
            r"Downside\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "autocall_patterns": [
            r"Call\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Redemption\s+threshold[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "coupon_patterns": [
            r"Contingent\s+Interest\s+Payment[^$]{0,200}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Contingent\s+(?:quarterly|monthly|semi-annual|annual)\s+coupon[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "notional_patterns": [
            r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
            r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "date_column_patterns": [
            "determination date",
            "redemption determination date",
            "observation date",
        ],
    },
    "Bank of America": {
        "initial_patterns": [
            r"Initial\s+(?:share\s+)?price[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Initial\s+Value[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "threshold_patterns": [
            r"Downside\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "autocall_patterns": [
            r"Call\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"automatic(?:ally)?\s+call(?:ed)?",
        ],
        "coupon_patterns": [
            r"Contingent\s+Interest\s+Payment[^$]{0,200}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Contingent\s+(?:quarterly|monthly|semi-annual|annual)\s+coupon[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "notional_patterns": [
            r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
            r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "date_column_patterns": [
            "observation date",
            "observation dates",
            "determination date",
        ],
    },
    "Barclays": {
        "initial_patterns": [
            r"Initial\s+underlier\s+value[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Initial\s+(?:share\s+)?price[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Initial\s+Value[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "threshold_patterns": [
            r"Downside\s+threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Threshold\s+level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Knock[- ]?in\s+(?:barrier\s+)?level[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "autocall_patterns": [
            # These must match entries in _AUTOCALL_EQUALS_INITIAL_PATTERNS exactly
            r"greater\s+than\s+or\s+equal\s+to\s+the\s+initial\s+(?:share\s+)?(?:price|value|underlier\s+value|level)",
            r"at\s+or\s+above\s+the\s+initial\s+(?:share\s+)?(?:price|value|underlier\s+value|level)",
            r"automatic(?:ally)?\s+call(?:ed)?",
        ],
        "coupon_patterns": [
            r"Contingent\s+(?:quarterly|monthly|semi-annual|annual)\s+(?:coupon|payment)[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
            r"Contingent\s+Interest\s+Payment[^$]{0,200}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "notional_patterns": [
            r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
            r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        ],
        "date_column_patterns": [
            "determination date",
            "coupon determination date",
            "observation date",
        ],
    },
}

# Patterns without dollar capture groups (autocall equals initial price)
_AUTOCALL_EQUALS_INITIAL_PATTERNS = [
    r"greater\s+than\s+or\s+equal\s+to\s+the\s+initial\s+(?:share\s+)?(?:price|value|underlier\s+value|level)",
    r"equal\s+to\s+or\s+greater\s+than\s+the\s+initial\s+(?:price|value|underlier\s+value|level)",
    r"at\s+or\s+above\s+the\s+initial\s+(?:share\s+)?(?:price|value|underlier\s+value|level)",
    r"automatic(?:ally)?\s+call(?:ed)?",
]


# ---------------------------------------------------------------------------
# Issuer detection  (moved from streamlit_app.py)
# ---------------------------------------------------------------------------
_ISSUER_DETECT_PATTERNS: Dict[str, List[str]] = {
    "Goldman Sachs": [r"GS\s+Finance\s+Corp", r"Goldman\s+Sachs\s+&\s+Co"],
    "JP Morgan": [r"JPMorgan\s+Chase\s+Financial", r"J\.?P\.?\s*Morgan"],
    "UBS": [r"UBS\s+AG", r"UBS\s+Financial"],
    "Morgan Stanley": [r"Morgan\s+Stanley\s+Finance", r"Morgan\s+Stanley\s+&\s+Co"],
    "Credit Suisse": [r"Credit\s+Suisse", r"CS\s+Finance"],
    "HSBC": [r"HSBC\s+USA", r"HSBC\s+Bank"],
    "Citigroup": [r"Citigroup\s+Global\s+Markets", r"Citibank"],
    "Barclays": [r"Barclays\s+Bank", r"Barclays\s+Capital"],
    "Bank of America": [r"Bank\s+of\s+America", r"BofA\s+Finance", r"Merrill\s+Lynch"],
    "Royal Bank of Canada": [r"Royal\s+Bank\s+of\s+Canada", r"RBC\s+Capital"],
    "Bank of Montreal": [r"Bank\s+of\s+Montreal", r"BMO\s+Capital"],
    "CIBC": [r"CIBC\s+World\s+Markets", r"Canadian\s+Imperial\s+Bank"],
}


def detect_issuer(text: str) -> Optional[str]:
    """Auto-detect issuer from filing text."""
    for issuer, patterns in _ISSUER_DETECT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, flags=re.I):
                return issuer
    return None


# ---------------------------------------------------------------------------
# Tier 2: Issuer-specific regex extraction
# ---------------------------------------------------------------------------
def _extract_with_issuer_regex(
    text: str,
    config: Dict[str, List[str]],
    initial_price: Optional[float] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Apply issuer-specific regex patterns (Tier 2).

    Returns a dict keyed by canonical field name, each value containing:
      {"value": float_or_None, "source": "regex_issuer", "pattern": str}
    """
    result: Dict[str, Dict[str, Any]] = {}

    # --- initial_price ---
    for pattern in config.get("initial_patterns", []):
        m = re.search(pattern, text, flags=re.I)
        if m:
            result["initial_price"] = {
                "value": float(m.group(1).replace(",", "")),
                "source": "regex_issuer",
                "pattern": pattern,
            }
            break

    # Use found initial or the one passed in
    init_val = (
        result.get("initial_price", {}).get("value") or initial_price
    )

    # --- threshold_dollar ---
    for pattern in config.get("threshold_patterns", []):
        m = re.search(pattern, text, flags=re.I)
        if m:
            result["threshold_dollar"] = {
                "value": float(m.group(1).replace(",", "")),
                "source": "regex_issuer",
                "pattern": pattern,
            }
            break

    # --- autocall_level ---
    for pattern in config.get("autocall_patterns", []):
        # Check if this pattern has a capture group (i.e., extracts a dollar value)
        # vs. a semantic pattern like "greater than or equal to the initial price"
        has_capture_group = bool(re.search(r'\((?!\?)', pattern))
        if not has_capture_group:
            # No capture group → semantic "equals initial" pattern
            if re.search(pattern, text, flags=re.I) and init_val:
                result["autocall_level"] = {
                    "value": init_val,
                    "source": "regex_issuer",
                    "pattern": pattern,
                }
                break
        else:
            m = re.search(pattern, text, flags=re.I)
            if m:
                result["autocall_level"] = {
                    "value": float(m.group(1).replace(",", "")),
                    "source": "regex_issuer",
                    "pattern": pattern,
                }
                break

    # --- coupon_payment / coupon_rate_pct ---
    for pattern in config.get("coupon_patterns", []):
        m = re.search(pattern, text, flags=re.I)
        if m:
            value = float(m.group(1).replace(",", ""))
            if r"per\s+annum" in pattern:
                result["coupon_rate_pct"] = {
                    "value": value,
                    "source": "regex_issuer",
                    "pattern": pattern,
                }
            else:
                result["coupon_payment"] = {
                    "value": value,
                    "source": "regex_issuer",
                    "pattern": pattern,
                }
            break

    # --- notional ---
    for pattern in config.get("notional_patterns", []):
        m = re.search(pattern, text, flags=re.I)
        if m:
            result["notional"] = {
                "value": float(m.group(1).replace(",", "")),
                "source": "regex_issuer",
                "pattern": pattern,
            }
            break

    return result


# ---------------------------------------------------------------------------
# Tier 3: Generic regex fallbacks  (moved from streamlit_app.py)
# ---------------------------------------------------------------------------
def _extract_generic_initial_and_threshold(
    text: str,
) -> Dict[str, Dict[str, Any]]:
    """
    Generic (issuer-agnostic) extraction of initial price and threshold.
    Multi-strategy approach with cross-validation.
    """
    result: Dict[str, Dict[str, Any]] = {}
    initial: Optional[float] = None

    # Strategy 1: "Initial Value ... $XXX"
    m = re.search(r"Initial\s+Value[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)", text, flags=re.I)
    if m:
        initial = float(m.group(1).replace(",", ""))

    # Strategy 2: "Initial price ... $XXX"
    if initial is None:
        m = re.search(r"Initial\s+price[^$]{0,30}\$\s*([0-9,]+(?:\.[0-9]+)?)", text, flags=re.I)
        if m:
            initial = float(m.group(1).replace(",", ""))

    # Strategy 3: "Initial Share Price:" or "Initial Stock Price:" as labeled field
    if initial is None:
        m = re.search(
            r"Initial\s+(?:Share|Stock)\s+Price[^:$]*[:]\s*\$?\s*([0-9,]+(?:\.[0-9]+)?)",
            text, flags=re.I,
        )
        if m:
            initial = float(m.group(1).replace(",", ""))

    # Strategy 4: Section heading + nearby dollar amount
    if initial is None:
        for m in re.finditer(r"\b(Initial\s+(?:Share|Stock)\s+Price)\b", text, flags=re.I):
            snippet = text[m.end():m.end() + 200]
            m_val = re.search(r"\$\s*([0-9,]+(?:\.[0-9]+)?)", snippet)
            if m_val:
                initial = float(m_val.group(1).replace(",", ""))
                break

    # Strategy 5: Broadest fallback
    if initial is None:
        m = re.search(r"initial\s+share\s+price[^$]*\$\s*([0-9,]+(?:\.[0-9]+)?)", text, flags=re.I)
        if m:
            initial = float(m.group(1).replace(",", ""))

    if initial is not None:
        result["initial_price"] = {
            "value": initial,
            "source": "regex_generic",
            "pattern": "generic_initial",
        }

    # --- Threshold ---
    threshold_dollar: Optional[float] = None
    threshold_pct: Optional[float] = None

    # Look near threshold headings with a tight window
    for m in re.finditer(
        r"(interest\s+barrier|trigger\s+value|downside\s+threshold\s+level|"
        r"threshold\s+level|barrier\s+level)",
        text, flags=re.I,
    ):
        snippet = text[m.end():m.end() + 250]

        m_d = re.search(r"\$?\s*([0-9]{2,5}\.[0-9]{2,5})", snippet)
        if not m_d:
            m_d = MONEY_RE.search(snippet)
        m_p = re.search(
            r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:of\s+the\s+initial\s+(?:value|share\s+price))?",
            snippet, flags=re.I,
        )

        if m_d:
            threshold_dollar = float(m_d.group(1).replace(",", ""))
        if m_p:
            threshold_pct = float(m_p.group(1))

        if threshold_dollar is not None or threshold_pct is not None:
            break

    # Wider fallback
    if threshold_dollar is None:
        m = re.search(r"threshold\s+level[^$]*\$\s*([0-9,]+(?:\.[0-9]+)?)", text, flags=re.I)
        if m:
            threshold_dollar = float(m.group(1).replace(",", ""))
    if threshold_pct is None:
        m = re.search(r"threshold\s+level[^%]*([0-9]+(?:\.[0-9]+)?)\s*%", text, flags=re.I)
        if m:
            threshold_pct = float(m.group(1))

    # Compute $ from % if only % found
    if threshold_dollar is None and threshold_pct is not None and initial is not None:
        threshold_dollar = round(initial * (threshold_pct / 100.0), 10)

    # Cross-check
    if threshold_dollar is not None and threshold_pct is not None and initial is not None:
        implied_pct = (threshold_dollar / initial) * 100.0
        if abs(implied_pct - threshold_pct) > 2.0:
            threshold_dollar = round(initial * (threshold_pct / 100.0), 10)

    if threshold_dollar is not None:
        result["threshold_dollar"] = {
            "value": threshold_dollar,
            "source": "regex_generic",
            "pattern": "generic_threshold",
        }

    return result


def _extract_generic_autocall(
    text: str, initial: Optional[float]
) -> Optional[Dict[str, Any]]:
    """Generic autocall level extraction (Tier 3).

    Uses a sanity check: if *initial* is known, reject any dollar-based
    autocall candidate that exceeds 5× initial (likely an aggregate
    principal amount, not a per-security price level).
    """

    # --- Check semantic "equals initial" patterns FIRST ---
    # These are the most reliable because they describe the rule directly
    # rather than relying on a nearby dollar amount.
    if initial is not None:
        _EQUALS_INITIAL_PATS = [
            r"greater\s+than\s+or\s+equal\s+to\s+the\s+initial\s+"
            r"(?:share\s+)?(?:price|value|underlier\s+value|level)",
            r"equal\s+to\s+or\s+greater\s+than\s+the\s+initial\s+"
            r"(?:share\s+)?(?:price|value|underlier\s+value|level)",
            r"at\s+or\s+above\s+the\s+initial\s+"
            r"(?:share\s+)?(?:price|value|underlier\s+value|level)",
            r"at\s+least\s+(?:equal\s+to\s+)?the\s+initial\s+"
            r"(?:share\s+)?(?:price|value|underlier\s+value|level)",
        ]
        for pat in _EQUALS_INITIAL_PATS:
            if re.search(pat, text, flags=re.I):
                return {"value": float(initial), "source": "regex_generic",
                        "pattern": "generic_autocall_equals_initial"}

        # "100% of initial"
        if re.search(
            r"\b100\s*%\s*(?:of\s+the\s+initial|initial\s+(?:share\s+)?(?:price|value|underlier\s+value|level))",
            text, flags=re.I,
        ):
            return {"value": float(initial), "source": "regex_generic",
                    "pattern": "generic_autocall_100pct"}

    # --- Dollar/percentage based extraction from context windows ---
    candidates = []

    for m in re.finditer(
        r"(automatic(?:ally)?\s+call(?:ed)?|autocall|early\s+redemption)",
        text, flags=re.I,
    ):
        start = max(0, m.start() - 250)
        end = min(len(text), m.end() + 250)
        candidates.append(text[start:end])

    for m in re.finditer(
        r"(call\s+threshold\s+level|call\s+level|redemption\s+trigger|redemption\s+level)",
        text, flags=re.I,
    ):
        start = max(0, m.start() - 250)
        end = min(len(text), m.end() + 250)
        candidates.append(text[start:end])

    for s in candidates:
        m_usd = MONEY_RE.search(s)
        m_pct = PCT_RE.search(s)
        if m_usd:
            val = float(m_usd.group(1).replace(",", ""))
            # Sanity check: autocall level should be near the initial price,
            # not an aggregate principal amount (e.g., $27,544,000)
            if initial is not None and val > initial * 5:
                logger.debug(
                    f"Rejecting autocall candidate ${val:,.2f} "
                    f"(>5× initial ${initial:.2f})"
                )
                continue
            return {"value": val,
                    "source": "regex_generic", "pattern": "generic_autocall"}
        if m_pct and initial is not None:
            pct_val = float(m_pct.group(1))
            if 50 <= pct_val <= 150:  # reasonable autocall percentage range
                return {"value": initial * (pct_val / 100.0),
                        "source": "regex_generic", "pattern": "generic_autocall_pct"}

    return None


def _extract_generic_coupon_rate(text: str) -> Optional[Dict[str, Any]]:
    """Generic coupon rate extraction (Tier 3)."""
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:per\s*annum|p\.a\.|annual)", text, flags=re.I)
    if m:
        return {"value": float(m.group(1)), "source": "regex_generic",
                "pattern": "generic_coupon_rate_annual"}

    m = re.search(
        r"Contingent\s+Interest\s+Rate[^:]*[:]\s*([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:per\s*annum)?",
        text, flags=re.I,
    )
    if m:
        return {"value": float(m.group(1)), "source": "regex_generic",
                "pattern": "generic_contingent_interest_rate"}
    return None


def _extract_generic_coupon_payment(text: str) -> Optional[Dict[str, Any]]:
    """Generic coupon payment extraction (Tier 3)."""
    m = re.search(
        r"Contingent\s+(?:quarterly|monthly|semi-annual|annual)\s+coupon[^$]{0,50}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        text, flags=re.I,
    )
    if m:
        return {"value": float(m.group(1).replace(",", "")),
                "source": "regex_generic", "pattern": "generic_coupon_payment_gs"}

    m = re.search(
        r"Contingent\s+Interest\s+Payment[^$]{0,200}\$\s*([0-9,]+(?:\.[0-9]+)?)",
        text, flags=re.I,
    )
    if m:
        return {"value": float(m.group(1).replace(",", "")),
                "source": "regex_generic", "pattern": "generic_coupon_payment_cip"}
    return None


def _extract_generic_notional(text: str) -> Optional[Dict[str, Any]]:
    """Generic notional extraction (Tier 3)."""
    patterns = [
        r"per\s+\$\s*([0-9,]+(?:\.[0-9]+)?)\s+(?:stated\s+)?principal\s+amount",
        r"(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        r"each\s+(?:security|note)\s+has\s+a\s+(?:stated\s+)?principal\s+amount\s+of\s+\$\s*([0-9,]+(?:\.[0-9]+)?)",
        r"principal\s+amount\s+per\s+(?:security|note)[:\s]+\$\s*([0-9,]+(?:\.[0-9]+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return {"value": float(m.group(1).replace(",", "")),
                    "source": "regex_generic", "pattern": pat}
    return None


# ---------------------------------------------------------------------------
# ParsedFiling dataclass
# ---------------------------------------------------------------------------
@dataclass
class ParsedFiling:
    """Result of parsing an EDGAR filing through the 3-tier pipeline."""

    initial_price: Optional[float] = None
    threshold_dollar: Optional[float] = None
    threshold_pct: Optional[float] = None
    autocall_level: Optional[float] = None
    coupon_rate_annual: Optional[float] = None
    coupon_payment_per_period: Optional[float] = None
    contingent_payment_pct: Optional[float] = None
    notional: Optional[float] = None
    issuer: Optional[str] = None

    # Extraction metadata
    sources: Dict[str, str] = field(default_factory=dict)
    validation_warnings: List[str] = field(default_factory=list)

    # Supplemental terms from structured_products.terms
    product_terms: Dict[str, Any] = field(default_factory=dict)
    product_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Produce the exact same dict shape as the old analyze_filing_advanced()
        output, so the UI code needs no changes.
        """
        return {
            "initial_price": self.initial_price,
            "threshold_dollar": self.threshold_dollar,
            "threshold_pct": self.threshold_pct,
            "autocall_level": self.autocall_level,
            "coupon_rate_annual": self.coupon_rate_annual,
            "coupon_payment_per_period": self.coupon_payment_per_period,
            "contingent_payment_pct": self.contingent_payment_pct,
            "notional": self.notional,
            "issuer": self.issuer,
            # Metadata
            "extraction_sources": self.sources,
            "validation_warnings": self.validation_warnings,
            "product_terms": self.product_terms,
            "product_summary": self.product_summary,
        }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def parse_filing(
    content: str,
    is_html: bool,
    issuer: str = "Auto-detect",
) -> ParsedFiling:
    """
    Parse an EDGAR filing through a 3-tier extraction pipeline.

    Args:
        content: Raw file content (HTML or plain text)
        is_html: Whether *content* is HTML
        issuer: Issuer name, or "Auto-detect"

    Returns:
        ParsedFiling with all extracted fields and metadata
    """
    filing = ParsedFiling()
    sources: Dict[str, str] = {}

    # Convert to plain text (using the better version from parser.py)
    text = extract_text_from_html(content) if is_html else content

    # --- Detect issuer ---
    detected_issuer: Optional[str] = None
    if issuer == "Auto-detect":
        detected_issuer = detect_issuer(text)
        issuer = detected_issuer or "Auto-detect"
    filing.issuer = issuer if issuer != "Auto-detect" else detected_issuer

    # ===================================================================
    # Tier 1: HTML Table extraction (highest confidence)
    # ===================================================================
    table_fields: Dict[str, Dict] = {}
    if is_html:
        pairs = extract_table_key_value_pairs(content)
        table_fields = match_labels_to_fields(pairs)
        logger.info(f"Tier 1 (tables): matched {len(table_fields)} fields")

    # Helper to extract a typed value from table_fields
    def _table_dollar(field_name: str) -> Optional[float]:
        entry = table_fields.get(field_name)
        if entry:
            v = entry["value"]  # parse_value() result
            return v.get("dollar")
        return None

    def _table_pct(field_name: str) -> Optional[float]:
        entry = table_fields.get(field_name)
        if entry:
            v = entry["value"]
            return v.get("pct")
        return None

    # Extract from tables
    t1_initial = _table_dollar("initial_price")
    t1_threshold = _table_dollar("threshold_dollar")
    t1_threshold_pct = _table_pct("threshold_dollar") or _table_pct("threshold_pct")
    t1_autocall = _table_dollar("autocall_level")
    t1_coupon_payment = _table_dollar("coupon_payment")
    t1_coupon_rate = _table_pct("coupon_rate_pct")
    t1_notional = _table_dollar("notional")

    # ===================================================================
    # Tier 2: Issuer-specific regex (medium confidence)
    # ===================================================================
    t2: Dict[str, Dict[str, Any]] = {}
    if issuer in ISSUER_CONFIGS:
        config = ISSUER_CONFIGS[issuer]
        # First pass without initial to get initial_price
        t2 = _extract_with_issuer_regex(text, config, None)
        # Re-run with initial for autocall derivation
        init_for_t2 = (
            t1_initial
            or (t2.get("initial_price", {}).get("value"))
        )
        if init_for_t2:
            t2 = _extract_with_issuer_regex(text, config, init_for_t2)

    # ===================================================================
    # Tier 3: Generic regex (lowest confidence)
    # ===================================================================
    t3_init_thresh = _extract_generic_initial_and_threshold(text)
    # Determine best initial for generic autocall
    init_for_t3 = (
        t1_initial
        or t2.get("initial_price", {}).get("value")
        or t3_init_thresh.get("initial_price", {}).get("value")
    )
    t3_autocall = _extract_generic_autocall(text, init_for_t3)
    t3_coupon_rate = _extract_generic_coupon_rate(text)
    t3_coupon_payment = _extract_generic_coupon_payment(text)
    t3_notional = _extract_generic_notional(text)

    # ===================================================================
    # Merge: prefer Tier 1 > Tier 2 > Tier 3
    # ===================================================================
    def _pick(field: str, t1_val, t2_key: str, t3_val) -> Optional[float]:
        """Select best value across tiers and record source."""
        if t1_val is not None:
            sources[field] = "table"
            return t1_val
        if t2_key in t2:
            sources[field] = "regex_issuer"
            return t2[t2_key]["value"]
        if t3_val is not None:
            if isinstance(t3_val, dict):
                sources[field] = t3_val.get("source", "regex_generic")
                return t3_val["value"]
            sources[field] = "regex_generic"
            return t3_val
        return None

    filing.initial_price = _pick(
        "initial_price", t1_initial, "initial_price",
        t3_init_thresh.get("initial_price"),
    )
    filing.threshold_dollar = _pick(
        "threshold_dollar", t1_threshold, "threshold_dollar",
        t3_init_thresh.get("threshold_dollar"),
    )
    filing.autocall_level = _pick(
        "autocall_level", t1_autocall, "autocall_level", t3_autocall,
    )
    filing.coupon_payment_per_period = _pick(
        "coupon_payment_per_period", t1_coupon_payment, "coupon_payment",
        t3_coupon_payment,
    )
    filing.notional = _pick(
        "notional", t1_notional, "notional", t3_notional,
    )

    # Coupon rate: could be from table %, issuer regex, or generic
    if t1_coupon_rate is not None:
        filing.coupon_rate_annual = t1_coupon_rate
        sources["coupon_rate_annual"] = "table"
    elif "coupon_rate_pct" in t2:
        filing.coupon_rate_annual = t2["coupon_rate_pct"]["value"]
        sources["coupon_rate_annual"] = "regex_issuer"
    elif t3_coupon_rate is not None:
        filing.coupon_rate_annual = t3_coupon_rate["value"]
        sources["coupon_rate_annual"] = "regex_generic"

    # ===================================================================
    # Derive computed fields
    # ===================================================================

    # threshold_pct from threshold_dollar + initial_price
    if t1_threshold_pct is not None:
        filing.threshold_pct = t1_threshold_pct
        sources["threshold_pct"] = "table"
    elif filing.threshold_dollar and filing.initial_price and filing.initial_price > 0:
        filing.threshold_pct = (filing.threshold_dollar / filing.initial_price) * 100
        sources["threshold_pct"] = "derived"

    # contingent_payment_pct
    if filing.coupon_rate_annual:
        # Assume quarterly payments (4 per year) — common in autocallables
        filing.contingent_payment_pct = filing.coupon_rate_annual / 4
        sources["contingent_payment_pct"] = "derived_from_annual_rate"
    elif filing.coupon_payment_per_period and filing.notional and filing.notional > 0:
        filing.contingent_payment_pct = (
            filing.coupon_payment_per_period / filing.notional
        ) * 100
        sources["contingent_payment_pct"] = "derived_from_payment_and_notional"

    # Default autocall to initial price if not found
    if filing.autocall_level is None and filing.initial_price is not None:
        filing.autocall_level = filing.initial_price
        sources["autocall_level"] = "default_equals_initial"

    filing.sources = sources

    # ===================================================================
    # Cross-validation
    # ===================================================================
    filing.validation_warnings = _cross_validate(filing)

    # ===================================================================
    # Supplemental extraction from structured_products.terms
    # ===================================================================
    try:
        from .terms import extract_product_terms, extract_basket_information, calculate_payoff_type
        terms = extract_product_terms(content, is_html=is_html)
        filing.product_terms = terms

        basket_info = extract_basket_information(text)
        if basket_info:
            filing.product_terms.update(basket_info)

        filing.product_summary = {
            "payoff_type": calculate_payoff_type(terms),
        }
    except Exception as e:
        logger.warning(f"Supplemental terms extraction failed: {e}")

    # ===================================================================
    # Validation via structured_products.validation
    # ===================================================================
    try:
        from .validation import validate_dates, ValidationWarning

        # If we have dates from table extraction, validate them
        # (dates are parsed separately in streamlit_app.py, but we
        # can validate the pricing/maturity dates we may have found)
        date_dict = {}
        pricing_entry = table_fields.get("pricing_date")
        if pricing_entry and pricing_entry["value"].get("date"):
            date_dict["pricing_date"] = pricing_entry["value"]["date"]
        maturity_entry = table_fields.get("maturity_date")
        if maturity_entry and maturity_entry["value"].get("date"):
            date_dict["maturity_date"] = maturity_entry["value"]["date"]

        if date_dict:
            date_warnings = validate_dates(date_dict)
            for w in date_warnings:
                filing.validation_warnings.append(str(w))
    except Exception as e:
        logger.warning(f"Date validation failed: {e}")

    logger.info(
        f"Filing parsed: {sum(1 for v in filing.to_dict().values() if v is not None)} "
        f"fields populated, {len(filing.validation_warnings)} warnings"
    )
    return filing


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------
def _cross_validate(filing: ParsedFiling) -> List[str]:
    """Check extracted values for consistency."""
    warnings: List[str] = []

    # autocall_level >= threshold_dollar
    if (
        filing.autocall_level is not None
        and filing.threshold_dollar is not None
        and filing.autocall_level < filing.threshold_dollar
    ):
        warnings.append(
            f"Autocall level (${filing.autocall_level:.2f}) is below "
            f"threshold (${filing.threshold_dollar:.2f}) — unusual"
        )

    # threshold_pct between 50-100%
    if filing.threshold_pct is not None:
        if not (50 <= filing.threshold_pct <= 100):
            warnings.append(
                f"Threshold percentage ({filing.threshold_pct:.2f}%) is outside "
                f"typical 50-100% range"
            )

    # initial_price sanity
    if filing.initial_price is not None and filing.initial_price <= 0:
        warnings.append(f"Initial price (${filing.initial_price}) is not positive")

    # coupon sanity
    if filing.coupon_rate_annual is not None:
        if filing.coupon_rate_annual > 50:
            warnings.append(
                f"Annual coupon rate ({filing.coupon_rate_annual}%) seems unusually high"
            )

    return warnings
