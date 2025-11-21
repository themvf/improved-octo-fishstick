"""
Financial analytics for structured products.

Provides:
- Historical volatility calculations
- Black-Scholes option Greeks
- Product-specific sensitivity analysis
- Risk metrics and breakeven calculations
"""

import math
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from scipy import stats
import numpy as np

logger = logging.getLogger(__name__)


def calculate_log_returns(prices: List[float]) -> List[float]:
    """
    Calculate logarithmic returns from price series.

    Args:
        prices: List of prices (chronologically ordered)

    Returns:
        List of log returns
    """
    if len(prices) < 2:
        return []

    returns = []
    for i in range(1, len(prices)):
        if prices[i] > 0 and prices[i-1] > 0:
            returns.append(math.log(prices[i] / prices[i-1]))

    return returns


def calculate_realized_volatility(
    prices: List[float],
    periods: int = 252,
    method: str = "close_to_close"
) -> Dict[str, float]:
    """
    Calculate historical volatility metrics.

    Args:
        prices: List of prices (chronologically ordered, most recent last)
        periods: Annualization factor (252 for daily, 52 for weekly, 12 for monthly)
        method: Calculation method ('close_to_close', 'parkinson', 'garman_klass')

    Returns:
        Dictionary with volatility metrics:
        - realized_vol_annualized: Annualized volatility
        - realized_vol_daily: Daily volatility
        - sample_size: Number of returns used
    """
    if len(prices) < 2:
        logger.warning("Insufficient price data for volatility calculation")
        return {
            "realized_vol_annualized": None,
            "realized_vol_daily": None,
            "sample_size": len(prices)
        }

    # Calculate log returns
    returns = calculate_log_returns(prices)

    if not returns:
        return {
            "realized_vol_annualized": None,
            "realized_vol_daily": None,
            "sample_size": 0
        }

    # Calculate standard deviation of returns
    std_dev = np.std(returns, ddof=1)  # Sample standard deviation

    # Annualize
    annualized_vol = std_dev * math.sqrt(periods)

    return {
        "realized_vol_annualized": round(annualized_vol, 4),
        "realized_vol_daily": round(std_dev, 6),
        "sample_size": len(returns),
        "mean_return_daily": round(np.mean(returns), 6) if returns else None
    }


def calculate_rolling_volatilities(
    prices: List[float],
    windows: List[int] = [20, 60, 252],
    periods: int = 252
) -> Dict[str, Optional[float]]:
    """
    Calculate volatility over multiple rolling windows.

    Args:
        prices: List of prices (chronologically ordered, most recent last)
        windows: List of window sizes (in number of prices)
        periods: Annualization factor

    Returns:
        Dictionary mapping window names to volatilities
    """
    result = {}

    for window in windows:
        key = f"vol_{window}d"
        if len(prices) >= window + 1:  # Need window+1 prices for window returns
            window_prices = prices[-window-1:]
            vol_data = calculate_realized_volatility(window_prices, periods)
            result[key] = vol_data["realized_vol_annualized"]
        else:
            result[key] = None
            logger.warning(f"Insufficient data for {window}-day volatility")

    return result


def black_scholes_call_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float
) -> float:
    """
    Calculate Black-Scholes call option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to maturity (years)
        r: Risk-free rate
        sigma: Volatility (annualized)

    Returns:
        Call option price
    """
    if T <= 0 or sigma <= 0:
        return max(S - K, 0)  # Intrinsic value

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    call_price = S * stats.norm.cdf(d1) - K * math.exp(-r * T) * stats.norm.cdf(d2)

    return call_price


def black_scholes_put_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float
) -> float:
    """
    Calculate Black-Scholes put option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to maturity (years)
        r: Risk-free rate
        sigma: Volatility (annualized)

    Returns:
        Put option price
    """
    if T <= 0 or sigma <= 0:
        return max(K - S, 0)  # Intrinsic value

    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    put_price = K * math.exp(-r * T) * stats.norm.cdf(-d2) - S * stats.norm.cdf(-d1)

    return put_price


