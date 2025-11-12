# Streamlit Web Application

A user-friendly web interface for analyzing structured product filings. Upload EDGAR HTML/PDF files and get comprehensive analysis with interactive visualizations.

## Features

### 📁 File Upload
- Support for HTML, HTM, TXT, and PDF files
- Drag-and-drop interface
- Automatic format detection

### 📊 Analysis Options
- **Extract Product Terms**: Barriers, caps, participation rates, autocall triggers, etc.
- **Extract Identifiers**: CUSIP, ISIN, SEDOL validation
- **Calculate Analytics**: Historical volatility, Black-Scholes Greeks, risk metrics
- **Configurable Parameters**:
  - Risk-free rate (0-10%, default 5%)
  - Volatility windows (default: 20, 60, 252 days)
  - Lookback days for price data (1-30, default 7)
  - Price caching option
  - PDF page limit

### 📈 Interactive Visualizations

#### Price Charts
- **Candlestick Charts**: OHLC data visualization with Plotly
- Interactive zoom, pan, and hover tooltips
- Multiple date ranges

#### Volatility Analysis
- **Bar Charts**: Compare volatility across different windows
- Visual representation of short-term vs long-term volatility
- Color-coded metrics

#### Risk Metrics Dashboard
- **Sharpe Ratio**: Risk-adjusted return metric
- **Maximum Drawdown**: Peak-to-trough loss visualization
- **Value at Risk (VaR)**: 95% and 99% confidence intervals
- Color-coded risk levels (green/yellow/red)

### 🔢 Quantitative Analytics Display

#### Greeks Analysis
- **ATM Greeks Table**: Delta, gamma, theta, vega, rho
- **Barrier Analysis**: Greeks at barrier level with distance metrics
- **Cap Analysis**: Upside limitation with distance to cap
- **Effective Delta**: Participation-adjusted exposure

#### Breakeven Levels
- **Interactive Table**: All critical price levels
- **Distance Metrics**: How far current price is from each level
- **Descriptions**: Clear explanations of each level

### 📝 Results Display

#### Symbols & Dates
- **Side-by-side view**: Detected indices and key dates
- **Yahoo Finance symbols**: Direct mapping from index names
- **Date types**: Pricing, trade, settlement, maturity dates

#### Product Terms
- **Summary Cards**: Payoff type, confidence, feature flags
- **Detailed Table**: All extracted terms with confidence scores
- **Visual Indicators**: Icons for downside protection, caps, leverage, path dependency

#### Security Identifiers
- **Three-column layout**: CUSIP, ISIN, SEDOL
- **Validation status**: Check marks for valid identifiers
- **Not found indicators**: Clear when identifiers missing

#### Validation Results
- **Color-coded messages**:
  - 🟢 Green: Validation passed
  - 🟡 Yellow: Warnings present
  - 🔴 Red: Errors found
- **Detailed warnings**: Field-by-field validation messages

### 💾 Export Options
- **Download JSON**: Complete analysis results
- **Copy to Clipboard**: Pretty-printed JSON for sharing
- **Filename preservation**: Uses original filename for exports

## Installation

### Option 1: Standard Installation

```bash
# Install all dependencies including Streamlit
pip install -r requirements.txt
```

### Option 2: Streamlit Only

If you already have the core toolkit installed:

```bash
pip install streamlit plotly
```

### Optional: PDF Support

For PDF filing support:

```bash
pip install pdfplumber
```

## Usage

### Starting the App

```bash
streamlit run streamlit_app.py
```

The app will open automatically in your default browser at `http://localhost:8501`

### Step-by-Step Workflow

1. **Configure Analysis Options** (left sidebar):
   - Check/uncheck extraction options
   - Enable analytics calculations
   - Adjust risk-free rate if needed
   - Set volatility windows
   - Configure lookback days

2. **Upload Filing**:
   - Click "Browse files" or drag-and-drop
   - Supported formats: .html, .htm, .txt, .pdf
   - Wait for file to load

