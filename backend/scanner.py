"""
Screening engine – evaluates every symbol and generates recommendations.

Recommendation rule (exact):
  1. RSI(14) < 30   (oversold)
  AND at least one reversal confirmation:
    a) Bullish MACD crossover within last 5 trading days
    b) Close crossed above SMA(20) within last 5 trading days
    c) RSI has risen for 3 consecutive days (momentum reversal)

Score:
  +3  MACD crossover
  +2  SMA20 bullish cross
  +1  RSI rising 3 days
   bonus: min(30 − RSI, 5)
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import httpx

from google_finance import (
    FundamentalData,
    PriceBar,
    fetch_fundamentals,
    fetch_price_history,
)
from indicators import rsi, macd, sma, MACDResult
from models import Symbol

logger = logging.getLogger(__name__)

CONCURRENCY_LIMIT = 8  # max parallel HTTP requests


# ──────────────────────────────────────────────
# Signal detection helpers
# ──────────────────────────────────────────────

def _detect_signals(
    closes: List[float],
    rsi_series: List[Optional[float]],
    macd_result: MACDResult,
    sma20_series: List[Optional[float]],
    lookback: int = 5,
) -> Dict:
    """Return dict describing which signals fired."""
    n = len(closes)
    signals = {
        "rsi_oversold": False,
        "macd_crossover": False,
        "sma20_cross": False,
        "rsi_rising_3d": False,
        "rsi_divergence": False,
        "macd_divergence": False,
        "latest_rsi": None,
        "latest_macd": None,
        "latest_signal": None,
        "latest_sma20": None,
        "latest_close": closes[-1] if closes else None,
    }

    # Latest RSI
    latest_rsi_val = None
    for v in reversed(rsi_series):
        if v is not None:
            latest_rsi_val = round(v, 2)
            break
    signals["latest_rsi"] = latest_rsi_val

    # Latest MACD / Signal
    for v in reversed(macd_result.macd_line):
        if v is not None:
            signals["latest_macd"] = round(v, 4)
            break
    for v in reversed(macd_result.signal_line):
        if v is not None:
            signals["latest_signal"] = round(v, 4)
            break

    # Latest SMA20
    for v in reversed(sma20_series):
        if v is not None:
            signals["latest_sma20"] = round(v, 2)
            break

    if latest_rsi_val is None:
        return signals

    # 1. RSI < 30  (check any of last *lookback* days)
    recent_rsi = [v for v in rsi_series[-lookback:] if v is not None]
    if recent_rsi and min(recent_rsi) < 30:
        signals["rsi_oversold"] = True

    # 2a. Bullish MACD crossover within last *lookback* days
    ml = macd_result.macd_line
    sl = macd_result.signal_line
    for i in range(max(1, n - lookback), n):
        if (
            ml[i] is not None and sl[i] is not None
            and ml[i - 1] is not None and sl[i - 1] is not None
        ):
            if ml[i - 1] <= sl[i - 1] and ml[i] > sl[i]:
                signals["macd_crossover"] = True
                break

    # 2b. Close crossed above SMA20 within last *lookback* days
    for i in range(max(1, n - lookback), n):
        if sma20_series[i] is not None and sma20_series[i - 1] is not None:
            if closes[i - 1] <= sma20_series[i - 1] and closes[i] > sma20_series[i]:
                signals["sma20_cross"] = True
                break

    # 2c. RSI rising for 3 consecutive days (ending at most recent)
    recent_rsi_vals = [v for v in rsi_series[-(3 + 1):] if v is not None]
    if len(recent_rsi_vals) >= 3:
        tail = recent_rsi_vals[-3:]
        if tail[0] < tail[1] < tail[2]:
            signals["rsi_rising_3d"] = True

    # 3. Divergence in last *lookback* days (bullish)
    # Price makes a lower low, indicator makes a higher low.
    if n >= lookback * 2:
        recent_prices = closes[-lookback:]
        prev_prices = closes[-(lookback * 2):-lookback]

        recent_low = min(recent_prices) if recent_prices else None
        prev_low = min(prev_prices) if prev_prices else None

        recent_rsi = [v for v in rsi_series[-lookback:] if v is not None]
        prev_rsi = [v for v in rsi_series[-(lookback * 2):-lookback] if v is not None]
        recent_rsi_low = min(recent_rsi) if recent_rsi else None
        prev_rsi_low = min(prev_rsi) if prev_rsi else None

        recent_macd = [v for v in macd_result.macd_line[-lookback:] if v is not None]
        prev_macd = [v for v in macd_result.macd_line[-(lookback * 2):-lookback] if v is not None]
        recent_macd_low = min(recent_macd) if recent_macd else None
        prev_macd_low = min(prev_macd) if prev_macd else None

        if (
            recent_low is not None
            and prev_low is not None
            and recent_low < prev_low
            and recent_rsi_low is not None
            and prev_rsi_low is not None
            and recent_rsi_low > prev_rsi_low
        ):
            signals["rsi_divergence"] = True

        if (
            recent_low is not None
            and prev_low is not None
            and recent_low < prev_low
            and recent_macd_low is not None
            and prev_macd_low is not None
            and recent_macd_low > prev_macd_low
        ):
            signals["macd_divergence"] = True

    return signals


def _score_and_reason(signals: Dict) -> Tuple[float, bool, str]:
    """Compute score, recommended bool, and reason string."""
    if not signals["rsi_oversold"]:
        return 0.0, False, ""

    has_confirmation = (
        signals["macd_crossover"]
        or signals["sma20_cross"]
        or signals["rsi_rising_3d"]
        or signals["rsi_divergence"]
        or signals["macd_divergence"]
    )

    if not has_confirmation:
        return 0.0, False, ""

    score = 0.0
    reasons: List[str] = []

    rsi_val = signals["latest_rsi"]
    reasons.append(f"RSI(14)={rsi_val} (oversold)")

    if signals["macd_crossover"]:
        score += 3
        reasons.append("bullish MACD crossover")
    if signals["sma20_cross"]:
        score += 2
        reasons.append("close crossed above SMA20")
    if signals["rsi_rising_3d"]:
        score += 1
        reasons.append("RSI rising 3 consecutive days")
    if signals["rsi_divergence"]:
        score += 1
        reasons.append("RSI bullish divergence (5d)")
    if signals["macd_divergence"]:
        score += 2
        reasons.append("MACD bullish divergence (5d)")

    # Bonus: (30 - RSI) capped at 5
    if rsi_val is not None:
        bonus = min(30 - rsi_val, 5)
        if bonus > 0:
            score += bonus

    reason_str = " + ".join(reasons)
    return round(score, 2), True, reason_str


# ──────────────────────────────────────────────
# Per-symbol processing
# ──────────────────────────────────────────────

async def _process_symbol(
    symbol_row: Symbol,
    scan_id: int,
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
) -> Dict:
    """Fetch data + compute indicators for one symbol. Returns result dict."""
    sym = symbol_row.symbol
    result: Dict = {
        "symbol": sym,
        "symbol_id": symbol_row.id,
        "error": None,
        "status": "ok",
    }
    logger.info("──── Processing %s (id=%d) ────", sym, symbol_row.id)

    try:
        # Fetch fundamentals and price history concurrently
        logger.debug("[%s] Starting concurrent fetch: fundamentals + price history", sym)
        fund_task = fetch_fundamentals(sym, client, semaphore)
        hist_task = fetch_price_history(sym, client, semaphore)
        fund_data, price_bars = await asyncio.gather(fund_task, hist_task)

        result["fundamentals"] = fund_data
        logger.info("[%s] Data fetched: fundamentals.name=%s  price_bars=%d", sym, fund_data.name, len(price_bars))

        if len(price_bars) < 30:
            msg = f"Insufficient price data ({len(price_bars)} bars, need ≥30)"
            logger.warning("[%s] ⚠ %s", sym, msg)
            result["error"] = msg
            result["status"] = "ignored"
            result["price_bars"] = price_bars
            result["signals"] = {}
            result["score"] = 0.0
            result["recommended"] = False
            result["reason"] = "Insufficient data"
            return result

        closes = [b.close for b in price_bars]
        logger.debug("[%s] Computing indicators on %d closes (last=%.2f)", sym, len(closes), closes[-1])

        rsi_series = rsi(closes)
        macd_result = macd(closes)
        sma20_series = sma(closes, 20)

        signals = _detect_signals(closes, rsi_series, macd_result, sma20_series)
        score, recommended, reason = _score_and_reason(signals)

        logger.info(
            "[%s] Indicators → RSI=%.2f  MACD=%.4f  Signal=%.4f  SMA20=%.2f  Close=%.2f",
            sym,
            signals.get('latest_rsi') or 0,
            signals.get('latest_macd') or 0,
            signals.get('latest_signal') or 0,
            signals.get('latest_sma20') or 0,
            signals.get('latest_close') or 0,
        )
        logger.info(
            "[%s] Signals → rsi_oversold=%s  macd_crossover=%s  sma20_cross=%s  rsi_rising_3d=%s  rsi_divergence=%s  macd_divergence=%s",
            sym,
            signals.get('rsi_oversold'),
            signals.get('macd_crossover'),
            signals.get('sma20_cross'),
            signals.get('rsi_rising_3d'),
            signals.get('rsi_divergence'),
            signals.get('macd_divergence'),
        )
        if recommended:
            logger.info("[%s] ★ RECOMMENDED  score=%.2f  reason='%s'", sym, score, reason)
        else:
            logger.info("[%s] · Not recommended (score=%.2f)", sym, score)

        result["price_bars"] = price_bars
        result["closes"] = closes
        result["rsi_series"] = rsi_series
        result["macd_result"] = macd_result
        result["sma20_series"] = sma20_series
        result["signals"] = signals
        result["score"] = score
        result["recommended"] = recommended
        result["reason"] = reason

    except Exception as exc:
        logger.exception("[%s] ✗ EXCEPTION during processing: %s", sym, exc)
        result["error"] = str(exc)
        result["status"] = "error"
        result["signals"] = {}
        result["score"] = 0.0
        result["recommended"] = False
        result["reason"] = ""

    logger.debug("[%s] _process_symbol done", sym)
    return result
