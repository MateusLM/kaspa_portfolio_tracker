# 📊 Kaspa Portfolio Tracker

> A powerful, real-time portfolio tracking application for Kaspa (KAS) cryptocurrency built with Python and Streamlit.

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![Streamlit](https://img.shields.io/badge/streamlit-1.51+-red.svg)
![License](https://img.shields.io/badge/license-Personal%20Use-green.svg)

---

## ✨ Features

### 📈 Real-Time Portfolio Analytics
- **Live Price Tracking** - Fetches current Kaspa prices from CoinGecko API
- **Portfolio Valuation** - Real-time USD value calculation for your holdings
- **Balance Overview** - Track total received, sent, and current balance

### 📊 Advanced Visualizations
- **Historical Portfolio Value Charts** - Interactive time-series graphs powered by Plotly
- **Balance vs. Price Comparison** - Correlate your holdings with market movements
- **Transaction Timeline** - Comprehensive view of all wallet activity

### 💾 Smart Data Management
- **SQLite Database Caching** - Minimizes API calls and improves performance
- **Historical Data Import** - Support for Excel-based historical price data
- **Multi-Address Support** - Track multiple Kaspa wallets simultaneously

### 📥 Export & Reporting
- **CSV Export** - Download detailed transaction reports for analysis
- **Accurate Transaction Details** - Precise sent/received amounts using Kaspa API's advanced features

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10 or higher** - [Download Python](https://www.python.org/downloads/)

### Installation

#### 1️⃣ Navigate to Project Directory

```powershell
cd c:\Users\...\kaspa_portfolio_tracker
```

#### 2️⃣ Create Virtual Environment

```powershell
python -m venv .venv
```

#### 3️⃣ Activate Virtual Environment

```powershell
.venv\Scripts\Activate.ps1
```

> **Note:** If you get an execution policy error, run: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

#### 4️⃣ Install Dependencies

```powershell
pip install streamlit pandas requests plotly openpyxl
```

**Installed packages:**
- `streamlit` - Web application framework
- `pandas` - Data manipulation and analysis
- `requests` - HTTP library for API calls
- `plotly` - Interactive charting library
- `openpyxl` - Excel file processing

---

## 💻 Usage

### Starting the Application

Make sure your virtual environment is activated, then launch the Streamlit web interface:

```powershell
# If not already activated
.venv\Scripts\Activate.ps1

# Run the app
streamlit run app.py
```

The application will automatically open in your default browser at `http://localhost:8501`

### Using the Tracker

1. **📝 Enter Wallet Addresses**
   - Paste one or more Kaspa addresses in the sidebar
   - Use one address per line for multiple wallets

2. **🔄 Generate Report**
   - Click the "Generate Report" button
   - The app auto-generates reports when addresses are entered

3. **📊 Explore Analytics**
   - **Summary Metrics** - View key portfolio statistics at the top
   - **Portfolio Value Chart** - Analyze historical performance
   - **Balance vs. Price Graph** - Compare holdings against market price
   - **Transaction Table** - Detailed breakdown of all transactions

4. **💾 Export Data**
   - Download transaction reports as CSV files for external analysis

---

## 📁 Project Structure

```
kaspa_portfolio_tracker/
├── app.py              # Main Streamlit application
├── database.py         # SQLite database operations
├── kaspa_data.db       # SQLite database (auto-generated)
├── pyproject.toml      # Poetry dependencies & project config
├── poetry.lock         # Locked dependency versions
└── README.md           # This file
```

---

## ⚙️ Configuration

### Historical Price Data

The application intelligently manages historical price data:

1. **Database Check** - First checks `kaspa_data.db` for existing price data
2. **Excel Import** - Imports from `kaspa_report.xlsx` if available (for dates older than 365 days)
3. **API Fetch** - Retrieves missing data from CoinGecko API (free tier: last 365 days)

> **💡 Tip:** For transactions older than 365 days, place a `kaspa_report.xlsx` file in the project directory with a sheet named "kas price" containing columns: `Date` and `Kas Price`

### Secrets Management
 
 To securely manage your API keys (e.g., for CoinStats), use Streamlit's secrets management:
 
 1. Create a file named `.streamlit/secrets.toml` in the project root.
 2. Add your API key to the file:
 
 ```toml
 COINSTATS_API_KEY = "your_api_key_here"
 ```
 
 > **Note:** The `.streamlit/` directory is added to `.gitignore` to prevent accidental commits of your secrets.
 
 ### API Endpoints

#### Kaspa API
- **Endpoint:** `https://api.kaspa.org/addresses/{address}/full-transactions`
- **Parameters:** `resolve_previous_outpoints=light` for accurate sent amount calculations
- **Purpose:** Transaction history and wallet data

#### CoinGecko API
- **Historical Prices:** `/coins/kaspa/market_chart/range`
- **Current Price:** `/simple/price`
- **Rate Limit:** Free tier (check CoinGecko documentation for limits)

---

## 🔧 Troubleshooting

### ⚠️ API Rate Limits

**Problem:** CoinGecko API errors or rate limit messages

**Solutions:**
- Wait 1-2 minutes before retrying
- The app caches data in the database to minimize API calls
- Consider upgrading to CoinGecko Pro for higher limits

---

## 🛠️ Development

### Running Tests

Test individual components:

```powershell
# Test transaction API functionality
python inspect_data.py

# Test price API functionality
python test_price.py
```

### Database Management

**Database Contents:**
- Daily Kaspa prices (date, price pairs)
- Automatically populated from API calls and Excel imports

**Reset Database:**
```powershell
# Delete the database file
Remove-Item kaspa_data.db

# Restart the app - database will be recreated
streamlit run app.py
```

### Adding Dependencies

```powershell
# Add a new package
pip install package-name

# Save current dependencies
pip freeze > requirements.txt
```

---

## 📝 License

This project is provided **as-is** for personal use.

---

## 🤝 Support & Resources

### Documentation
- [Kaspa API Documentation](https://api.kaspa.org)
- [CoinGecko API Documentation](https://www.coingecko.com/en/api)
- [Streamlit Documentation](https://docs.streamlit.io)

### Community
- [Kaspa Discord](https://discord.gg/kaspa)
- [Kaspa Official Website](https://kaspa.org)

---

## 👨‍💻 Author

**Mateus Líbano Monteiro**
- Email: mateuslibanomonteiro@gmail.com

---

<div align="center">

**Built with ❤️ for the Kaspa community**

</div>
