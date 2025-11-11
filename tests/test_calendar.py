"""
Unit tests for business day calendar module.
"""

import pytest
from datetime import datetime, date
from structured_products.calendar import (
    Market,
    is_weekend,
    is_trading_day,
    next_trading_day,
    previous_trading_day,
    get_settlement_date,
    adjust_to_trading_day,
    is_us_holiday,
    is_uk_holiday,
    infer_market_from_symbol,
    validate_settlement_date,
)


class TestWeekendDetection:
    """Test weekend detection."""

    def test_saturday_is_weekend(self):
        """Test that Saturday is detected as weekend."""
        saturday = datetime(2024, 1, 6)  # Saturday
        assert is_weekend(saturday)

    def test_sunday_is_weekend(self):
        """Test that Sunday is detected as weekend."""
        sunday = datetime(2024, 1, 7)  # Sunday
        assert is_weekend(sunday)

    def test_monday_not_weekend(self):
        """Test that Monday is not weekend."""
        monday = datetime(2024, 1, 8)  # Monday
        assert not is_weekend(monday)

    def test_friday_not_weekend(self):
        """Test that Friday is not weekend."""
        friday = datetime(2024, 1, 5)  # Friday
        assert not is_weekend(friday)


class TestUSHolidays:
    """Test US holiday detection."""

    def test_new_years_day(self):
        """Test New Year's Day detection."""
        new_years = datetime(2024, 1, 1)
        assert is_us_holiday(new_years)

    def test_independence_day(self):
        """Test Independence Day detection."""
        july_4th = datetime(2024, 7, 4)
        assert is_us_holiday(july_4th)

    def test_christmas(self):
        """Test Christmas detection."""
        christmas = datetime(2024, 12, 25)
        assert is_us_holiday(christmas)

    def test_mlk_day(self):
        """Test MLK Day (3rd Monday of January)."""
        mlk_day = datetime(2024, 1, 15)  # 3rd Monday in Jan 2024
        assert is_us_holiday(mlk_day)

    def test_thanksgiving(self):
        """Test Thanksgiving (4th Thursday of November)."""
        thanksgiving = datetime(2024, 11, 28)  # 4th Thursday in Nov 2024
        assert is_us_holiday(thanksgiving)

    def test_regular_day_not_holiday(self):
        """Test that regular day is not a holiday."""
        regular_day = datetime(2024, 3, 15)
        assert not is_us_holiday(regular_day)


class TestUKHolidays:
    """Test UK holiday detection."""

    def test_new_years_day(self):
        """Test New Year's Day detection."""
        new_years = datetime(2024, 1, 1)
        assert is_uk_holiday(new_years)

    def test_christmas(self):
        """Test Christmas detection."""
        christmas = datetime(2024, 12, 25)
        assert is_uk_holiday(christmas)

    def test_boxing_day(self):
        """Test Boxing Day detection."""
        boxing_day = datetime(2024, 12, 26)
        assert is_uk_holiday(boxing_day)

    def test_regular_day_not_holiday(self):
        """Test that regular day is not a holiday."""
        regular_day = datetime(2024, 3, 15)
        assert not is_uk_holiday(regular_day)


class TestTradingDayDetection:
    """Test trading day detection for different markets."""

    def test_weekday_is_trading_day_nyse(self):
        """Test that weekday is trading day for NYSE."""
        monday = datetime(2024, 1, 8)  # Regular Monday
        assert is_trading_day(monday, Market.NYSE)

    def test_saturday_not_trading_day(self):
        """Test that Saturday is not a trading day."""
        saturday = datetime(2024, 1, 6)
        assert not is_trading_day(saturday, Market.NYSE)

    def test_sunday_not_trading_day(self):
        """Test that Sunday is not a trading day."""
        sunday = datetime(2024, 1, 7)
        assert not is_trading_day(sunday, Market.NYSE)

    def test_us_holiday_not_trading_day(self):
        """Test that US holiday is not a trading day for NYSE."""
        july_4th = datetime(2024, 7, 4)
        assert not is_trading_day(july_4th, Market.NYSE)

    def test_weekday_is_trading_day_lse(self):
        """Test that weekday is trading day for LSE."""
        monday = datetime(2024, 1, 8)  # Regular Monday
        assert is_trading_day(monday, Market.LSE)

    def test_uk_holiday_not_trading_day_lse(self):
        """Test that UK holiday is not a trading day for LSE."""
        boxing_day = datetime(2024, 12, 26)
        assert not is_trading_day(boxing_day, Market.LSE)

    def test_generic_market_ignores_holidays(self):
        """Test that GENERIC market only considers weekends."""
        july_4th = datetime(2024, 7, 4)  # US holiday, but Thursday
        assert is_trading_day(july_4th, Market.GENERIC)


