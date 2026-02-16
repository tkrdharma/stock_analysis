# Oversold Reversal Stock Screener - Setup Guide

This guide explains how to run the app in a new environment.

## Requirements

- Windows 10/11 (or macOS/Linux)
- Python 3.11+
- Node.js 18+ (npm included)

## Repo Layout

- backend/  FastAPI + SQLite
- frontend/ React + Vite
- symbols.txt  Stock universe list

## Backend Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Backend runs at: http://localhost:8000

Useful endpoints:
- POST /api/symbols/reload
- POST /api/scan/run
- GET  /api/recommendations/latest
- GET  /api/recommendations/latest/all
- GET  /api/scan/latest/logs
- DELETE /api/scan/latest/symbol/{SYMBOL}

SQLite DB:
- backend/stock_screener.db

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173 (or next available port)

## First Run

1. Start backend
2. Start frontend
3. Click "Reload symbols.txt"
4. Click "Run Scan"

## Network and Data Sources

The app tries Google Finance and Yahoo Finance. If the network blocks outbound HTTPS,
it automatically falls back to deterministic mock data (for demo/dev use).

If your environment requires a proxy, set standard variables before starting:

```
set HTTPS_PROXY=http://proxy.host:8080
set HTTP_PROXY=http://proxy.host:8080
```

## Resetting Data

To start fresh:

```bash
del backend\stock_screener.db
```

Restart the backend after deleting the DB.

## Troubleshooting

- If the UI shows "Unable to connect":
  - Confirm backend is running on port 8000
  - Confirm frontend is running (5173/5174/5175)
- If scans are slow:
  - Network might be blocking data sources; mock data will be used
- If ports are in use:
  - Stop old dev servers or choose another port
