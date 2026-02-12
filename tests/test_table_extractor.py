"""
Tests for structured_products.table_extractor.

Uses synthetic EDGAR HTML tables mimicking each major issuer's format:
  - Goldman Sachs (2-column label-value)
  - JP Morgan (3-column with spacer)
  - UBS (mixed 2-col and inline bold labels)
  - Morgan Stanley (2-column with compound values)
  - Bank of America (2-column standard)
"""

import pytest

from structured_products.table_extractor import (
    extract_table_key_value_pairs,
    match_labels_to_fields,
    parse_value,
    _looks_like_label,
    _clean_label,
    LABEL_MAP,
)


# ---------------------------------------------------------------------------
# parse_value() tests
# ---------------------------------------------------------------------------
class TestParseValue:
    def test_dollar_amount(self):
        result = parse_value("$237.52")
        assert result["dollar"] == 237.52
        assert result["pct"] is None

    def test_dollar_with_commas(self):
        result = parse_value("$1,000.00")
        assert result["dollar"] == 1000.0

    def test_percentage(self):
        result = parse_value("70.00%")
        assert result["pct"] == 70.0
        assert result["dollar"] is None

    def test_compound_value(self):
        result = parse_value("$166.264 (70.00% of the initial share price)")
        assert result["dollar"] == 166.264
        assert result["pct"] == 70.0
        assert result["compound_pct"] == 70.0

    def test_date(self):
        result = parse_value("January 15, 2025")
        assert result["date"] == "2025-01-15"

    def test_iso_date(self):
        result = parse_value("2025-01-15")
        assert result["date"] == "2025-01-15"

    def test_empty_string(self):
        result = parse_value("")
        assert result["dollar"] is None
        assert result["pct"] is None

    def test_pure_number_no_dollar_sign(self):
        result = parse_value("1000")
        assert result["dollar"] == 1000.0

    def test_percentage_per_annum(self):
        result = parse_value("9.40% per annum")
        assert result["pct"] == 9.4


# ---------------------------------------------------------------------------
# _looks_like_label() tests
# ---------------------------------------------------------------------------
class TestLooksLikeLabel:
    def test_normal_label(self):
        assert _looks_like_label("Initial share price") is True

    def test_label_with_colon(self):
        assert _looks_like_label("Initial share price:") is True

    def test_pure_number(self):
        assert _looks_like_label("$237.52") is False

    def test_pure_percentage(self):
        assert _looks_like_label("70.00%") is False

    def test_empty(self):
        assert _looks_like_label("") is False

    def test_long_paragraph(self):
        assert _looks_like_label("x" * 130) is False

    def test_single_char(self):
        assert _looks_like_label("X") is False


# ---------------------------------------------------------------------------
# _clean_label() tests
# ---------------------------------------------------------------------------
class TestCleanLabel:
    def test_trailing_colon(self):
        assert _clean_label("Initial price:") == "Initial price"

    def test_extra_whitespace(self):
        assert _clean_label("  Initial   share   price  ") == "Initial share price"


# ---------------------------------------------------------------------------
# Synthetic EDGAR HTML fixtures
# ---------------------------------------------------------------------------
GOLDMAN_SACHS_HTML = """
<html><body>
<table>
  <tr><td>Initial share price</td><td>$237.52</td></tr>
  <tr><td>Downside threshold level</td><td>$166.264 (70.00% of the initial share price)</td></tr>
  <tr><td>Contingent quarterly coupon</td><td>$0.5375 per security</td></tr>
  <tr><td>Stated principal amount</td><td>$10.00 per security</td></tr>
  <tr><td>Maturity date</td><td>January 15, 2026</td></tr>
</table>
</body></html>
"""

JP_MORGAN_HTML = """
<html><body>
<table>
  <tr><td>Initial Value</td><td></td><td>$198.35</td></tr>
  <tr><td>Interest Barrier</td><td></td><td>$138.845 (70.00% of Initial Value)</td></tr>
  <tr><td>Contingent Interest Payment</td><td></td><td>$37.50 per $1,000 principal amount</td></tr>
  <tr><td>Stated principal amount</td><td></td><td>$1,000.00</td></tr>
  <tr><td>Pricing date</td><td></td><td>March 10, 2025</td></tr>
</table>
</body></html>
"""

UBS_HTML = """
<html><body>
<table>
  <tr><td><b>Initial price:</b> $150.25</td></tr>
  <tr><td><b>Downside threshold level:</b> $105.175 (70.00%)</td></tr>
  <tr><td><b>Contingent Coupon Rate:</b> 9.40% per annum</td></tr>
  <tr><td><b>Call threshold level:</b> $150.25</td></tr>
  <tr><td><b>Principal Amount:</b> $1,000.00 per security</td></tr>
</table>
</body></html>
"""