def calculate_greeks(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call"
) -> Dict[str, float]:
    """
    Calculate Black-Scholes Greeks.

    Args:
        S: Spot price
        K: Strike price
        T: Time to maturity (years)
        r: Risk-free rate (annualized)
        sigma: Volatility (annualized)
        option_type: 'call' or 'put'

    Returns:
        Dictionary with Greeks:
        - delta: Sensitivity to underlying price (dV/dS)
        - gamma: Rate of delta change (d²V/dS²)
        - theta: Time decay per day (dV/dt per day)
        - vega: Sensitivity to 1% volatility change (dV/dσ per 0.01)
        - rho: Sensitivity to 1% rate change (dV/dr per 0.01)
    """
    if T <= 0:
        # At expiration
        if option_type == "call":
            delta = 1.0 if S > K else 0.0
        else:
            delta = -1.0 if S < K else 0.0

        return {
            "delta": delta,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0
        }

    if sigma <= 0:
        logger.warning("Volatility must be positive for Greeks calculation")
        return {
            "delta": None,
            "gamma": None,
            "theta": None,
            "vega": None,
            "rho": None
        }

    # Calculate d1 and d2
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)

    # Standard normal PDF and CDF
    pdf_d1 = stats.norm.pdf(d1)

    # Delta
    if option_type == "call":
        delta = stats.norm.cdf(d1)
    else:
        delta = stats.norm.cdf(d1) - 1

    # Gamma (same for call and put)
    gamma = pdf_d1 / (S * sigma * math.sqrt(T))

    # Vega (same for call and put) - per 1% change in volatility
    vega = S * pdf_d1 * math.sqrt(T) / 100

    # Theta - per day
    if option_type == "call":
        theta = (-(S * pdf_d1 * sigma) / (2 * math.sqrt(T))
                 - r * K * math.exp(-r * T) * stats.norm.cdf(d2)) / 365
    else:
        theta = (-(S * pdf_d1 * sigma) / (2 * math.sqrt(T))
                 + r * K * math.exp(-r * T) * stats.norm.cdf(-d2)) / 365

    # Rho - per 1% change in interest rate
    if option_type == "call":
        rho = K * T * math.exp(-r * T) * stats.norm.cdf(d2) / 100
    else:
        rho = -K * T * math.exp(-r * T) * stats.norm.cdf(-d2) / 100

    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 4),
        "vega": round(vega, 4),
        "rho": round(rho, 4)
    }


def estimate_time_to_maturity(
    maturity_date_str: str,
    pricing_date_str: Optional[str] = None
) -> float:
    """
    Calculate time to maturity in years.

    Args:
        maturity_date_str: Maturity date in YYYY-MM-DD format
        pricing_date_str: Pricing date in YYYY-MM-DD format (default: today)

    Returns:
        Time to maturity in years (using 365-day convention)
    """
    try:
        maturity_date = datetime.strptime(maturity_date_str, "%Y-%m-%d")

        if pricing_date_str:
            pricing_date = datetime.strptime(pricing_date_str, "%Y-%m-%d")
        else:
            pricing_date = datetime.now()

        days_to_maturity = (maturity_date - pricing_date).days

        if days_to_maturity < 0:
            logger.warning("Maturity date is in the past")
            return 0.0

        return days_to_maturity / 365.0

    except Exception as e:
        logger.error(f"Error calculating time to maturity: {e}")
        return None


