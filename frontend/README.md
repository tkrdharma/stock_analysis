# Frontend – Oversold Reversal Stock Screener

React + Vite single-page dashboard for viewing screened stocks, detailed charts, and managing scans.

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Node.js     | 18+     |
| npm          | 9+      |

## Installation

```bash
# 1. Navigate to frontend folder
cd frontend

# 2. Install dependencies
npm install
```

### Dependencies

| Package          | Purpose                                |
|------------------|----------------------------------------|
| react / react-dom | UI framework                          |
| axios            | HTTP client for API calls              |
| recharts         | Charting library (Price, RSI, MACD)    |
| vite             | Dev server + build tool                |
| @vitejs/plugin-react | React fast-refresh for Vite        |

## Running (Development)

```bash
npm run dev
```

- Opens on **http://localhost:5173** (or next available port if 5173 is busy)
- The Vite dev server proxies all `/api/*` requests to `http://localhost:8000` (the FastAPI backend)
- Hot Module Replacement (HMR) is enabled — edits auto-refresh in the browser

> **Important:** The backend must be running on port 8000 before the frontend can fetch data.

## Building for Production

```bash
npm run build
```

Output is written to `dist/`. Serve with any static file server or configure a reverse proxy.

```bash
# Preview the production build locally
npm run preview
```

## Project Structure

```
frontend/
├── index.html               # Entry HTML
├── vite.config.js           # Vite config (proxy, port)
├── package.json             # Dependencies + scripts
└── src/
    ├── main.jsx             # React entry point
    ├── App.jsx              # Main app component (state, polling, routing)
    ├── api.js               # Axios API helpers (all backend calls)
    ├── index.css            # Global styles (dark theme, progress bar, table, modal)
    └── components/
        ├── ScanControls.jsx        # Reload symbols, Run Scan, Delete All buttons + progress bar
        ├── RecommendationsTable.jsx # Sortable, searchable, paginated stock table
        ├── StockDetailsModal.jsx    # Detail drawer: fundamentals, technicals, signals, charts
        └── PriceChart.jsx           # Recharts line/bar charts (Price, RSI, MACD)
```

## Features

- **Scan progress bar** — live animated progress with symbol count, current symbol, and error tracking
- **Sortable & searchable table** — click column headers to sort; type to filter by symbol
- **Pagination** — 10 / 25 / 50 / 100 rows per page
- **Detail modal** — click any row to see fundamentals, technicals, triggered signals, and interactive charts
- **RSI / MACD divergence columns** — shows "Bullish" or "Bearing" status
- **Delete per-row / Delete all** — manage scan results directly from the UI
- **Page-load recovery** — if you refresh during a scan, the progress bar automatically resumes

## Configuration

The proxy target can be changed in `vite.config.js`:

```js
proxy: {
  '/api': {
    target: 'http://localhost:8000',  // ← change if backend runs elsewhere
    changeOrigin: true,
  },
}
```
