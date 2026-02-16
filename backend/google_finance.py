"""
Google Finance scraper for fundamentals + historical price data.

Fundamentals (Stock Name, CMP, PE, ROCE, BV, Industry) are scraped from
Google Finance pages using httpx + BeautifulSoup4.

Historical daily prices: Google Finance embeds limited chart data in the page.
We attempt to extract it.  When that fails, we fall back to **Yahoo Finance**
(yfinance library) which reliably provides OHLCV history.  Only historical
prices use the fallback – fundamentals always come from Google Finance.

The module is designed for robustness:
  • Retry with exponential back‑off (3 attempts)
  • Throttling via asyncio.Semaphore (shared by caller)
  • Missing fields → None  (displayed as N/A in the UI)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import httpx
from bs4 import BeautifulSoup

# Suppress InsecureRequestWarning when verify=False
import warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Network connectivity check (cached per process)
# ──────────────────────────────────────────────

_network_available: Optional[bool] = None


async def _check_network(client: httpx.AsyncClient) -> bool:
    """Quick check if we can reach Google Finance.  Result cached."""
    global _network_available
    if _network_available is not None:
        return _network_available
    try:
        logger.info("Checking network connectivity (3s timeout)...")
        resp = await client.get(
            "https://www.google.com/finance/",
            headers=_HEADERS, timeout=5, follow_redirects=True,
        )
        _network_available = resp.status_code == 200
        logger.info("Network check: %s (HTTP %s)", "OK" if _network_available else "FAIL", resp.status_code)
    except Exception as exc:
        _network_available = False
        logger.warning("Network check FAILED (%s) → will use mock data", type(exc).__name__)
    return _network_available


# ──────────────────────────────────────────────
# Data containers
# ──────────────────────────────────────────────

@dataclass
class FundamentalData:
    symbol: str
    name: Optional[str] = None
    cmp: Optional[float] = None
    pe: Optional[float] = None
    roce: Optional[float] = None
    bv: Optional[float] = None
    debt: Optional[float] = None
    industry: Optional[str] = None


@dataclass
class PriceBar:
    date: str          # "YYYY-MM-DD"
    close: float


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Google Finance URL for NSE‑listed Indian stocks.  Adjust exchange prefix as
# needed.  We try NSE first, then plain symbol.
_GF_URL_TEMPLATES = [
    "https://www.google.com/finance/quote/{symbol}:NSE",
    "https://www.google.com/finance/quote/{symbol}:BOM",
    "https://www.google.com/finance/quote/{symbol}",
]


def _safe_float(text: Optional[str]) -> Optional[float]:
    """Parse a float from a potentially messy string (commas, currency symbols)."""
    if text is None:
        return None
    text = text.strip().replace(",", "").replace("₹", "").replace("$", "").replace("%", "")
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


async def _fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    retries: int = 2,
    backoff: float = 0.5,
) -> Optional[httpx.Response]:
    """GET *url* with exponential back‑off.  Returns None on final failure."""
    for attempt in range(retries):
        try:
            logger.debug("  HTTP GET %s (attempt %d/%d)", url, attempt + 1, retries)
            resp = await client.get(url, headers=_HEADERS, follow_redirects=True, timeout=8)
            if resp.status_code == 200:
                logger.debug("  HTTP 200 OK for %s (%d bytes)", url, len(resp.content))
                return resp
            logger.warning("HTTP %s for %s (attempt %d)", resp.status_code, url, attempt + 1)
        except (httpx.RequestError, httpx.TimeoutException) as exc:
            logger.warning(
                "Request error for %s (attempt %d): [%s] %s",
                url, attempt + 1, type(exc).__name__, exc,
            )
        wait = backoff * (2 ** attempt)
        logger.debug("  Waiting %.1fs before retry...", wait)
        await asyncio.sleep(wait)
    logger.error("ALL %d retries FAILED for %s", retries, url)
    return None


# ──────────────────────────────────────────────
# Fundamental data scraping from Google Finance
# ──────────────────────────────────────────────

async def fetch_fundamentals(
    symbol: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> FundamentalData:
    """Scrape fundamental fields from Google Finance for *symbol*."""
    async with semaphore:
        # Fast-path: if network already known-bad, go straight to mock
        if not await _check_network(client):
            logger.info("[%s] Network unavailable → using mock fundamentals", symbol)
            from mock_data import mock_fundamentals
            return mock_fundamentals(symbol)

        fd = FundamentalData(symbol=symbol)
        logger.info("[%s] Fetching fundamentals from Google Finance...", symbol)

        matched_url = None
        for tmpl in _GF_URL_TEMPLATES:
            url = tmpl.format(symbol=symbol)
            logger.debug("[%s]   Trying URL: %s", symbol, url)
            resp = await _fetch_with_retry(client, url)
            if resp is not None:
                matched_url = url
                logger.debug("[%s]   ✓ Got HTTP 200 from %s (body=%d bytes)", symbol, url, len(resp.text))
                break
        else:
            logger.error("[%s] ✗ All Google Finance URLs failed → using mock data", symbol)
            from mock_data import mock_fundamentals
            return mock_fundamentals(symbol)

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Stock Name ---
        # Google Finance renders the company name in a <div class="zzDege"> or
        # in the page title.
        name_tag = soup.select_one("div.zzDege")
        if name_tag:
            fd.name = name_tag.get_text(strip=True)
        else:
            title = soup.title
            if title:
                # title is like "TCS Share Price - Tata Consultancy Services ..."
                parts = title.get_text().split("-")
                if len(parts) > 1:
                    fd.name = parts[1].strip().split("Stock")[0].strip()
                else:
                    fd.name = parts[0].strip()

        # --- CMP (current market price) ---
        price_tag = soup.select_one("div.YMlKec.fxKbKc")
        if price_tag:
            fd.cmp = _safe_float(price_tag.get_text())
        else:
            # alternative selector
            price_tag = soup.select_one("[data-last-price]")
            if price_tag:
                fd.cmp = _safe_float(price_tag.get("data-last-price"))

        # --- Structured key–value pairs (PE, Industry, etc.) ---
        # Google Finance shows "About" section with rows like
        #   <div class="mfs7Fc"><div class="...">P/E ratio</div><div class="...">28.34</div></div>
        kv_rows = soup.select("div.gyFHrc")
        kv: dict[str, str] = {}
        for row in kv_rows:
            cols = row.select("div")
            if len(cols) >= 2:
                key = cols[0].get_text(strip=True).lower()
                val = cols[-1].get_text(strip=True)
                kv[key] = val

        # Also try table rows
        table_rows = soup.select("table tr")
        for row in table_rows:
            cells = row.select("td")
            if len(cells) >= 2:
                key = cells[0].get_text(strip=True).lower()
                val = cells[-1].get_text(strip=True)
                kv[key] = val

        fd.pe = _safe_float(kv.get("p/e ratio") or kv.get("pe ratio") or kv.get("p/e"))
        fd.bv = _safe_float(kv.get("book value") or kv.get("book value per share"))
        fd.roce = _safe_float(kv.get("roce") or kv.get("return on capital employed"))
        fd.debt = _safe_float(kv.get("total debt") or kv.get("debt") or kv.get("net debt"))

        # Industry / Sector
        industry_tag = soup.select_one("a.py3Ok")
        if industry_tag:
            fd.industry = industry_tag.get_text(strip=True)
        else:
            fd.industry = kv.get("industry") or kv.get("sector")

        logger.info(
            "[%s] Fundamentals scraped → name=%s  cmp=%s  pe=%s  roce=%s  bv=%s  debt=%s  industry=%s",
            symbol, fd.name, fd.cmp, fd.pe, fd.roce, fd.bv, fd.debt, fd.industry,
        )
        if not fd.cmp:
            logger.warning("[%s] ⚠ CMP is None – price selector may have changed", symbol)
        # Throttle politely
        await asyncio.sleep(0.3)
        return fd


# ──────────────────────────────────────────────
# Historical price data
# ──────────────────────────────────────────────

async def fetch_price_history_google(
    symbol: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    months: int = 9,
) -> List[PriceBar]:
    """
    Try to extract daily close prices from the Google Finance page.
    Google embeds chart data as JSON in the page source for ~6 months.
    Returns empty list if extraction fails.
    """
    async with semaphore:
        # Fast-path: if network already known-bad, return empty → caller falls to mock
        if not await _check_network(client):
            logger.info("[%s] Network unavailable → skipping Google chart fetch", symbol)
            return []

        logger.info("[%s] Fetching price history from Google Finance...", symbol)
        for tmpl in _GF_URL_TEMPLATES:
            url = tmpl.format(symbol=symbol)
            resp = await _fetch_with_retry(client, url)
            if resp is not None:
                logger.debug("[%s] Got chart page from %s (%d bytes)", symbol, url, len(resp.text))
                break
        else:
            logger.warning("[%s] ✗ All Google Finance chart URLs failed", symbol)
            return []

        bars: List[PriceBar] = []
        try:
            # Google Finance embeds chart data in a JS variable.
            # Look for patterns like: data:[[...],[...]] or similar JSON arrays
            # containing timestamp/price pairs.
            text = resp.text

            # Pattern 1: Look for price arrays in embedded JSON
            # Google uses patterns like [timestamp, close_price]
            json_patterns = re.findall(
                r'\[\[(\d{10,13}),[\d.]+,[\d.]+,[\d.]+,([\d.]+)\]',
                text
            )
            if json_patterns:
                for ts_str, close_str in json_patterns:
                    ts = int(ts_str)
                    if ts > 1e12:
                        ts = ts // 1000
                    dt = datetime.utcfromtimestamp(ts)
                    bars.append(PriceBar(date=dt.strftime("%Y-%m-%d"), close=float(close_str)))

            if not bars:
                # Pattern 2: Look for data in script tags
                scripts = BeautifulSoup(text, "html.parser").find_all("script")
                for script in scripts:
                    script_text = script.string or ""
                    # Look for arrays with price data
                    matches = re.findall(
                        r'"(\d{4}-\d{2}-\d{2})"[^}]*?"close":\s*([\d.]+)',
                        script_text,
                        re.DOTALL
                    )
                    for date_str, close_str in matches:
                        bars.append(PriceBar(date=date_str, close=float(close_str)))

        except Exception as exc:
            logger.warning("[%s] Failed to parse Google Finance chart data: %s", symbol, exc)

        logger.info("[%s] Google chart extraction → %d bars", symbol, len(bars))
        if bars:
            logger.debug("[%s]   date range: %s → %s", symbol, bars[0].date, bars[-1].date)
        await asyncio.sleep(0.2)
        return bars


def fetch_price_history_yahoo_sync(
    symbol: str,
    months: int = 9,
) -> List[PriceBar]:
    """
    FALLBACK: Fetch daily close prices from Yahoo Finance using yfinance.
    This is used only when Google Finance chart data extraction fails.
    Fundamentals always come from Google Finance.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed – cannot fetch history for %s", symbol)
        return []

    # For Indian NSE stocks, yfinance expects ".NS" suffix
    suffixes = [".NS", ".BO", ""]
    bars: List[PriceBar] = []

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=months * 30)

    for suffix in suffixes:
        ticker_str = f"{symbol}{suffix}"
        logger.debug("[%s] Yahoo: trying ticker '%s'  range %s → %s", symbol, ticker_str, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
        try:
            ticker = yf.Ticker(ticker_str)
            df = ticker.history(start=start_date.strftime("%Y-%m-%d"),
                                end=end_date.strftime("%Y-%m-%d"))
            row_count = len(df) if df is not None else 0
            logger.debug("[%s] Yahoo '%s' returned %d rows", symbol, ticker_str, row_count)
            if df is not None and row_count >= 20:
                for idx, row in df.iterrows():
                    bars.append(PriceBar(
                        date=idx.strftime("%Y-%m-%d"),
                        close=float(row["Close"]),
                    ))
                logger.info("[%s] ✓ Yahoo fallback: %d bars for '%s'", symbol, len(bars), ticker_str)
                return bars
            else:
                logger.debug("[%s] Yahoo '%s' → only %d rows (need ≥20), skipping", symbol, ticker_str, row_count)
        except Exception as exc:
            logger.warning("[%s] Yahoo '%s' exception: %s", symbol, ticker_str, exc)
            continue

    logger.error("[%s] ✗ Yahoo fallback FAILED for all suffixes %s", symbol, suffixes)
    return bars


async def fetch_price_history(
    symbol: str,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    months: int = 9,
) -> List[PriceBar]:
    """
    Attempts Google Finance first; falls back to Yahoo Finance for historical
    prices only.  Returns list of PriceBar sorted by date ascending.
    """
    bars = await fetch_price_history_google(symbol, client, semaphore, months)
    if len(bars) >= 60:
        bars.sort(key=lambda b: b.date)
        logger.info("[%s] ✓ Using Google Finance history: %d bars", symbol, len(bars))
        return bars

    logger.info(
        "[%s] Google chart data insufficient (%d bars < 60) → falling back to Yahoo Finance",
        symbol, len(bars),
    )

    # Skip Yahoo if network is known-dead
    if not await _check_network(client):
        logger.info("[%s] Network unavailable → skipping Yahoo, using mock data", symbol)
        from mock_data import mock_price_history
        return mock_price_history(symbol, months)

    # Run synchronous yfinance in a thread to not block the event loop
    loop = asyncio.get_event_loop()
    try:
        bars = await loop.run_in_executor(None, fetch_price_history_yahoo_sync, symbol, months)
    except Exception as exc:
        logger.warning("[%s] Yahoo fallback exception: %s", symbol, exc)
        bars = []

    if bars:
        bars.sort(key=lambda b: b.date)
        logger.info("[%s] Yahoo Finance fallback → %d bars", symbol, len(bars))
        logger.debug("[%s]   date range: %s → %s  last_close=%.2f", symbol, bars[0].date, bars[-1].date, bars[-1].close)
        return bars

    # Both Google + Yahoo failed → use mock data
    logger.warning("[%s] Both Google and Yahoo failed → using mock price data", symbol)
    from mock_data import mock_price_history
    bars = mock_price_history(symbol, months)
    return bars