def analyze_structured_product_greeks(
    product_terms: Dict[str, Any],
    spot: float,
    pricing_date: str,
    maturity_date: str,
    volatility: float,
    risk_free_rate: float = 0.05
) -> Dict[str, Any]:
    """
    Analyze Greeks for structured product components.

    Args:
        product_terms: Product terms dictionary from terms.py
        spot: Current spot price
        pricing_date: Pricing date (YYYY-MM-DD)
        maturity_date: Maturity date (YYYY-MM-DD)
        volatility: Implied or historical volatility
        risk_free_rate: Risk-free rate (annualized)

    Returns:
        Dictionary with product-specific Greeks and sensitivity analysis
    """
    T = estimate_time_to_maturity(maturity_date, pricing_date)

    if T is None or T <= 0:
        logger.warning("Cannot calculate Greeks: invalid time to maturity")
        return {
            "error": "Invalid time to maturity",
            "time_to_maturity": T
        }

    result = {
        "time_to_maturity_years": round(T, 4),
        "time_to_maturity_days": round(T * 365, 0),
        "spot_price": spot,
        "volatility": volatility,
        "risk_free_rate": risk_free_rate
    }

    # Extract product terms
    participation_rate = 1.0
    if "participation_rate" in product_terms:
        participation_rate = product_terms["participation_rate"].get("value", 100.0) / 100.0

    # Barrier analysis
    if "barrier" in product_terms:
        barrier_pct = product_terms["barrier"].get("value", 0)
        barrier_level = spot * (1 - barrier_pct / 100.0)

        # Calculate put Greeks at barrier level
        barrier_greeks = calculate_greeks(
            S=spot,
            K=barrier_level,
            T=T,
            r=risk_free_rate,
            sigma=volatility,
            option_type="put"
        )

        result["barrier_analysis"] = {
            "barrier_level": round(barrier_level, 2),
            "barrier_percentage": barrier_pct,
            "distance_to_barrier": round((spot - barrier_level) / spot * 100, 2),
            "barrier_greeks": barrier_greeks
        }

    # Cap analysis
    if "cap" in product_terms:
        cap_pct = product_terms["cap"].get("value", 0)
        cap_level = spot * (1 + cap_pct / 100.0)

        # Calculate call Greeks at cap level
        cap_greeks = calculate_greeks(
            S=spot,
            K=cap_level,
            T=T,
            r=risk_free_rate,
            sigma=volatility,
            option_type="call"
        )

        result["cap_analysis"] = {
            "cap_level": round(cap_level, 2),
            "cap_percentage": cap_pct,
            "distance_to_cap": round((cap_level - spot) / spot * 100, 2),
            "cap_greeks": cap_greeks
        }

    # At-the-money Greeks (reference point)
    atm_call_greeks = calculate_greeks(
        S=spot,
        K=spot,
        T=T,
        r=risk_free_rate,
        sigma=volatility,
        option_type="call"
    )

    result["atm_greeks"] = atm_call_greeks

    # Participation-adjusted Greeks
    result["effective_delta"] = round(
        atm_call_greeks["delta"] * participation_rate, 4
    )

    return result


def calculate_breakeven_levels(
    product_terms: Dict[str, Any],
    spot: float
) -> Dict[str, Any]:
    """
    Calculate breakeven and critical price levels for structured product.

    Args:
        product_terms: Product terms dictionary from terms.py
        spot: Current spot price

    Returns:
        Dictionary with breakeven levels and critical points
    """
    result = {
        "spot_price": spot,
        "levels": {}
    }

    # Extract terms
    participation = 1.0
    if "participation_rate" in product_terms:
        participation = product_terms["participation_rate"].get("value", 100.0) / 100.0

    buffer = 0.0
    if "buffer" in product_terms:
        buffer = product_terms["buffer"].get("value", 0.0)

    barrier = 0.0
    if "barrier" in product_terms:
        barrier = product_terms["barrier"].get("value", 0.0)

    cap = None
    if "cap" in product_terms:
        cap = product_terms["cap"].get("value", None)

    knock_in = None
    if "knock_in" in product_terms:
        knock_in = product_terms["knock_in"].get("value", None)

    # Calculate levels
    if buffer > 0:
        result["levels"]["buffer_level"] = {
            "price": round(spot * (1 - buffer / 100.0), 2),
            "percentage": -buffer,
            "description": "Downside protection ends here"
        }

    if barrier > 0:
        result["levels"]["barrier_level"] = {
            "price": round(spot * (1 - barrier / 100.0), 2),
            "percentage": -barrier,
            "description": "Downside participation begins here"
        }

    if knock_in is not None:
        result["levels"]["knock_in_level"] = {
            "price": round(spot * (1 - knock_in / 100.0), 2),
            "percentage": -knock_in,
            "description": "Knock-in barrier activation"
        }

    if cap is not None:
        result["levels"]["cap_level"] = {
            "price": round(spot * (1 + cap / 100.0), 2),
            "percentage": cap,
            "description": "Maximum return level"
        }

    # Breakeven for return
    if participation != 1.0:
        # Breakeven where participation-adjusted return = 0
        result["levels"]["participation_breakeven"] = {
            "price": round(spot, 2),
            "percentage": 0.0,
            "description": f"With {participation*100}% participation"
        }

    return result


