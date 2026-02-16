"""
Technical indicator calculations: RSI(14), MACD(12,26,9), SMA(20).

All functions accept a list of floats (daily closing prices, oldest‑first)
and return computed series or scalar values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple


# ──────────────────────────────────────────────
# SMA – Simple Moving Average
# ──────────────────────────────────────────────

def sma(closes: List[float], period: int) -> List[Optional[float]]:
    """Return SMA series (same length as *closes*).  First *period‑1* values are None."""
    result: List[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return result
    window_sum = sum(closes[:period])
    result[period - 1] = window_sum / period
    for i in range(period, len(closes)):
        window_sum += closes[i] - closes[i - period]
        result[i] = window_sum / period
    return result


# ──────────────────────────────────────────────
# EMA – Exponential Moving Average (helper)
# ──────────────────────────────────────────────

def ema(closes: List[float], period: int) -> List[Optional[float]]:
    """Return EMA series.  Uses SMA as seed for first valid value."""
    result: List[Optional[float]] = [None] * len(closes)
    if len(closes) < period:
        return result
    k = 2.0 / (period + 1)
    # seed with SMA
    seed = sum(closes[:period]) / period
    result[period - 1] = seed
    for i in range(period, len(closes)):
        result[i] = closes[i] * k + result[i - 1] * (1 - k)
    return result


# ──────────────────────────────────────────────
# RSI – Relative Strength Index (Wilder smooth)
# ──────────────────────────────────────────────

def rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder‑smoothed RSI.  First *period* values are None."""
    result: List[Optional[float]] = [None] * len(closes)
    if len(closes) <= period:
        return result

    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100.0 - 100.0 / (1.0 + rs)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            result[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i + 1] = 100.0 - 100.0 / (1.0 + rs)

    return result


# ──────────────────────────────────────────────
# MACD
# ──────────────────────────────────────────────

@dataclass
class MACDResult:
    macd_line: List[Optional[float]]
    signal_line: List[Optional[float]]
    histogram: List[Optional[float]]


def macd(
    closes: List[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> MACDResult:
    """Compute MACD line, signal line, and histogram."""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)

    n = len(closes)
    macd_line: List[Optional[float]] = [None] * n
    for i in range(n):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            macd_line[i] = ema_fast[i] - ema_slow[i]

    # Signal line = EMA of MACD line
    # Collect non‑None MACD values for computing signal EMA
    valid_macd: List[Tuple[int, float]] = [
        (i, v) for i, v in enumerate(macd_line) if v is not None
    ]

    signal_line: List[Optional[float]] = [None] * n
    if len(valid_macd) >= signal_period:
        k = 2.0 / (signal_period + 1)
        seed = sum(v for _, v in valid_macd[:signal_period]) / signal_period
        signal_line[valid_macd[signal_period - 1][0]] = seed
        prev = seed
        for j in range(signal_period, len(valid_macd)):
            idx, val = valid_macd[j]
            cur = val * k + prev * (1 - k)
            signal_line[idx] = cur
            prev = cur

    histogram: List[Optional[float]] = [None] * n
    for i in range(n):
        if macd_line[i] is not None and signal_line[i] is not None:
            histogram[i] = macd_line[i] - signal_line[i]

    return MACDResult(macd_line=macd_line, signal_line=signal_line, histogram=histogram)


# ──────────────────────────────────────────────
# Convenience: latest values
# ──────────────────────────────────────────────

def latest_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    series = rsi(closes, period)
    for v in reversed(series):
        if v is not None:
            return round(v, 2)
    return None


def latest_sma(closes: List[float], period: int = 20) -> Optional[float]:
    series = sma(closes, period)
    for v in reversed(series):
        if v is not None:
            return round(v, 2)
    return None


def latest_macd(closes: List[float]) -> Tuple[Optional[float], Optional[float]]:
    m = macd(closes)
    ml = None
    sl = None
    for v in reversed(m.macd_line):
        if v is not None:
            ml = round(v, 4)
            break
    for v in reversed(m.signal_line):
        if v is not None:
            sl = round(v, 4)
            break
    return ml, sl
