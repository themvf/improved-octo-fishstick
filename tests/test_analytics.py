"""
Unit tests for analytics module.
"""

import pytest
import math
from structured_products.analytics import (
    calculate_log_returns,
    calculate_realized_volatility,
    calculate_rolling_volatilities,
    calculate_greeks,
    estimate_time_to_maturity,
    analyze_structured_product_greeks,
    calculate_breakeven_levels,
    calculate_risk_metrics,
    generate_analytics_summary,
    black_scholes_call_price,
    black_scholes_put_price
)


class TestLogReturns:
    """Test logarithmic returns calculation."""

    def test_calculate_log_returns_simple(self):
        """Test log returns with simple price series."""
        prices = [100, 105, 110]
        returns = calculate_log_returns(prices)

        assert len(returns) == 2
        assert returns[0] == pytest.approx(math.log(105/100), rel=1e-6)
        assert returns[1] == pytest.approx(math.log(110/105), rel=1e-6)

    def test_calculate_log_returns_single_price(self):
        """Test that single price returns empty list."""
        prices = [100]
        returns = calculate_log_returns(prices)
        assert returns == []

    def test_calculate_log_returns_empty(self):
        """Test that empty prices returns empty list."""
        prices = []
        returns = calculate_log_returns(prices)
        assert returns == []

    def test_calculate_log_returns_with_zero(self):
        """Test that zero prices are skipped."""
        prices = [100, 0, 105]
        returns = calculate_log_returns(prices)
        # Should skip the 0 price
        assert len(returns) == 0  # Can't calculate log(105/0)


class TestRealizedVolatility:
    """Test realized volatility calculations."""

    def test_calculate_realized_volatility(self):
        """Test volatility calculation with known prices."""
        # Simple test case
        prices = [100, 102, 101, 103, 105, 104, 106]
        result = calculate_realized_volatility(prices, periods=252)

        assert result["realized_vol_annualized"] is not None
        assert result["realized_vol_daily"] is not None
        assert result["sample_size"] == 6  # 7 prices = 6 returns

    def test_calculate_realized_volatility_insufficient_data(self):
        """Test with insufficient data."""
        prices = [100]
        result = calculate_realized_volatility(prices, periods=252)

        assert result["realized_vol_annualized"] is None
        assert result["realized_vol_daily"] is None
        assert result["sample_size"] == 1

    def test_calculate_realized_volatility_empty(self):
        """Test with empty prices."""
        prices = []
        result = calculate_realized_volatility(prices, periods=252)

        assert result["realized_vol_annualized"] is None
        assert result["sample_size"] == 0

    def test_annualization_factor(self):
        """Test that annualization works correctly."""
        # Daily prices with known volatility
        prices = [100, 101, 99, 102, 98, 103, 97]

        # Calculate with daily annualization
        result_daily = calculate_realized_volatility(prices, periods=252)
        # Calculate with weekly annualization
        result_weekly = calculate_realized_volatility(prices, periods=52)

        # Weekly vol should be lower than daily vol (same data, different annualization)
        assert result_weekly["realized_vol_annualized"] < result_daily["realized_vol_annualized"]


class TestRollingVolatilities:
    """Test rolling volatility calculations."""

    def test_calculate_rolling_volatilities(self):
        """Test rolling volatilities with various windows."""
        # Generate 300 prices
        prices = [100 + i * 0.1 for i in range(300)]

        windows = [20, 60, 252]
        result = calculate_rolling_volatilities(prices, windows=windows)

        assert "vol_20d" in result
        assert "vol_60d" in result
        assert "vol_252d" in result
        assert all(result[f"vol_{w}d"] is not None for w in windows)

    def test_calculate_rolling_volatilities_insufficient_data(self):
        """Test with insufficient data for large windows."""
        prices = [100 + i for i in range(50)]

        windows = [20, 60, 252]
        result = calculate_rolling_volatilities(prices, windows=windows)

        assert result["vol_20d"] is not None  # Have enough
        assert result["vol_60d"] is None  # Not enough (need 61)
        assert result["vol_252d"] is None  # Not enough


