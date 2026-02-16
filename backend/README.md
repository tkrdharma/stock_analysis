# Backend – Oversold Reversal Stock Screener

FastAPI backend that screens stocks for oversold + reversal setups using Google Finance data.

## Quick start

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The API server starts on **http://localhost:8000**.  
Swagger docs at **http://localhost:8000/docs**.

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/symbols/reload` | Read `symbols.txt` and upsert into DB |
| POST | `/api/scan/run` | Start a background scan |
| GET  | `/api/scan/{scan_id}` | Scan status + counts |
| GET  | `/api/recommendations/latest` | Recommended stocks from latest scan |
| GET  | `/api/recommendations/latest/all` | All symbols from latest scan (debug) |
| GET  | `/api/symbol/{symbol}/details` | Detailed data for chart modal |

## Architecture

- **google_finance.py** – scrapes fundamentals from Google Finance; falls back to Yahoo Finance for historical prices only
- **indicators.py** – RSI(14), MACD(12,26,9), SMA(20) calculations
- **scanner.py** – orchestrates data fetching and recommendation logic
- **models.py** – SQLAlchemy ORM (SQLite)
- **db.py** – engine/session management
