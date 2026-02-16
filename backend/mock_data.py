"""
Mock data provider for offline / corporate-firewall environments.

Generates realistic Indian stock fundamentals and 9-month daily price
histories for the symbols in symbols.txt.  Two stocks (NMDC and WIPRO)
are given price patterns that trigger the "oversold reversal" screening
rule, so the UI has something meaningful to display.

The data is deterministic (seeded RNG) – the same symbols always produce
the same prices, making debugging reproducible.
"""

from __future__ import annotations

import hashlib
import logging
import math
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from google_finance import FundamentalData, PriceBar

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Static fundamental info for well-known NSE stocks
# ──────────────────────────────────────────────

_FUNDAMENTALS: Dict[str, dict] = {
    "TCS": dict(name="Tata Consultancy Services", cmp=3852.40, pe=28.54,
                roce=52.3, bv=285.20, debt=12000.0, industry="IT Services"),
    "INFY": dict(name="Infosys Limited", cmp=1523.75, pe=25.18,
                 roce=36.82, bv=220.45, debt=3800.0, industry="IT Services"),
    "NMDC": dict(name="NMDC Limited", cmp=127.30, pe=8.42,
                 roce=22.10, bv=95.60, debt=4200.0, industry="Mining & Minerals"),
    "TECHM": dict(name="Tech Mahindra Limited", cmp=1342.90, pe=32.05,
                  roce=14.50, bv=380.10, debt=9100.0, industry="IT Services"),
    "WIPRO": dict(name="Wipro Limited", cmp=452.15, pe=22.78,
                  roce=18.92, bv=130.80, debt=6200.0, industry="IT Services"),
}

# Default template for unknown symbols
_DEFAULT_FUNDAMENTAL = dict(name=None, cmp=500.0, pe=18.0,
                            roce=15.0, bv=120.0, debt=2500.0, industry="General")


def _seeded_rng(symbol: str, seed_extra: str = "") -> random.Random:
    """Return a Random instance seeded deterministically by symbol."""
    h = hashlib.md5(f"{symbol}:{seed_extra}".encode()).hexdigest()
    return random.Random(int(h, 16))


# ──────────────────────────────────────────────
# Price-series generators
# ──────────────────────────────────────────────

def _business_days(n: int, end: Optional[datetime] = None) -> List[str]:
    """Return *n* business-day date strings ending near *end*."""
    if end is None:
        end = datetime.utcnow()
    dates: List[str] = []
    d = end
    while len(dates) < n:
        if d.weekday() < 5:  # Mon-Fri
            dates.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    dates.reverse()
    return dates


def _generate_normal_series(
    rng: random.Random,
    base_price: float,
    n: int = 180,
    daily_vol: float = 0.012,
    drift: float = 0.0002,
) -> List[float]:
    """Simple geometric Brownian motion walk."""
    prices = [base_price]
    for _ in range(n - 1):
        ret = drift + daily_vol * rng.gauss(0, 1)
        prices.append(round(prices[-1] * (1 + ret), 2))
    return prices


def _generate_oversold_recovery(
    rng: random.Random,
    base_price: float,
    n: int = 180,
    dip_start_frac: float = 0.80,   # where dip begins (fraction of series)
    dip_depth: float = 0.18,         # % decline from local high
    recovery_days: int = 8,          # days of recovery after bottom
) -> List[float]:
    """
    Generate a price series that:
      1. Trends mildly up/flat for most of the period
      2. Drops sharply near the end (creating RSI < 30)
      3. Recovers for a few days (MACD crossover + RSI rising)

    This ensures the screening rule triggers.
    """
    dip_idx = int(n * dip_start_frac)
    normal_len = dip_idx
    dip_len = n - dip_idx - recovery_days
    if dip_len < 5:
        dip_len = 5
        recovery_days = n - dip_idx - dip_len

    # Phase 1: gentle uptrend
    prices = _generate_normal_series(rng, base_price, normal_len,
                                     daily_vol=0.008, drift=0.0003)
    peak = prices[-1]

    # Phase 2: sharp decline
    target_bottom = peak * (1 - dip_depth)
    daily_drop = (peak - target_bottom) / dip_len
    for i in range(dip_len):
        noise = rng.gauss(0, daily_drop * 0.15)
        prices.append(round(prices[-1] - daily_drop + noise, 2))

    bottom = prices[-1]

    # Phase 3: recovery (bounce)
    daily_bounce = (peak - bottom) * 0.35 / recovery_days
    for i in range(recovery_days):
        # Accelerating bounce
        factor = 1 + (i / recovery_days) * 0.5
        noise = rng.gauss(0, daily_bounce * 0.2)
        prices.append(round(prices[-1] + daily_bounce * factor + noise, 2))

    # Ensure exactly n bars
    while len(prices) < n:
        prices.append(round(prices[-1] * (1 + rng.gauss(0, 0.005)), 2))
    prices = prices[:n]

    return prices


# ──────────────────────────────────────────────
# Public API (mirrors google_finance signatures)
# ──────────────────────────────────────────────

def mock_fundamentals(symbol: str) -> FundamentalData:
    """Return mock fundamental data for *symbol*."""
    info = _FUNDAMENTALS.get(symbol.upper(), _DEFAULT_FUNDAMENTAL).copy()
    # If unknown symbol, use symbol as name
    if info["name"] is None:
        info["name"] = f"{symbol} (mock)"
    fd = FundamentalData(
        symbol=symbol,
        name=info["name"],
        cmp=info["cmp"],
        pe=info["pe"],
        roce=info["roce"],
        bv=info["bv"],
        debt=info["debt"],
        industry=info["industry"],
    )
    logger.info("[%s] ★ Using MOCK fundamentals: name=%s cmp=%.2f pe=%.2f debt=%.2f",
                symbol, fd.name, fd.cmp or 0, fd.pe or 0, fd.debt or 0)
    return fd


def mock_price_history(symbol: str, months: int = 9) -> List[PriceBar]:
    """
    Return mock daily price bars for approximately *months* months.
    NMDC and WIPRO get oversold-recovery patterns; others get normal walks.
    """
    n = months * 22  # ~22 trading days per month
    if n < 60:
        n = 60
    dates = _business_days(n)
    rng = _seeded_rng(symbol, "prices")

    base_info = _FUNDAMENTALS.get(symbol.upper(), _DEFAULT_FUNDAMENTAL)
    base_price = base_info["cmp"] * 0.92   # start ~8% below current mock CMP

    sym_upper = symbol.upper()

    # Symbols that get oversold-recovery patterns
    if sym_upper == "NMDC":
        closes = _generate_oversold_recovery(
            rng, base_price, n,
            dip_start_frac=0.78, dip_depth=0.22, recovery_days=6,
        )
    elif sym_upper == "WIPRO":
        closes = _generate_oversold_recovery(
            rng, base_price, n,
            dip_start_frac=0.82, dip_depth=0.16, recovery_days=10,
        )
    else:
        closes = _generate_normal_series(
            rng, base_price, n,
            daily_vol=0.012, drift=0.0002,
        )

    bars = [PriceBar(date=d, close=c) for d, c in zip(dates, closes)]
    logger.info(
        "[%s] ★ Using MOCK price history: %d bars  range %s → %s  last_close=%.2f",
        symbol, len(bars), bars[0].date, bars[-1].date, bars[-1].close,
    )
    return bars