def calculate_risk_metrics(
    prices: List[float],
    returns_data: Optional[List[float]] = None
) -> Dict[str, float]:
    """
    Calculate risk metrics from price/return series.

    Args:
        prices: List of prices
        returns_data: Optional pre-calculated returns

    Returns:
        Dictionary with risk metrics:
        - sharpe_ratio: Risk-adjusted return (assuming rf=0)
        - max_drawdown: Maximum peak-to-trough decline
        - value_at_risk_95: 95% VaR (daily)
        - value_at_risk_99: 99% VaR (daily)
    """
    if returns_data is None:
        returns_data = calculate_log_returns(prices)

    if not returns_data:
        return {
            "sharpe_ratio": None,
            "max_drawdown": None,
            "value_at_risk_95": None,
            "value_at_risk_99": None
        }

    # Sharpe ratio (annualized, assuming rf=0)
    mean_return = np.mean(returns_data)
    std_return = np.std(returns_data, ddof=1)

    if std_return > 0:
        sharpe_ratio = (mean_return / std_return) * math.sqrt(252)
    else:
        sharpe_ratio = None

    # Maximum drawdown
    cumulative = np.cumprod(1 + np.array(returns_data))
    running_max = np.maximum.accumulate(cumulative)
    drawdown = (cumulative - running_max) / running_max
    max_drawdown = np.min(drawdown)

    # Value at Risk
    var_95 = np.percentile(returns_data, 5)  # 5th percentile
    var_99 = np.percentile(returns_data, 1)  # 1st percentile

    return {
        "sharpe_ratio": round(sharpe_ratio, 4) if sharpe_ratio is not None else None,
        "max_drawdown": round(max_drawdown, 4),
        "value_at_risk_95": round(var_95, 6),
        "value_at_risk_99": round(var_99, 6),
        "mean_daily_return": round(mean_return, 6),
        "std_daily_return": round(std_return, 6)
    }


def generate_analytics_summary(
    prices_data: Dict[str, Any],
    product_terms: Optional[Dict[str, Any]] = None,
    dates: Optional[Dict[str, str]] = None,
    risk_free_rate: float = 0.05,
    volatility_windows: List[int] = [20, 60, 252]
) -> Dict[str, Any]:
    """
    Generate comprehensive analytics summary.

    Args:
        prices_data: Price data from fetcher
        product_terms: Product terms (optional)
        dates: Date information including maturity_date (optional)
        risk_free_rate: Risk-free rate for Greeks calculation
        volatility_windows: Windows for rolling volatility

    Returns:
        Complete analytics dictionary
    """
    result = {}

    # Extract price series
    if "data" not in prices_data or not prices_data["data"]:
        logger.warning("No price data available for analytics")
        return {"error": "No price data available"}

    # Get all prices sorted by date
    price_dict = prices_data["data"]
    sorted_dates = sorted(price_dict.keys())
    adj_close_prices = [price_dict[d]["adj_close"] for d in sorted_dates
                        if price_dict[d].get("adj_close") is not None]

    if len(adj_close_prices) < 2:
        logger.warning("Insufficient price data for analytics")
        return {"error": "Insufficient price data"}

    current_price = adj_close_prices[-1]

    # Calculate volatility metrics
    result["volatility"] = calculate_rolling_volatilities(
        adj_close_prices,
        windows=volatility_windows
    )

    # Add overall realized volatility
    full_vol = calculate_realized_volatility(adj_close_prices)
    result["volatility"]["realized_vol_annualized"] = full_vol["realized_vol_annualized"]
    result["volatility"]["sample_size"] = full_vol["sample_size"]

    # Risk metrics
    result["risk_metrics"] = calculate_risk_metrics(adj_close_prices)

    # Greeks and product analysis (if product terms provided)
    if product_terms and dates and "maturity_date" in dates:
        pricing_date = dates.get("pricing_date", datetime.now().strftime("%Y-%m-%d"))

        # Use the most recent volatility available
        vol_to_use = None
        for window in [60, 252, 20]:  # Prefer 60-day, then 252-day, then 20-day
            vol_key = f"vol_{window}d"
            if vol_key in result["volatility"] and result["volatility"][vol_key]:
                vol_to_use = result["volatility"][vol_key]
                break

        if vol_to_use and vol_to_use > 0:
            result["greeks"] = analyze_structured_product_greeks(
                product_terms=product_terms,
                spot=current_price,
                pricing_date=pricing_date,
                maturity_date=dates["maturity_date"],
                volatility=vol_to_use,
                risk_free_rate=risk_free_rate
            )

            result["breakeven_levels"] = calculate_breakeven_levels(
                product_terms=product_terms,
                spot=current_price
            )

    result["current_price"] = current_price
    result["price_series_length"] = len(adj_close_prices)

    return result