class TestNextTradingDay:
    """Test next trading day calculation."""

    def test_next_trading_day_from_friday(self):
        """Test next trading day from Friday is Monday."""
        friday = datetime(2024, 1, 5)
        next_day = next_trading_day(friday, Market.NYSE)
        assert next_day.weekday() == 0  # Monday
        assert next_day == datetime(2024, 1, 8)

    def test_next_trading_day_from_weekday(self):
        """Test next trading day from Wednesday is Thursday."""
        wednesday = datetime(2024, 1, 10)
        next_day = next_trading_day(wednesday, Market.NYSE)
        assert next_day == datetime(2024, 1, 11)

    def test_next_trading_day_skips_holiday(self):
        """Test next trading day skips holiday."""
        # Day before Independence Day
        july_3rd = datetime(2024, 7, 3)
        next_day = next_trading_day(july_3rd, Market.NYSE)
        # Should skip July 4th (Thursday) to Friday July 5th
        assert next_day == datetime(2024, 7, 5)


class TestPreviousTradingDay:
    """Test previous trading day calculation."""

    def test_previous_trading_day_from_monday(self):
        """Test previous trading day from Monday is Friday."""
        monday = datetime(2024, 1, 8)
        prev_day = previous_trading_day(monday, Market.NYSE)
        assert prev_day.weekday() == 4  # Friday
        assert prev_day == datetime(2024, 1, 5)

    def test_previous_trading_day_from_weekday(self):
        """Test previous trading day from Thursday is Wednesday."""
        thursday = datetime(2024, 1, 11)
        prev_day = previous_trading_day(thursday, Market.NYSE)
        assert prev_day == datetime(2024, 1, 10)


class TestSettlementDate:
    """Test settlement date calculation."""

    def test_t_plus_2_from_monday(self):
        """Test T+2 settlement from Monday."""
        monday = datetime(2024, 1, 8)
        settlement = get_settlement_date(monday, settlement_days=2, market=Market.NYSE)
        # Monday + 2 trading days = Wednesday
        assert settlement == datetime(2024, 1, 10)

    def test_t_plus_2_from_thursday(self):
        """Test T+2 settlement from Thursday."""
        thursday = datetime(2024, 1, 11)
        settlement = get_settlement_date(thursday, settlement_days=2, market=Market.NYSE)
        # Thursday + 2 trading days = Monday (skips weekend)
        assert settlement == datetime(2024, 1, 15)

    def test_t_plus_1(self):
        """Test T+1 settlement."""
        monday = datetime(2024, 1, 8)
        settlement = get_settlement_date(monday, settlement_days=1, market=Market.NYSE)
        assert settlement == datetime(2024, 1, 9)

    def test_t_plus_0(self):
        """Test T+0 (same day settlement)."""
        monday = datetime(2024, 1, 8)
        settlement = get_settlement_date(monday, settlement_days=0, market=Market.NYSE)
        assert settlement == monday