MORGAN_STANLEY_HTML = """
<html><body>
<table>
  <tr><td>Initial share price</td><td>$425.50</td></tr>
  <tr><td>Threshold level</td><td>$297.85 (70.00% of the initial share price)</td></tr>
  <tr><td>Redemption threshold</td><td>$425.50</td></tr>
  <tr><td>Contingent Interest Payment</td><td>$8.75 per $1,000 stated principal amount</td></tr>
  <tr><td>Stated principal amount</td><td>$1,000.00</td></tr>
</table>
</body></html>
"""

BANK_OF_AMERICA_HTML = """
<html><body>
<table>
  <tr><td>Initial Value</td><td>$310.00</td></tr>
  <tr><td>Downside threshold level</td><td>$217.00 (70.00% of the Initial Value)</td></tr>
  <tr><td>Call threshold level</td><td>$310.00</td></tr>
  <tr><td>Contingent Interest Payment</td><td>$12.50 per $1,000 principal amount</td></tr>
  <tr><td>Stated principal amount</td><td>$1,000.00</td></tr>
</table>
</body></html>
"""

# A table that should be SKIPPED (example/hypothetical data)
EXAMPLE_TABLE_HTML = """
<html><body>
<table>
  <tr><td>Hypothetical example</td><td>Scenario 1</td></tr>
  <tr><td>Initial share price</td><td>$100.00</td></tr>
  <tr><td>Final share price</td><td>$120.00</td></tr>
  <tr><td>Return</td><td>20%</td></tr>
</table>
<table>
  <tr><td>Initial share price</td><td>$237.52</td></tr>
  <tr><td>Downside threshold level</td><td>$166.264</td></tr>
</table>
</body></html>
"""


# ---------------------------------------------------------------------------
# extract_table_key_value_pairs() tests
# ---------------------------------------------------------------------------
class TestExtractTableKeyValuePairs:
    def test_goldman_sachs_2col(self):
        """Goldman Sachs: simple 2-column label-value pattern."""
        pairs = extract_table_key_value_pairs(GOLDMAN_SACHS_HTML)
        labels = [p["label"] for p in pairs]
        assert "Initial share price" in labels
        assert "Downside threshold level" in labels
        assert "Contingent quarterly coupon" in labels

        # Check value parsing
        initial_pair = next(p for p in pairs if "Initial share price" in p["label"])
        assert initial_pair["value"]["dollar"] == 237.52
        assert initial_pair["pattern"] == "2col"

        # Compound value: threshold has both dollar and pct
        threshold_pair = next(p for p in pairs if "threshold" in p["label"].lower())
        assert threshold_pair["value"]["dollar"] == 166.264
        assert threshold_pair["value"]["compound_pct"] == 70.0

    def test_jp_morgan_3col_spacer(self):
        """JP Morgan: 3-column with empty spacer column."""
        pairs = extract_table_key_value_pairs(JP_MORGAN_HTML)
        labels = [p["label"] for p in pairs]
        assert "Initial Value" in labels

        initial_pair = next(p for p in pairs if "Initial Value" in p["label"])
        assert initial_pair["value"]["dollar"] == 198.35
        assert initial_pair["pattern"] == "3col_spacer"

    def test_ubs_inline_bold(self):
        """UBS: inline <b>Label:</b> Value pattern."""
        pairs = extract_table_key_value_pairs(UBS_HTML)
        labels = [p["label"] for p in pairs]

        # Should find inline-pattern pairs
        assert any("Initial price" in lbl for lbl in labels)

        initial_pair = next(p for p in pairs if "Initial price" in p["label"])
        assert initial_pair["value"]["dollar"] == 150.25
        assert initial_pair["pattern"] == "inline"

        # Coupon rate should be a percentage
        coupon_pair = next(p for p in pairs if "Coupon Rate" in p["label"])
        assert coupon_pair["value"]["pct"] == 9.4

    def test_morgan_stanley_compound(self):
        """Morgan Stanley: 2-column with compound values."""
        pairs = extract_table_key_value_pairs(MORGAN_STANLEY_HTML)
        labels = [p["label"] for p in pairs]
        assert "Initial share price" in labels
        assert "Threshold level" in labels

        threshold_pair = next(p for p in pairs if "Threshold level" in p["label"])
        assert threshold_pair["value"]["dollar"] == 297.85
        assert threshold_pair["value"]["compound_pct"] == 70.0

    def test_bank_of_america(self):
        """Bank of America: standard 2-column."""
        pairs = extract_table_key_value_pairs(BANK_OF_AMERICA_HTML)
        labels = [p["label"] for p in pairs]
        assert "Initial Value" in labels
        assert "Downside threshold level" in labels

    def test_skips_hypothetical_table(self):
        """Should skip tables containing 'hypothetical' but parse the real table."""
        pairs = extract_table_key_value_pairs(EXAMPLE_TABLE_HTML)
        labels = [p["label"] for p in pairs]
        # The hypothetical table ($100.00) should be skipped
        # The real table ($237.52) should be parsed
        initial_pairs = [p for p in pairs if "Initial share price" in p["label"]]
        assert len(initial_pairs) == 1
        assert initial_pairs[0]["value"]["dollar"] == 237.52

    def test_empty_html(self):
        pairs = extract_table_key_value_pairs("<html><body></body></html>")
        assert pairs == []

    def test_no_tables(self):
        pairs = extract_table_key_value_pairs("<html><body><p>No tables here</p></body></html>")
        assert pairs == []


