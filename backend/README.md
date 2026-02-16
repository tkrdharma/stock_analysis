# Backend – Oversold Reversal Stock Screener

FastAPI + SQLite backend that screens Indian stocks (NSE/BOM) for oversold reversal buy setups using Google Finance / Yahoo Finance data.

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python      | 3.11+   |
| pip         | latest  |

## Installation

```bash
# 1. Navigate to backend folder
cd backend

# 2. (Recommended) Create a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Dependencies (requirements.txt)

| Package        | Purpose                                    |
|----------------|--------------------------------------------|
| fastapi        | REST API framework                         |
| uvicorn        | ASGI server                                |
| sqlalchemy     | ORM + SQLite persistence                   |
| httpx          | Async HTTP client for Google Finance       |
| beautifulsoup4 | HTML parsing for fundamentals scraping     |
| yfinance       | Yahoo Finance fallback for price history   |
| lxml           | Fast HTML/XML parser for BeautifulSoup     |

## Running

```bash
python main.py
```

- API server starts on **http://localhost:8000**
- Swagger docs at **http://localhost:8000/docs**
- SQLite database created automatically at `backend/stock_screener.db`

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/api/symbols/reload`            | Read `symbols.txt` and upsert into DB |
| POST   | `/api/scan/run`                  | Start a background scan (returns `scan_id`) |
| GET    | `/api/scan/active`               | Check if a scan is currently running |
| GET    | `/api/scan/{scan_id}`            | Scan status, counts, and live progress |
| GET    | `/api/scan/{scan_id}/logs`       | Skip / ignore / error logs for a scan |
| GET    | `/api/scan/latest/logs`          | Logs for the most recent scan |
| GET    | `/api/recommendations/latest`    | Recommended stocks from latest scan |
| GET    | `/api/recommendations/latest/all`| All symbols from latest scan |
| GET    | `/api/symbol/{symbol}/details`   | Detailed data for the modal (charts, signals) |
| DELETE | `/api/scan/{scan_id}/symbol/{symbol}` | Delete a symbol's records from a scan |
| DELETE | `/api/scan/latest/symbol/{symbol}`    | Delete a symbol from the latest scan |
| DELETE | `/api/admin/clear-all?confirm=true`   | Delete all records from all tables |

## Architecture

- **main.py** – FastAPI app, routes, background scan orchestration, progress tracking
- **google_finance.py** – Scrapes fundamentals from Google Finance; falls back to Yahoo Finance for historical prices; auto-detects network issues and uses mock data
- **mock_data.py** – Deterministic mock data provider for offline / firewall environments
- **indicators.py** – RSI(14), MACD(12,26,9), SMA(20) calculations
- **scanner.py** – Per-symbol processing, signal detection, scoring logic
- **models.py** – SQLAlchemy ORM (tables: symbols, scans, fundamentals, technicals, recommendations, scan_logs)
- **db.py** – Engine / session management

## Screening Logic

A stock is **recommended** when:

1. **RSI(14) < 30** within the last 5 days (oversold), AND
2. At least one reversal confirmation:
   - Bullish **MACD crossover** (last 5 days)
   - Close **crossed above SMA(20)** (last 5 days)
   - **RSI rising 3 consecutive days**
   - **RSI bullish divergence** (last 5 days)
   - **MACD bullish divergence** (last 5 days)

### Scoring

| Signal                    | Points |
|---------------------------|--------|
| MACD crossover            | +3     |
| SMA20 bullish cross       | +2     |
| MACD bullish divergence   | +2     |
| RSI rising 3 days         | +1     |
| RSI bullish divergence    | +1     |
| Bonus: min(30 − RSI, 5)   | up to +5 |

## Resetting Data

```bash
# Delete the SQLite database and restart the backend
del backend\stock_screener.db   # Windows
rm backend/stock_screener.db    # macOS/Linux
python main.py
```

## Network / Proxy

If your network blocks outbound HTTPS (e.g. corporate firewall), the app automatically uses deterministic mock data. To use a proxy:

```bash
# Windows
set HTTPS_PROXY=http://proxy.host:8080
set HTTP_PROXY=http://proxy.host:8080

# macOS / Linux
export HTTPS_PROXY=http://proxy.host:8080
export HTTP_PROXY=http://proxy.host:8080
```