class TestAdjustToTradingDay:
    """Test date adjustment to trading days."""

    def test_following_convention_from_saturday(self):
        """Test FOLLOWING convention from Saturday."""
        saturday = datetime(2024, 1, 6)
        adjusted = adjust_to_trading_day(saturday, Market.NYSE, convention="following")
        assert adjusted == datetime(2024, 1, 8)  # Next Monday

    def test_preceding_convention_from_saturday(self):
        """Test PRECEDING convention from Saturday."""
        saturday = datetime(2024, 1, 6)
        adjusted = adjust_to_trading_day(saturday, Market.NYSE, convention="preceding")
        assert adjusted == datetime(2024, 1, 5)  # Previous Friday

    def test_modified_following_convention(self):
        """Test MODIFIED_FOLLOWING convention."""
        # Last Saturday of month
        saturday = datetime(2024, 1, 27)
        adjusted = adjust_to_trading_day(saturday, Market.NYSE, convention="modified_following")
        # Should go to next Monday (Jan 29), same month
        assert adjusted == datetime(2024, 1, 29)

    def test_nearest_convention_saturday(self):
        """Test NEAREST convention from Saturday."""
        saturday = datetime(2024, 1, 6)
        adjusted = adjust_to_trading_day(saturday, Market.NYSE, convention="nearest")
        # Saturday is closer to Friday than Monday
        assert adjusted == datetime(2024, 1, 5)  # Friday

    def test_nearest_convention_sunday(self):
        """Test NEAREST convention from Sunday."""
        sunday = datetime(2024, 1, 7)
        adjusted = adjust_to_trading_day(sunday, Market.NYSE, convention="nearest")
        # Sunday is closer to Monday than Friday
        assert adjusted == datetime(2024, 1, 8)  # Monday

    def test_trading_day_unchanged(self):
        """Test that trading day is unchanged."""
        monday = datetime(2024, 1, 8)
        adjusted = adjust_to_trading_day(monday, Market.NYSE)
        assert adjusted == monday


class TestMarketInference:
    """Test market inference from symbols."""

    def test_sp500_infers_nyse(self):
        """Test S&P 500 symbol infers NYSE."""
        market = infer_market_from_symbol("^GSPC")
        assert market == Market.NYSE

    def test_ftse_infers_lse(self):
        """Test FTSE symbol infers LSE."""
        market = infer_market_from_symbol("^FTSE")
        assert market == Market.LSE

    def test_nikkei_infers_tse(self):
        """Test Nikkei symbol infers TSE."""
        market = infer_market_from_symbol("^N225")
        assert market == Market.TSE

    def test_hang_seng_infers_hkex(self):
        """Test Hang Seng symbol infers HKEX."""
        market = infer_market_from_symbol("^HSI")
        assert market == Market.HKEX

    def test_shanghai_infers_sse(self):
        """Test Shanghai Composite infers SSE."""
        market = infer_market_from_symbol("000001.SS")
        assert market == Market.SSE

    def test_unknown_symbol_generic(self):
        """Test unknown symbol infers GENERIC."""
        market = infer_market_from_symbol("UNKNOWN")
        assert market == Market.GENERIC


class TestSettlementValidation:
    """Test settlement date validation."""

    def test_valid_t_plus_2_settlement(self):
        """Test valid T+2 settlement is accepted."""
        trade_date = datetime(2024, 1, 8)  # Monday
        settlement_date = datetime(2024, 1, 10)  # Wednesday
        result = validate_settlement_date(trade_date, settlement_date, 2, Market.NYSE)
        assert result["is_valid"]
        assert result["expected_settlement"] == settlement_date

    def test_invalid_settlement_too_early(self):
        """Test invalid settlement (too early) is rejected."""
        trade_date = datetime(2024, 1, 8)  # Monday
        settlement_date = datetime(2024, 1, 9)  # Tuesday (should be Wed)
        result = validate_settlement_date(trade_date, settlement_date, 2, Market.NYSE)
        assert not result["is_valid"]
        assert "error" in result

    def test_invalid_settlement_on_weekend(self):
        """Test invalid settlement on weekend is rejected."""
        trade_date = datetime(2024, 1, 8)  # Monday
        settlement_date = datetime(2024, 1, 13)  # Saturday
        result = validate_settlement_date(trade_date, settlement_date, 2, Market.NYSE)
        assert not result["is_valid"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