# ---------------------------------------------------------------------------
# match_labels_to_fields() tests
# ---------------------------------------------------------------------------
class TestMatchLabelsToFields:
    def test_goldman_sachs_matching(self):
        pairs = extract_table_key_value_pairs(GOLDMAN_SACHS_HTML)
        matched = match_labels_to_fields(pairs)

        assert "initial_price" in matched
        assert matched["initial_price"]["value"]["dollar"] == 237.52
        assert matched["initial_price"]["source"] == "table"

        assert "threshold_dollar" in matched
        assert matched["threshold_dollar"]["value"]["dollar"] == 166.264

    def test_jp_morgan_matching(self):
        pairs = extract_table_key_value_pairs(JP_MORGAN_HTML)
        matched = match_labels_to_fields(pairs)

        assert "initial_price" in matched
        assert matched["initial_price"]["value"]["dollar"] == 198.35

        assert "threshold_dollar" in matched
        assert matched["threshold_dollar"]["value"]["dollar"] == 138.845

        assert "coupon_payment" in matched

    def test_ubs_matching(self):
        pairs = extract_table_key_value_pairs(UBS_HTML)
        matched = match_labels_to_fields(pairs)

        assert "initial_price" in matched
        assert matched["initial_price"]["value"]["dollar"] == 150.25

        assert "coupon_rate_pct" in matched
        assert matched["coupon_rate_pct"]["value"]["pct"] == 9.4

        assert "autocall_level" in matched
        assert matched["autocall_level"]["value"]["dollar"] == 150.25

    def test_confidence_ordering(self):
        """First pattern in LABEL_MAP list should give higher confidence."""
        pairs = extract_table_key_value_pairs(GOLDMAN_SACHS_HTML)
        matched = match_labels_to_fields(pairs)

        # "initial share price" matches the first pattern in LABEL_MAP["initial_price"]
        assert matched["initial_price"]["confidence"] >= 0.9

    def test_custom_label_map(self):
        """Should work with a custom label map."""
        custom_map = {
            "my_field": [r"initial\s+share\s+price"],
        }
        pairs = extract_table_key_value_pairs(GOLDMAN_SACHS_HTML)
        matched = match_labels_to_fields(pairs, label_map=custom_map)
        assert "my_field" in matched
        assert matched["my_field"]["value"]["dollar"] == 237.52


# ---------------------------------------------------------------------------
# Integration: full pipeline from HTML to matched fields
# ---------------------------------------------------------------------------
class TestFullPipeline:
    def test_goldman_end_to_end(self):
        """Full pipeline: GS HTML -> pairs -> matched fields with all key values."""
        pairs = extract_table_key_value_pairs(GOLDMAN_SACHS_HTML)
        matched = match_labels_to_fields(pairs)

        assert matched["initial_price"]["value"]["dollar"] == 237.52
        assert matched["threshold_dollar"]["value"]["dollar"] == 166.264
        assert matched["threshold_dollar"]["value"]["compound_pct"] == 70.0
        assert "coupon_payment" in matched
        assert "notional" in matched

    def test_all_issuers_extract_initial(self):
        """All issuer formats should successfully extract an initial price."""
        for name, html in [
            ("Goldman Sachs", GOLDMAN_SACHS_HTML),
            ("JP Morgan", JP_MORGAN_HTML),
            ("UBS", UBS_HTML),
            ("Morgan Stanley", MORGAN_STANLEY_HTML),
            ("Bank of America", BANK_OF_AMERICA_HTML),
        ]:
            pairs = extract_table_key_value_pairs(html)
            matched = match_labels_to_fields(pairs)
            assert "initial_price" in matched, f"{name}: failed to extract initial_price"
            assert matched["initial_price"]["value"]["dollar"] is not None, \
                f"{name}: initial_price dollar value is None"