class TestBlackScholesPrice:
    """Test Black-Scholes option pricing."""

    def test_call_price_at_the_money(self):
        """Test ATM call price."""
        price = black_scholes_call_price(
            S=100, K=100, T=1.0, r=0.05, sigma=0.2
        )
        assert price > 0
        assert price < 100  # Call can't be worth more than stock

    def test_call_price_deep_in_the_money(self):
        """Test deep ITM call."""
        price = black_scholes_call_price(
            S=100, K=50, T=1.0, r=0.05, sigma=0.2
        )
        # Deep ITM call should be close to intrinsic value (S - K)
        assert price > 50  # At least intrinsic value
        assert price < 100

    def test_call_price_at_expiration(self):
        """Test call at expiration."""
        price = black_scholes_call_price(
            S=105, K=100, T=0.0, r=0.05, sigma=0.2
        )
        # At expiration, option worth intrinsic value
        assert price == 5.0

    def test_put_price_at_the_money(self):
        """Test ATM put price."""
        price = black_scholes_put_price(
            S=100, K=100, T=1.0, r=0.05, sigma=0.2
        )
        assert price > 0
        assert price < 100

    def test_put_price_deep_in_the_money(self):
        """Test deep ITM put."""
        price = black_scholes_put_price(
            S=50, K=100, T=1.0, r=0.05, sigma=0.2
        )
        # Deep ITM put should be close to intrinsic value (K - S)
        assert price > 50
        assert price < 100

    def test_put_price_at_expiration(self):
        """Test put at expiration."""
        price = black_scholes_put_price(
            S=95, K=100, T=0.0, r=0.05, sigma=0.2
        )
        # At expiration, option worth intrinsic value
        assert price == 5.0


class TestGreeks:
    """Test Greeks calculations."""

    def test_calculate_greeks_call(self):
        """Test Greeks for call option."""
        greeks = calculate_greeks(
            S=100, K=100, T=1.0, r=0.05, sigma=0.2, option_type="call"
        )

        assert "delta" in greeks
        assert "gamma" in greeks
        assert "theta" in greeks
        assert "vega" in greeks
        assert "rho" in greeks

        # ATM call delta should be around 0.5
        assert 0.4 < greeks["delta"] < 0.6

        # Gamma should be positive
        assert greeks["gamma"] > 0

        # Theta should be negative (time decay)
        assert greeks["theta"] < 0

        # Vega should be positive
        assert greeks["vega"] > 0

    def test_calculate_greeks_put(self):
        """Test Greeks for put option."""
        greeks = calculate_greeks(
            S=100, K=100, T=1.0, r=0.05, sigma=0.2, option_type="put"
        )

        # ATM put delta should be around -0.5
        assert -0.6 < greeks["delta"] < -0.4

        # Gamma should be positive (same as call)
        assert greeks["gamma"] > 0

        # Theta should be negative
        assert greeks["theta"] < 0

    def test_greeks_at_expiration(self):
        """Test Greeks at expiration."""
        # ITM call at expiration
        greeks = calculate_greeks(
            S=105, K=100, T=0.0, r=0.05, sigma=0.2, option_type="call"
        )

        assert greeks["delta"] == 1.0  # ITM call
        assert greeks["gamma"] == 0.0
        assert greeks["theta"] == 0.0
        assert greeks["vega"] == 0.0

    def test_greeks_zero_volatility(self):
        """Test Greeks with zero volatility."""
        greeks = calculate_greeks(
            S=100, K=100, T=1.0, r=0.05, sigma=0.0, option_type="call"
        )

        # Should return None values
        assert all(v is None for v in greeks.values())

    def test_greeks_itm_call(self):
        """Test Greeks for ITM call."""
        greeks = calculate_greeks(
            S=110, K=100, T=1.0, r=0.05, sigma=0.2, option_type="call"
        )

        # ITM call delta should be > 0.5
        assert greeks["delta"] > 0.6


class TestTimeToMaturity:
    """Test time to maturity calculations."""

    def test_estimate_time_to_maturity(self):
        """Test time to maturity calculation."""
        # 1 year from pricing date
        T = estimate_time_to_maturity(
            maturity_date_str="2025-01-01",
            pricing_date_str="2024-01-01"
        )
        assert T == pytest.approx(1.0, rel=0.01)

    def test_estimate_time_to_maturity_half_year(self):
        """Test 6 month time to maturity."""
        T = estimate_time_to_maturity(
            maturity_date_str="2024-07-01",
            pricing_date_str="2024-01-01"
        )
        # 182 days / 365 ≈ 0.4986
        assert T == pytest.approx(0.4986, rel=0.01)

    def test_estimate_time_to_maturity_past(self):
        """Test maturity in the past."""
        T = estimate_time_to_maturity(
            maturity_date_str="2020-01-01",
            pricing_date_str="2024-01-01"
        )
        assert T == 0.0


class TestStructuredProductGreeks:
    """Test structured product Greeks analysis."""

    def test_analyze_product_with_barrier(self):
        """Test analysis of product with barrier."""
        product_terms = {
            "barrier": {"value": 10.0, "unit": "%"},
            "participation_rate": {"value": 100.0, "unit": "%"}
        }

        result = analyze_structured_product_greeks(
            product_terms=product_terms,
            spot=100.0,
            pricing_date="2024-01-01",
            maturity_date="2025-01-01",
            volatility=0.20,
            risk_free_rate=0.05
        )

        assert "time_to_maturity_years" in result
        assert "barrier_analysis" in result
        assert result["barrier_analysis"]["barrier_level"] == 90.0
        assert "barrier_greeks" in result["barrier_analysis"]

    def test_analyze_product_with_cap(self):
        """Test analysis of product with cap."""
        product_terms = {
            "cap": {"value": 15.0, "unit": "%"},
            "participation_rate": {"value": 100.0, "unit": "%"}
        }

        result = analyze_structured_product_greeks(
            product_terms=product_terms,
            spot=100.0,
            pricing_date="2024-01-01",
            maturity_date="2025-01-01",
            volatility=0.20
        )

        assert "cap_analysis" in result
        assert result["cap_analysis"]["cap_level"] == 115.0
        assert "cap_greeks" in result["cap_analysis"]

    def test_analyze_product_atm_greeks(self):
        """Test ATM Greeks are always calculated."""
        product_terms = {}

        result = analyze_structured_product_greeks(
            product_terms=product_terms,
            spot=100.0,
            pricing_date="2024-01-01",
            maturity_date="2025-01-01",
            volatility=0.20
        )

        assert "atm_greeks" in result
        assert "effective_delta" in result


