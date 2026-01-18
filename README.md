# 🚀 Nado Trading Setup Analyzer

A comprehensive trading analysis tool for [Nado](https://app.nado.xyz) perpetual markets. Automatically scans all available perpetual instruments and identifies the best trading setups based on technical analysis, funding rates, and risk metrics.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## ✨ Features

- **Real-time Market Scanning** - Automatically fetches data from Nado's perpetual markets
- **Technical Analysis** - RSI, MACD, Bollinger Bands, Moving Averages, ADX, and more
- **Funding Rate Analysis** - Identifies funding rate arbitrage opportunities
- **Smart Scoring System** - Rates setups based on trend, momentum, funding, liquidity, and volatility
- **Risk Management** - Suggests leverage, stop-loss, and take-profit levels
- **Beautiful Dashboard** - Modern, responsive web interface
- **REST API** - Full API access for integrations

## 📊 How It Works

The analyzer evaluates each market using a weighted scoring system:

| Component | Weight | Description |
|-----------|--------|-------------|
| Trend | 30% | Price vs moving averages, trend strength (ADX) |
| Momentum | 25% | RSI levels, MACD signals |
| Funding | 20% | Funding rate advantage for position direction |
| Liquidity | 15% | Bid-ask spread, 24h trading volume |
| Volatility | 10% | Bollinger Band width, ATR analysis |

## 🛠️ Installation

### Prerequisites

- Python 3.10 or higher
- pip (Python package manager)

### Step 1: Clone or Download

```bash
cd /path/to/your/project
```

### Step 2: Create Virtual Environment (Recommended)

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure (Optional)

Create a `.env` file in the project root to customize settings:

```env
# Nado API URLs (defaults work for mainnet)
NADO_GATEWAY_URL=https://gateway.nado.xyz
NADO_ARCHIVE_URL=https://archive.nado.xyz

# Data refresh interval (seconds)
DATA_REFRESH_INTERVAL=60

# Server settings
HOST=0.0.0.0
PORT=8000
DEBUG=true

# Trading thresholds
RSI_OVERSOLD=30
RSI_OVERBOUGHT=70
FUNDING_RATE_HIGH=0.01
FUNDING_RATE_LOW=-0.01
MIN_VOLUME_24H=100000
MAX_SPREAD_PERCENT=0.5
```

## 🚀 Running the Application

### Start the Server

```bash
# From the project root directory
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Or use the shorter command:

```bash
uvicorn app.main:app --reload
```

### Access the Application

- **Web Dashboard**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **Alternative API Docs**: http://localhost:8000/redoc

## 📡 API Endpoints

### Health & Status

```
GET /api/health
```
Returns server status and last update time.

### Market Summary

```
GET /api/summary
```
Returns overview of all markets including top movers and best setups.

### All Trading Setups

```
GET /api/setups?signal=buy&quality=good&min_score=60&limit=10
```
Returns trading setups with optional filtering.

### Specific Market Setup

```
GET /api/setups/{symbol}
```
Returns detailed analysis for a specific symbol (e.g., `SOLUSDT0`).

### Best Setups

```
GET /api/best-setups?direction=long&limit=5
```
Returns the best trading setups for long or short positions.

### Funding Opportunities

```
GET /api/funding-opportunities?favorable_for=long&limit=5
```
Returns markets with favorable funding rates.

### Manual Refresh

```
POST /api/refresh
```
Triggers immediate data refresh.

## 🎯 Understanding Signals

| Signal | Score Range | Meaning |
|--------|-------------|---------|
| 🟢 Strong Buy | 75-100 | Excellent long opportunity |
| 🟢 Buy | 60-74 | Good long opportunity |
| ⚪ Neutral | 41-59 | No clear direction |
| 🔴 Sell | 26-40 | Good short opportunity |
| 🔴 Strong Sell | 0-25 | Excellent short opportunity |

## ⚠️ Risk Warnings

**This tool is for informational purposes only.** 

- Trading perpetual contracts involves substantial risk of loss
- Leverage amplifies both gains and losses
- Past performance does not guarantee future results
- Always do your own research (DYOR)
- Never trade more than you can afford to lose
- Check Nado's [Terms of Use](https://www.nado.xyz/terms-of-use) for regional restrictions

## 🏗️ Project Structure

```
Nado/
├── app/
│   ├── __init__.py        # Package initialization
│   ├── config.py          # Configuration management
│   ├── models.py          # Pydantic data models
│   ├── nado_client.py     # Nado API client
│   ├── analyzer.py        # Trading setup analyzer
│   └── main.py            # FastAPI application
├── static/
│   ├── index.html         # Web dashboard
│   ├── styles.css         # Styles
│   └── app.js             # Frontend JavaScript
├── requirements.txt       # Python dependencies
├── README.md              # This file
└── .env                   # Environment variables (create this)
```

## 🔧 Development

### Running in Development Mode

```bash
uvicorn app.main:app --reload --log-level debug
```

### Testing API Endpoints

```bash
# Check health
curl http://localhost:8000/api/health

# Get all markets
curl http://localhost:8000/api/markets

# Get best setups
curl "http://localhost:8000/api/best-setups?direction=long&limit=3"
```

## 📚 References

- [Nado Documentation](https://docs.nado.xyz)
- [Nado API V2](https://docs.nado.xyz/developer-resources/api/v2)
- [Funding Rates](https://docs.nado.xyz/funding-rates)
- [Liquidations](https://docs.nado.xyz/liquidations)

## 📄 License

This project is for educational purposes. Use at your own risk.

---

Built with ❤️ for the Nado community

