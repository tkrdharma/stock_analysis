# Oversold Reversal Stock Screener

A full-stack web application that screens stocks for **oversold + reversal-to-buy** setups using technical indicators (RSI, MACD, SMA) with fundamental data from Google Finance.

## Architecture

```
stock_analysis/
├── symbols.txt              # One stock symbol per line
├── backend/                 # Python FastAPI
│   ├── main.py              # FastAPI app + routes
│   ├── db.py                # SQLAlchemy engine/session (SQLite)
│   ├── models.py            # ORM models
│   ├── google_finance.py    # Scrape fundamentals + historical prices
│   ├── indicators.py        # RSI(14), MACD(12,26,9), SMA(20)
│   ├── scanner.py           # Screening rules, scoring, reason
│   └── requirements.txt
├── frontend/                # React + Vite
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   └── components/
│   │       ├── ScanControls.jsx
│   │       ├── RecommendationsTable.jsx
│   │       ├── StockDetailsModal.jsx
│   │       └── PriceChart.jsx
│   └── package.json
└── README.md                # ← you are here
```

## Quick Start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The API starts on **http://localhost:8000** (Swagger docs at `/docs`).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on **http://localhost:5173** with API proxy to the backend.

### 3. Usage

1. Click **Reload symbols.txt** to load stock symbols into the database.
2. Click **Run Scan** to fetch data and screen all symbols.
3. View recommended stocks in the table (sorted by score).
4. Click any row for detailed charts and signal information.

## Screening Logic

A stock is **recommended** if:

1. **RSI(14) < 30** (oversold) _AND_
2. At least one reversal confirmation:
   - Bullish **MACD crossover** within the last 5 trading days, _OR_
   - Close **crossed above SMA(20)** within the last 5 trading days, _OR_
   - **RSI rising 3 consecutive days** (momentum reversal)

### Scoring

| Signal                | Points |
|-----------------------|--------|
| MACD crossover        | +3     |
| SMA20 bullish cross   | +2     |
| RSI rising 3 days     | +1     |
| Bonus: (30 − RSI)     | up to +5 |

Results sorted by score descending.

## Data Sources

- **Fundamentals**: Google Finance (httpx + BeautifulSoup4)
- **Historical prices**: Google Finance first, with **Yahoo Finance** (yfinance) as fallback

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/symbols/reload` | Read symbols.txt → DB |
| POST | `/api/scan/run` | Start background scan |
| GET | `/api/scan/{id}` | Scan status |
| GET | `/api/recommendations/latest` | Recommended stocks |
| GET | `/api/recommendations/latest/all` | All scanned (debug) |
| GET | `/api/symbol/{symbol}/details` | Detail data for modal |

## Database

SQLite with tables: `symbols`, `scans`, `fundamentals`, `technicals`, `recommendations`. Auto-created on startup.
# stock_analysis