class TestBreakevenLevels:
    """Test breakeven level calculations."""

    def test_calculate_breakeven_with_buffer(self):
        """Test breakeven calculation with buffer."""
        product_terms = {
            "buffer": {"value": 10.0, "unit": "%"}
        }

        result = calculate_breakeven_levels(product_terms, spot=100.0)

        assert "buffer_level" in result["levels"]
        assert result["levels"]["buffer_level"]["price"] == 90.0
        assert result["levels"]["buffer_level"]["percentage"] == -10.0

    def test_calculate_breakeven_with_cap(self):
        """Test breakeven calculation with cap."""
        product_terms = {
            "cap": {"value": 20.0, "unit": "%"}
        }

        result = calculate_breakeven_levels(product_terms, spot=100.0)

        assert "cap_level" in result["levels"]
        assert result["levels"]["cap_level"]["price"] == 120.0
        assert result["levels"]["cap_level"]["percentage"] == 20.0

    def test_calculate_breakeven_with_barrier(self):
        """Test breakeven calculation with barrier."""
        product_terms = {
            "barrier": {"value": 15.0, "unit": "%"}
        }

        result = calculate_breakeven_levels(product_terms, spot=100.0)

        assert "barrier_level" in result["levels"]
        assert result["levels"]["barrier_level"]["price"] == 85.0


class TestRiskMetrics:
    """Test risk metrics calculations."""

    def test_calculate_risk_metrics(self):
        """Test risk metrics calculation."""
        # Generate some sample prices
        prices = [100, 102, 101, 103, 102, 105, 104, 106]

        result = calculate_risk_metrics(prices)

        assert "sharpe_ratio" in result
        assert "max_drawdown" in result
        assert "value_at_risk_95" in result
        assert "value_at_risk_99" in result
        assert "mean_daily_return" in result
        assert "std_daily_return" in result

    def test_max_drawdown(self):
        """Test maximum drawdown calculation."""
        # Prices with known drawdown
        prices = [100, 110, 120, 90, 100]  # Peak at 120, trough at 90

        result = calculate_risk_metrics(prices)

        # Drawdown should be negative
        assert result["max_drawdown"] < 0

    def test_risk_metrics_insufficient_data(self):
        """Test with insufficient data."""
        prices = [100]
        result = calculate_risk_metrics(prices)

        assert result["sharpe_ratio"] is None


class TestAnalyticsSummary:
    """Test full analytics summary generation."""

    def test_generate_analytics_summary(self):
        """Test complete analytics summary."""
        prices_data = {
            "symbol": "^GSPC",
            "data": {
                "2024-01-01": {"adj_close": 4700.0},
                "2024-01-02": {"adj_close": 4710.0},
                "2024-01-03": {"adj_close": 4705.0},
                "2024-01-04": {"adj_close": 4720.0},
                "2024-01-05": {"adj_close": 4715.0},
            }
        }

        result = generate_analytics_summary(prices_data, volatility_windows=[3])

        assert "volatility" in result
        assert "risk_metrics" in result
        assert "current_price" in result
        assert result["current_price"] == 4715.0

    def test_generate_analytics_with_product_terms(self):
        """Test analytics with product terms."""
        prices_data = {
            "symbol": "^GSPC",
            "data": {
                f"2024-01-{i:02d}": {"adj_close": 4700.0 + i * 10}
                for i in range(1, 31)
            }
        }

        product_terms = {
            "barrier": {"value": 10.0, "unit": "%"},
            "cap": {"value": 15.0, "unit": "%"}
        }

        dates = {
            "pricing_date": "2024-01-01",
            "maturity_date": "2025-01-01"
        }

        result = generate_analytics_summary(
            prices_data,
            product_terms=product_terms,
            dates=dates,
            risk_free_rate=0.05
        )

        assert "greeks" in result
        assert "breakeven_levels" in result

    def test_generate_analytics_no_data(self):
        """Test with no price data."""
        prices_data = {
            "symbol": "^GSPC",
            "data": {}
        }

        result = generate_analytics_summary(prices_data)

        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
