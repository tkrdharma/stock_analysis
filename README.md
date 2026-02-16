# Oversold Reversal Stock Screener

A full-stack web application that screens Indian stocks (NSE/BOM) for **oversold + reversal-to-buy** setups using technical indicators (RSI, MACD, SMA) with fundamental data from Google Finance.

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Python      | 3.11+   | `python --version` |
| Node.js     | 18+     | `node --version`   |
| npm          | 9+      | `npm --version`    |

## Architecture

```
stock_analysis/
├── symbols.txt              # One stock symbol per line (edit to change universe)
├── backend/                 # Python FastAPI + SQLite
│   ├── main.py              # FastAPI app, routes, scan orchestration, progress tracking
│   ├── db.py                # SQLAlchemy engine/session (SQLite)
│   ├── models.py            # ORM models (symbols, scans, fundamentals, technicals, recommendations, scan_logs)
│   ├── google_finance.py    # Scrape fundamentals + historical prices (Google → Yahoo → mock fallback)
│   ├── mock_data.py         # Deterministic mock data for offline/firewall environments
│   ├── indicators.py        # RSI(14), MACD(12,26,9), SMA(20)
│   ├── scanner.py           # Per-symbol processing, signal detection, scoring
│   └── requirements.txt     # Python dependencies
├── frontend/                # React + Vite
│   ├── src/
│   │   ├── App.jsx          # Main app component (state, polling, scan recovery)
│   │   ├── api.js           # Axios API helpers
│   │   ├── index.css        # Global styles (dark theme, progress bar, etc.)
│   │   └── components/
│   │       ├── ScanControls.jsx        # Buttons + scan progress bar
│   │       ├── RecommendationsTable.jsx # Sortable, paginated stock table
│   │       ├── StockDetailsModal.jsx    # Detail modal with charts
│   │       └── PriceChart.jsx           # Recharts line/bar charts
│   ├── vite.config.js       # Vite config (port, API proxy)
│   └── package.json         # Node dependencies
├── SETUP.md                 # Detailed setup guide
└── README.md                # ← you are here
```

## Quick Start (New Machine)

### 1. Clone the repository

```bash
git clone <repo-url>
cd stock_analysis
```

### 2. Backend setup

```bash
cd backend

# Create virtual environment (recommended)
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the API server
python main.py
```

The API starts on **http://localhost:8000** (Swagger docs at `/docs`).

### 3. Frontend setup (new terminal)

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Opens on **http://localhost:5173** (or next available port) with API proxy to the backend.

### 4. First run

1. Open the frontend URL in your browser
2. Click **📄 Reload symbols.txt** to load stock symbols into the database
3. Click **🔍 Run Scan** — a progress bar will show live status
4. View recommended stocks in the table; click any row for detailed charts

## Features

- **Live scan progress bar** — shows completed/total symbols, current symbol, errors, animated progress
- **Sortable & searchable table** — columns: Symbol, CMP, PE, ROCE, Debt, RSI Divergence, MACD Divergence
- **Pagination** — 10 / 25 / 50 / 100 rows per page
- **Detail modal** — fundamentals, technicals, triggered signals, interactive Price/RSI/MACD charts
- **RSI & MACD divergence detection** — checks for bullish divergence in the last 5 trading days
- **Daily skip logic** — re-scanning the same day reuses already-fetched data
- **Scan logs** — tracks skipped / ignored / errored symbols per scan
- **Delete controls** — delete individual symbols or clear all records
- **Offline fallback** — auto-detects blocked networks; uses deterministic mock data for dev/demo
- **Page-load recovery** — refreshing the browser during a scan auto-resumes the progress bar

## Screening Logic

A stock is **recommended** if:

1. **RSI(14) < 30** within the last 5 days (oversold), AND
2. At least one reversal confirmation:
   - Bullish **MACD crossover** within the last 5 trading days
   - Close **crossed above SMA(20)** within the last 5 trading days
   - **RSI rising 3 consecutive days** (momentum reversal)
   - **RSI bullish divergence** (price lower low + RSI higher low, last 5 days)
   - **MACD bullish divergence** (price lower low + MACD higher low, last 5 days)

### Scoring

| Signal                    | Points |
|---------------------------|--------|
| MACD crossover            | +3     |
| SMA20 bullish cross       | +2     |
| MACD bullish divergence   | +2     |
| RSI rising 3 days         | +1     |
| RSI bullish divergence    | +1     |
| Bonus: min(30 − RSI, 5)   | up to +5 |

Results sorted by score descending.

## Data Sources

| Data | Primary Source | Fallback |
|------|---------------|----------|
| Fundamentals (CMP, PE, ROCE, BV, Debt, Industry) | Google Finance | Mock data |
| Historical prices (9 months daily close) | Google Finance | Yahoo Finance → Mock data |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST   | `/api/symbols/reload`            | Read symbols.txt → DB |
| POST   | `/api/scan/run`                  | Start background scan |
| GET    | `/api/scan/active`               | Check for running scan |
| GET    | `/api/scan/{id}`                 | Scan status + progress |
| GET    | `/api/scan/{id}/logs`            | Scan logs (skip/error) |
| GET    | `/api/scan/latest/logs`          | Latest scan logs |
| GET    | `/api/recommendations/latest`    | Recommended stocks |
| GET    | `/api/recommendations/latest/all`| All scanned symbols |
| GET    | `/api/symbol/{symbol}/details`   | Detail data for modal |
| DELETE | `/api/scan/{id}/symbol/{symbol}` | Delete symbol from scan |
| DELETE | `/api/scan/latest/symbol/{symbol}` | Delete from latest scan |
| DELETE | `/api/admin/clear-all?confirm=true` | Wipe all tables |

## Database

SQLite file at `backend/stock_screener.db` — auto-created on first startup.

Tables: `symbols`, `scans`, `fundamentals`, `technicals`, `recommendations`, `scan_logs`.

To reset: delete the DB file and restart the backend.

## Customising the Stock Universe

Edit `symbols.txt` in the project root — one NSE/BOM symbol per line. Lines starting with `#` are ignored.

```text
RELIANCE
TCS
INFY
# This line is a comment
HDFCBANK
```

After editing, click **Reload symbols.txt** in the UI (or `POST /api/symbols/reload`).

## Network / Proxy

If your network blocks outbound HTTPS (corporate firewall), the app automatically detects this and falls back to deterministic mock data. To configure a proxy:

```bash
# Windows
set HTTPS_PROXY=http://proxy.host:8080
set HTTP_PROXY=http://proxy.host:8080

# macOS / Linux
export HTTPS_PROXY=http://proxy.host:8080
export HTTP_PROXY=http://proxy.host:8080
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Frontend shows "Unable to connect" | Ensure the backend is running on port 8000 |
| `npm run dev` picks a different port | That's normal — Vite auto-selects the next available port |
| Scan takes a long time | Network may be slow or blocked; mock data will be used as fallback |
| `no such column: fundamentals.debt` | Delete `backend/stock_screener.db` and restart the backend |
| `A scan is already running` (409) | Wait for the current scan to finish, or restart the backend |
