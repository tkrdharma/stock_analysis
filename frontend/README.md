# Frontend – Oversold Reversal Stock Screener

React + Vite single-page dashboard.

## Quick start

```bash
cd frontend
npm install
npm run dev
```

Opens on **http://localhost:5173**.

The Vite dev server proxies `/api` requests to `http://localhost:8000` (the FastAPI backend).

## Components

| Component | Description |
|-----------|-------------|
| `ScanControls` | Reload symbols + Run Scan buttons, scan status display |
| `RecommendationsTable` | Sortable, searchable table of screened stocks |
| `StockDetailsModal` | Detail drawer with fundamentals, technicals, signals, charts |
| `PriceChart` | Recharts-based line/bar charts for Price, RSI, MACD |