3. **Analyze**:
   - Click "🚀 Analyze Filing" button
   - Watch progress indicators
   - Review results as they appear

4. **Explore Results**:
   - Scroll through each section
   - Interact with charts (zoom, pan, hover)
   - Review validation messages

5. **Download**:
   - Click "📥 Download JSON" for results
   - Use "📋 Copy JSON" to view formatted output

## Screenshots

### Main Interface
```
+------------------+----------------------------------------+
|                  |  📊 Structured Products Analyzer       |
| ⚙️ Analysis      |  Upload EDGAR filings to extract...   |
| Options          |                                        |
|                  |  📁 Upload Filing                      |
| ☑ Extract Terms  |  [Drag and drop or browse]             |
| ☑ Extract IDs    |                                        |
| ☑ Analytics      |  🚀 Analyze Filing                     |
|                  |                                        |
| Risk-Free: 5%    |  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━     |
| Windows:         |                                        |
| 20,60,252        |  📈 Symbols & Dates                    |
|                  |  [Results display here]                |
+------------------+----------------------------------------+
```

### Volatility Chart Example
```
Historical Volatility
┌─────────────────────────────────────┐
│ 20%│           ███                  │
│ 15%│       ███ ███ ███              │
│ 10%│   ███ ███ ███ ███              │
│  5%│   ███ ███ ███ ███              │
│  0%└───────────────────────────────│
│     20d   60d   252d               │
└─────────────────────────────────────┘
```

### Greeks Display
```
🔢 Option Greeks

Time to Maturity: 0.99 years (364 days)

At-The-Money Greeks:
┌─────────┬────────┬────────┬───────┬──────┐
│ Delta   │ Gamma  │ Theta  │ Vega  │ Rho  │
├─────────┼────────┼────────┼───────┼──────┤
│ 0.6234  │ 0.0008 │ -3.21  │ 19.88 │ 12.5 │
└─────────┴────────┴────────┴───────┴──────┘

Effective Delta: 0.6234
```

## Configuration Options

### Sidebar Settings

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| Extract Terms | ✓ | - | Extract product features |
| Extract Identifiers | ✓ | - | Extract CUSIP/ISIN/SEDOL |
| Calculate Analytics | ✓ | - | Volatility & Greeks |
| Risk-Free Rate | 5% | 0-10% | For Greeks calculation |
| Volatility Windows | 20,60,252 | Custom | Window sizes in days |
| Lookback Days | 7 | 1-30 | Price history window |
| Use Cache | ✓ | - | Cache price data |
| Max PDF Pages | 50 | 1-1000 | PDF extraction limit |

### Performance Tips

1. **Large PDFs**: Set lower max pages (10-20) for faster processing
2. **Price Caching**: Keep enabled to reduce API calls and speed up repeated analysis
3. **Analytics**: Disable if only need extraction (faster)
4. **Volatility Windows**: Use fewer windows (e.g., just "60") for faster calculation

## Use Cases

### 1. Quick Filing Review
```
Goal: Quickly understand product structure
Settings:
  ✓ Extract Terms
  ✗ Analytics
  ✗ Identifiers
Time: ~5 seconds
```

### 2. Comprehensive Analysis
```
Goal: Full quantitative evaluation
Settings:
  ✓ Extract Terms
  ✓ Extract Identifiers
  ✓ Calculate Analytics
  Risk-Free: 5%
Time: ~15-30 seconds
```

### 3. Pricing Verification
```
Goal: Validate issuer pricing
Settings:
  ✓ Extract Terms
  ✓ Calculate Analytics
  Risk-Free: Current treasury rate
  Windows: 60,252
Focus: Greeks section, compare delta/vega
```

### 4. Risk Assessment
```
Goal: Understand downside risk
Settings:
  ✓ Extract Terms
  ✓ Calculate Analytics
Focus:
  - Barrier analysis
  - Max drawdown
  - VaR metrics
  - Distance to barrier
```

