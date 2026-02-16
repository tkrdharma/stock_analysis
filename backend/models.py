"""
SQLAlchemy ORM models for the Oversold Reversal Stock Screener.

Tables:
  symbols        – universe of stock tickers loaded from symbols.txt
  scans          – each full screening run
  fundamentals   – fundamental data snapshot per symbol per scan
  technicals     – computed indicator values per symbol per scan
  recommendations – buy/not‑buy decision per symbol per scan
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, DateTime,
    ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utcnow():
    return datetime.now(timezone.utc)


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=_utcnow)


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=_utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="running")       # running | completed | failed
    error_message = Column(Text, nullable=True)

    fundamentals = relationship("Fundamental", back_populates="scan")
    technicals = relationship("Technical", back_populates="scan")
    recommendations = relationship("Recommendation", back_populates="scan")
    logs = relationship("ScanLog", back_populates="scan")


class Fundamental(Base):
    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=False)
    name = Column(String(256), nullable=True)
    cmp = Column(Float, nullable=True)
    pe = Column(Float, nullable=True)
    roce = Column(Float, nullable=True)
    bv = Column(Float, nullable=True)
    debt = Column(Float, nullable=True)
    industry = Column(String(256), nullable=True)
    fetched_at = Column(DateTime, default=_utcnow)

    scan = relationship("Scan", back_populates="fundamentals")
    symbol = relationship("Symbol")


class Technical(Base):
    __tablename__ = "technicals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=False)
    rsi14 = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    sma20 = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    signals_json = Column(Text, nullable=True)   # JSON string of triggered signals
    computed_at = Column(DateTime, default=_utcnow)
    # Store price series for charting (JSON array of {date, close})
    price_series_json = Column(Text, nullable=True)
    rsi_series_json = Column(Text, nullable=True)
    macd_series_json = Column(Text, nullable=True)

    scan = relationship("Scan", back_populates="technicals")
    symbol = relationship("Symbol")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=False)
    recommended = Column(Boolean, default=False)
    score = Column(Float, default=0.0)
    reason = Column(Text, nullable=True)

    scan = relationship("Scan", back_populates="recommendations")
    symbol = relationship("Symbol")


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)
    symbol_id = Column(Integer, ForeignKey("symbols.id"), nullable=True)
    status = Column(String(16), nullable=False)  # skipped | ignored | error
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    scan = relationship("Scan", back_populates="logs")
    symbol = relationship("Symbol")
