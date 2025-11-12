"""
Streamlit Web Application for Structured Products Toolkit

A user-friendly web interface for analyzing structured product filings.
Upload HTML/PDF/text filings and get comprehensive analysis with visualizations.
"""

import streamlit as st
import json
import tempfile
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
from typing import Dict, Any, Optional

from structured_products import (
    extract_symbols,
    extract_dates,
    fetch_historical_prices,
    extract_product_terms,
    summarize_product_terms,
    extract_all_identifiers,
    validate_extraction_results,
    generate_analytics_summary,
)
from structured_products.pdf import read_filing_content, is_pdf_supported


# Page configuration
st.set_page_config(
    page_title="Structured Products Analyzer",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 0.5rem 0;
    }
    .success-box {
        background-color: #d4edda;
        border-left: 5px solid #28a745;
        padding: 1rem;
        margin: 1rem 0;
    }
    .warning-box {
        background-color: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 1rem;
        margin: 1rem 0;
    }
    .error-box {
        background-color: #f8d7da;
        border-left: 5px solid #dc3545;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


def display_header():
    """Display application header."""
    st.markdown('<div class="main-header">📊 Structured Products Analyzer</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sub-header">Upload EDGAR filings to extract symbols, dates, product terms, and calculate analytics</div>',
        unsafe_allow_html=True
    )


def display_sidebar():
    """Display sidebar with options."""
    st.sidebar.header("⚙️ Analysis Options")

    # Extraction options
    st.sidebar.subheader("Extraction")
    extract_terms = st.sidebar.checkbox("Extract Product Terms", value=True, help="Extract barriers, caps, participation rates, etc.")
    extract_identifiers = st.sidebar.checkbox("Extract Identifiers", value=True, help="Extract CUSIP, ISIN, SEDOL")

    # Analytics options
    st.sidebar.subheader("Analytics")
    calculate_analytics = st.sidebar.checkbox("Calculate Analytics", value=True, help="Calculate volatility, Greeks, and risk metrics")

    if calculate_analytics:
        risk_free_rate = st.sidebar.slider(
            "Risk-Free Rate",
            min_value=0.0,
            max_value=0.10,
            value=0.05,
            step=0.0025,
            format="%.4f",
            help="Annual risk-free rate for Greeks calculation"
        )

        vol_windows_str = st.sidebar.text_input(
            "Volatility Windows (days)",
            value="20,60,252",
            help="Comma-separated window sizes"
        )
        try:
            vol_windows = [int(w.strip()) for w in vol_windows_str.split(",")]
        except:
            vol_windows = [20, 60, 252]
            st.sidebar.warning("Invalid windows, using default: 20,60,252")
    else:
        risk_free_rate = 0.05
        vol_windows = [20, 60, 252]

    # Price fetching options
    st.sidebar.subheader("Price Data")
    lookback_days = st.sidebar.slider(
        "Lookback Days",
        min_value=1,
        max_value=30,
        value=7,
        help="Days to look back for historical prices"
    )

    use_cache = st.sidebar.checkbox("Use Price Cache", value=True, help="Cache price data to reduce API calls")

    # PDF options
    st.sidebar.subheader("PDF Options")
    if is_pdf_supported():
        st.sidebar.success("✅ PDF support available")
        max_pdf_pages = st.sidebar.number_input(
            "Max PDF Pages",
            min_value=1,
            max_value=1000,
            value=50,
            help="Maximum pages to extract from PDF"
        )
    else:
        st.sidebar.warning("⚠️ PDF support not available. Install: pip install pdfplumber")
        max_pdf_pages = None

    return {
        "extract_terms": extract_terms,
        "extract_identifiers": extract_identifiers,
        "calculate_analytics": calculate_analytics,
        "risk_free_rate": risk_free_rate,
        "vol_windows": vol_windows,
        "lookback_days": lookback_days,
        "use_cache": use_cache,
        "max_pdf_pages": max_pdf_pages
    }


def process_filing(file_content: str, is_html: bool, options: Dict[str, Any]) -> Dict[str, Any]:
    """Process filing and return results."""

    with st.spinner("🔍 Extracting symbols and dates..."):
        # Extract symbols and dates
        symbol_data = extract_symbols(file_content, is_html=is_html)
        date_data = extract_dates(file_content, is_html=is_html)

        st.success(f"Found {len(symbol_data['yahoo_symbols'])} symbols and {len(date_data)} dates")

    # Initialize result
    result = {
        "indices": symbol_data["indices"],
        "yahoo_symbols": symbol_data["yahoo_symbols"],
        "raw_tickers": symbol_data["raw_tickers"],
        "dates": date_data,
        "prices": {}
    }

    # Extract product terms
    if options["extract_terms"]:
        with st.spinner("📝 Extracting product terms..."):
            product_terms = extract_product_terms(file_content, is_html=is_html)
            terms_summary = summarize_product_terms(product_terms)

            if product_terms:
                result["product_terms"] = product_terms
                result["terms_summary"] = terms_summary
                st.success(f"Extracted {len(product_terms)} product terms")
    else:
        product_terms = None
        terms_summary = None

    # Extract identifiers
    if options["extract_identifiers"]:
        with st.spinner("🔖 Extracting identifiers..."):
            identifiers = extract_all_identifiers(file_content, is_html=is_html)
            if any(identifiers.values()):
                result["identifiers"] = identifiers
                found = [k for k, v in identifiers.items() if v]
                st.success(f"Found identifiers: {', '.join(found)}")

    # Validate
    with st.spinner("✅ Validating extraction..."):
        validation_result = validate_extraction_results(symbol_data, date_data)
        result["validation"] = validation_result

        if validation_result["has_errors"]:
            st.error(f"❌ Validation errors: {validation_result['error_count']}")
        elif validation_result["has_warnings"]:
            st.warning(f"⚠️ Validation warnings: {validation_result['warning_count']}")
        else:
            st.success("✅ Validation passed")

    # Fetch prices
    if symbol_data["yahoo_symbols"] and date_data:
        primary_symbol = symbol_data["yahoo_symbols"][0]
        date_list = list(date_data.values())

        with st.spinner(f"💰 Fetching prices for {primary_symbol}..."):
            try:
                prices = fetch_historical_prices(
                    primary_symbol,
                    date_list,
                    options["lookback_days"],
                    use_cache=options["use_cache"]
                )
                result["prices"] = {
                    "symbol": primary_symbol,
                    "data": prices
                }
                st.success(f"Fetched prices for {len(prices)} dates")
            except Exception as e:
                st.error(f"Could not fetch prices: {e}")
                result["prices"] = {
                    "symbol": primary_symbol,
                    "error": str(e)
                }

    # Calculate analytics
    if options["calculate_analytics"] and result.get("prices", {}).get("data"):
        with st.spinner("📊 Calculating analytics..."):
            try:
                analytics_result = generate_analytics_summary(
                    prices_data=result["prices"],
                    product_terms=product_terms,
                    dates=date_data,
                    risk_free_rate=options["risk_free_rate"],
                    volatility_windows=options["vol_windows"]
                )
                result["analytics"] = analytics_result
                st.success("✅ Analytics calculated")
            except Exception as e:
                st.error(f"Analytics calculation failed: {e}")
                result["analytics"] = {"error": str(e)}

    return result


def display_symbols_and_dates(result: Dict[str, Any]):
    """Display extracted symbols and dates."""
    st.header("📈 Symbols & Dates")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Detected Indices")
        if result["indices"]:
            for idx, symbol in zip(result["indices"], result["yahoo_symbols"]):
                st.write(f"**{idx}** → `{symbol}`")
        else:
            st.info("No indices detected")

    with col2:
        st.subheader("Key Dates")
        if result["dates"]:
            for date_type, date_value in result["dates"].items():
                st.write(f"**{date_type.replace('_', ' ').title()}**: `{date_value}`")
        else:
            st.info("No dates detected")


def display_product_terms(result: Dict[str, Any]):
    """Display product terms."""
    if "product_terms" not in result:
        return

    st.header("📝 Product Terms")

    # Terms summary
    if "terms_summary" in result:
        summary = result["terms_summary"]

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Payoff Type", summary.get("payoff_type", "N/A"))
        col2.metric("Terms Extracted", summary.get("terms_extracted", 0))
        col3.metric("Confidence", summary.get("confidence", "N/A").upper())

        # Flags
        flags = []
        if summary.get("has_downside_protection"):
            flags.append("🛡️ Downside Protection")
        if summary.get("has_upside_cap"):
            flags.append("🔒 Upside Cap")
        if summary.get("has_leverage"):
            flags.append("📈 Leveraged")
        if summary.get("is_path_dependent"):
            flags.append("🛤️ Path Dependent")

        if flags:
            st.write("**Product Features:**")
            st.write(" • ".join(flags))

    # Detailed terms
    st.subheader("Detailed Terms")

    terms_data = []
    for term_name, term_info in result["product_terms"].items():
        if isinstance(term_info, dict):
            terms_data.append({
                "Term": term_name.replace("_", " ").title(),
                "Value": f"{term_info.get('value', 'N/A')} {term_info.get('unit', '')}",
                "Confidence": term_info.get("confidence", "N/A"),
                "Raw Text": term_info.get("raw_text", "N/A")[:50]
            })

    if terms_data:
        df = pd.DataFrame(terms_data)
        st.dataframe(df, use_container_width=True)


def display_identifiers(result: Dict[str, Any]):
    """Display security identifiers."""
    if "identifiers" not in result:
        return

    st.header("🔖 Security Identifiers")

    identifiers = result["identifiers"]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("CUSIP", identifiers.get("cusip") or "Not found")
    with col2:
        st.metric("ISIN", identifiers.get("isin") or "Not found")
    with col3:
        st.metric("SEDOL", identifiers.get("sedol") or "Not found")


def display_prices(result: Dict[str, Any]):
    """Display price data with chart."""
    if not result.get("prices", {}).get("data"):
        return

    st.header("💰 Historical Prices")

    prices_data = result["prices"]["data"]
    symbol = result["prices"]["symbol"]

    # Create dataframe
    price_list = []
    for date_str, price_info in sorted(prices_data.items()):
        price_list.append({
            "Date": price_info.get("actual_date", date_str),
            "Open": price_info.get("open"),
            "High": price_info.get("high"),
            "Low": price_info.get("low"),
            "Close": price_info.get("close"),
            "Adj Close": price_info.get("adj_close"),
            "Volume": price_info.get("volume")
        })

    if price_list:
        df = pd.DataFrame(price_list)

        # Display table
        st.subheader(f"Price Data for {symbol}")
        st.dataframe(df, use_container_width=True)

        # Create candlestick chart
        if len(df) > 1:
            fig = go.Figure(data=[go.Candlestick(
                x=df["Date"],
                open=df["Open"],
                high=df["High"],
                low=df["Low"],
                close=df["Close"],
                name=symbol
            )])

            fig.update_layout(
                title=f"{symbol} Price Chart",
                yaxis_title="Price",
                xaxis_title="Date",
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)


def display_analytics(result: Dict[str, Any]):
    """Display analytics with visualizations."""
    if "analytics" not in result:
        return

    analytics = result["analytics"]

    if "error" in analytics:
        st.error(f"Analytics error: {analytics['error']}")
        return

    st.header("📊 Quantitative Analytics")

    # Current price
    if "current_price" in analytics:
        st.metric("Current Price", f"${analytics['current_price']:,.2f}")

    # Volatility section
    if "volatility" in analytics:
        st.subheader("📉 Historical Volatility")

        vol = analytics["volatility"]

        cols = st.columns(4)
        metrics = [
            ("20-Day", "vol_20d"),
            ("60-Day", "vol_60d"),
            ("252-Day", "vol_252d"),
            ("Realized", "realized_vol_annualized")
        ]

        for col, (label, key) in zip(cols, metrics):
            if vol.get(key) is not None:
                col.metric(f"{label} Vol", f"{vol[key]:.2%}")

        # Volatility chart
        vol_data = []
        for window in ["vol_20d", "vol_60d", "vol_252d"]:
            if vol.get(window):
                vol_data.append({
                    "Window": window.replace("vol_", "").replace("d", "-day"),
                    "Volatility": vol[window] * 100
                })

        if vol_data:
            df_vol = pd.DataFrame(vol_data)
            fig = go.Figure(data=[
                go.Bar(x=df_vol["Window"], y=df_vol["Volatility"], name="Volatility")
            ])
            fig.update_layout(
                title="Volatility Across Different Windows",
                yaxis_title="Annualized Volatility (%)",
                height=300
            )
            st.plotly_chart(fig, use_container_width=True)

    # Risk metrics section
    if "risk_metrics" in analytics:
        st.subheader("⚠️ Risk Metrics")

        risk = analytics["risk_metrics"]

        col1, col2, col3, col4 = st.columns(4)

        if risk.get("sharpe_ratio") is not None:
            col1.metric("Sharpe Ratio", f"{risk['sharpe_ratio']:.3f}")
        if risk.get("max_drawdown") is not None:
            col2.metric("Max Drawdown", f"{risk['max_drawdown']:.2%}")
        if risk.get("value_at_risk_95") is not None:
            col3.metric("VaR 95%", f"{risk['value_at_risk_95']:.2%}")
        if risk.get("value_at_risk_99") is not None:
            col4.metric("VaR 99%", f"{risk['value_at_risk_99']:.2%}")

    # Greeks section
    if "greeks" in analytics:
        st.subheader("🔢 Option Greeks")

        greeks_data = analytics["greeks"]

        # Time to maturity
        if "time_to_maturity_years" in greeks_data:
            st.write(f"**Time to Maturity:** {greeks_data['time_to_maturity_years']:.2f} years ({greeks_data.get('time_to_maturity_days', 0):.0f} days)")

        # ATM Greeks
        if "atm_greeks" in greeks_data:
            st.write("**At-The-Money Greeks:**")

            atm = greeks_data["atm_greeks"]

            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("Delta", f"{atm.get('delta', 0):.4f}")
            col2.metric("Gamma", f"{atm.get('gamma', 0):.6f}")
            col3.metric("Theta", f"{atm.get('theta', 0):.4f}")
            col4.metric("Vega", f"{atm.get('vega', 0):.4f}")
            col5.metric("Rho", f"{atm.get('rho', 0):.4f}")

        # Effective delta
        if "effective_delta" in greeks_data:
            st.metric("Effective Delta (Participation-Adjusted)", f"{greeks_data['effective_delta']:.4f}")

        # Barrier analysis
        if "barrier_analysis" in greeks_data:
            st.write("**Barrier Analysis:**")
            barrier = greeks_data["barrier_analysis"]

            col1, col2 = st.columns(2)
            col1.metric("Barrier Level", f"${barrier['barrier_level']:,.2f}")
            col2.metric("Distance to Barrier", f"{barrier['distance_to_barrier']:.1f}%")

        # Cap analysis
        if "cap_analysis" in greeks_data:
            st.write("**Cap Analysis:**")
            cap = greeks_data["cap_analysis"]

            col1, col2 = st.columns(2)
            col1.metric("Cap Level", f"${cap['cap_level']:,.2f}")
            col2.metric("Distance to Cap", f"{cap['distance_to_cap']:.1f}%")

    # Breakeven levels
    if "breakeven_levels" in analytics:
        st.subheader("🎯 Breakeven Levels")

        levels = analytics["breakeven_levels"].get("levels", {})

        if levels:
            level_data = []
            for level_name, level_info in levels.items():
                level_data.append({
                    "Level": level_name.replace("_", " ").title(),
                    "Price": f"${level_info['price']:,.2f}",
                    "Percentage": f"{level_info['percentage']:+.1f}%",
                    "Description": level_info["description"]
                })

            df_levels = pd.DataFrame(level_data)
            st.dataframe(df_levels, use_container_width=True)


def display_validation(result: Dict[str, Any]):
    """Display validation results."""
    if "validation" not in result:
        return

    validation = result["validation"]

    if validation.get("has_errors"):
        st.error(f"❌ **Validation Errors:** {validation['error_count']}")

        for warning in validation.get("date_warnings", []) + validation.get("symbol_warnings", []):
            if warning["severity"] == "error":
                st.error(f"**{warning['field']}**: {warning['message']}")

    elif validation.get("has_warnings"):
        st.warning(f"⚠️ **Validation Warnings:** {validation['warning_count']}")

        for warning in validation.get("date_warnings", []) + validation.get("symbol_warnings", []):
            if warning["severity"] == "warning":
                st.warning(f"**{warning['field']}**: {warning['message']}")

    else:
        st.success("✅ **Validation Passed:** No errors or warnings")


def main():
    """Main application."""

    display_header()

    # Sidebar options
    options = display_sidebar()

    # File upload
    st.header("📁 Upload Filing")

    uploaded_file = st.file_uploader(
        "Choose a filing file",
        type=["html", "htm", "txt", "pdf"],
        help="Upload an EDGAR filing (HTML, text, or PDF format)"
    )

    if uploaded_file is not None:
        # Read file
        file_extension = Path(uploaded_file.name).suffix.lower()

        try:
            if file_extension == ".pdf":
                if not is_pdf_supported():
                    st.error("PDF support not available. Install with: pip install pdfplumber")
                    return

                # Save to temp file for PDF processing
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_path = tmp_file.name

                content, is_html = read_filing_content(tmp_path, max_pdf_pages=options["max_pdf_pages"])

                # Clean up temp file
                Path(tmp_path).unlink()
            else:
                # Read as text - try multiple encodings
                raw_bytes = uploaded_file.read()

                # Try common encodings in order
                encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
                content = None

                for encoding in encodings_to_try:
                    try:
                        content = raw_bytes.decode(encoding)
                        st.info(f"✅ File decoded using {encoding} encoding")
                        break
                    except UnicodeDecodeError:
                        continue

                if content is None:
                    # Last resort: decode with errors='replace'
                    content = raw_bytes.decode('utf-8', errors='replace')
                    st.warning("⚠️ File contains non-UTF-8 characters. Some characters may be replaced.")

                is_html = file_extension in [".html", ".htm"] or content.strip().startswith("<")

            st.success(f"✅ Loaded {uploaded_file.name} ({len(content):,} characters)")

            # Process button
            if st.button("🚀 Analyze Filing", type="primary", use_container_width=True):

                # Process filing
                result = process_filing(content, is_html, options)

                # Store in session state
                st.session_state["result"] = result
                st.session_state["filename"] = uploaded_file.name

        except Exception as e:
            st.error(f"Error loading file: {e}")
            return

    # Display results if available
    if "result" in st.session_state:
        result = st.session_state["result"]
        filename = st.session_state.get("filename", "filing")

        st.markdown("---")

        # Display sections
        display_symbols_and_dates(result)

        st.markdown("---")

        display_product_terms(result)

        st.markdown("---")

        display_identifiers(result)

        st.markdown("---")

        display_prices(result)

        st.markdown("---")

        display_analytics(result)

        st.markdown("---")

        display_validation(result)

        # Download results
        st.markdown("---")
        st.header("💾 Download Results")

        col1, col2 = st.columns(2)

        with col1:
            # JSON download
            json_str = json.dumps(result, indent=2)
            st.download_button(
                label="📥 Download JSON",
                data=json_str,
                file_name=f"{Path(filename).stem}_analysis.json",
                mime="application/json",
                use_container_width=True
            )

        with col2:
            # Pretty print option
            if st.button("📋 Copy JSON to Clipboard", use_container_width=True):
                st.code(json_str, language="json")


if __name__ == "__main__":
    main()