## Troubleshooting

### PDF Support Not Available
**Error**: "PDF support not available"
**Solution**:
```bash
pip install pdfplumber
streamlit run streamlit_app.py
```

### File Upload Fails
**Error**: "Error loading file"
**Solutions**:
- Check file is valid HTML/PDF
- Ensure file isn't corrupted
- Try smaller file size
- Check file permissions

### Price Fetching Fails
**Error**: "Could not fetch prices"
**Solutions**:
- Check internet connection
- Verify symbol is valid
- Try enabling cache
- Reduce lookback days

### Analytics Calculation Fails
**Error**: "Analytics calculation failed"
**Solutions**:
- Ensure sufficient price data (need 20+ prices)
- Check dates are valid
- Verify maturity date is in future
- Try disabling analytics to see if extraction works

### Slow Performance
**Solutions**:
- Enable price caching
- Reduce PDF max pages
- Use fewer volatility windows
- Disable analytics if not needed
- Clear browser cache

## API Rate Limits

### Yahoo Finance
- Rate limit: ~2 calls/second (automatically handled)
- Caching: Recommended to reduce API calls
- Failures: Auto-retry with exponential backoff

### Recommendations
- Enable caching for repeated analysis
- Batch multiple filings sequentially
- Avoid processing 100+ files rapidly
- Consider local price data for high-volume use

## Deployment

### Local Development
```bash
streamlit run streamlit_app.py
```

### Streamlit Cloud
1. Push code to GitHub repository
2. Go to https://share.streamlit.io
3. Connect GitHub account
4. Select repository and branch
5. Set `streamlit_app.py` as main file
6. Deploy

### Docker
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 8501
CMD ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
```

Build and run:
```bash
docker build -t structured-products .
docker run -p 8501:8501 structured-products
```

## Browser Compatibility

| Browser | Version | Status |
|---------|---------|--------|
| Chrome | 90+ | ✅ Fully supported |
| Firefox | 88+ | ✅ Fully supported |
| Safari | 14+ | ✅ Fully supported |
| Edge | 90+ | ✅ Fully supported |

## Security Considerations

### Data Privacy
- All processing is local (except Yahoo Finance API calls)
- No filing data is stored on servers
- Session data cleared on browser close

### File Upload Safety
- Only accepts text-based files
- No executable code processing
- Size limits enforced by Streamlit

### API Keys
- No API keys required
- Uses public Yahoo Finance data
- No authentication needed

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl/Cmd + K` | Focus on file upload |
| `Ctrl/Cmd + Enter` | Run analysis |
| `Ctrl/Cmd + R` | Refresh page |
| `Ctrl/Cmd + Shift + R` | Hard refresh (clear cache) |

## Advanced Features

### Custom Volatility Windows
```
Sidebar > Volatility Windows: "10,30,90,180,365"
```

### Multiple File Analysis
Process multiple files sequentially:
1. Upload first file
2. Analyze and download results
3. Upload next file
4. Repeat

### Programmatic Access
For batch processing, use CLI instead:
```bash
for file in filings/*.html; do
  python -m structured_products -i "$file" \
    --extract-terms \
    --calculate-analytics \
    --pretty > "results/$(basename $file .html).json"
done
```

## Future Enhancements

Planned features:
- [ ] Batch file upload (multiple files at once)
- [ ] Comparison view (compare multiple filings side-by-side)
- [ ] Custom payoff diagram generation
- [ ] Excel export option
- [ ] Historical volatility surface visualization
- [ ] Monte Carlo simulation integration
- [ ] Portfolio-level Greeks aggregation
- [ ] Email report functionality

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review main README.md
3. Check ANALYTICS_ENHANCEMENT.md for Greeks documentation
4. Open issue on GitHub repository

## License

MIT License - Same as main toolkit

---

**Version**: 1.0.0
**Requires**: structured_products >= 0.5.0
**Python**: 3.7+
**Streamlit**: 1.28.0+
