"""
FastAPI application – Oversold Reversal Stock Screener.

Endpoints:
  POST /api/symbols/reload
  POST /api/scan/run
  GET  /api/scan/{scan_id}
  GET  /api/recommendations/latest
  GET  /api/recommendations/latest/all
  GET  /api/symbol/{symbol}/details?scan_id=...
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import desc

from db import engine, get_db
from models import Base, Symbol, Scan, Fundamental, Technical, Recommendation, ScanLog
from scanner import _process_symbol, CONCURRENCY_LIMIT

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)-8s [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)
# Suppress noisy third-party debug logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.INFO)
logging.getLogger("watchfiles").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created / verified.")
    yield
    # Shutdown: nothing needed

app = FastAPI(title="Oversold Reversal Stock Screener", version="1.0.0", lifespan=lifespan)

# CORS – allow React dev‑server (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────

# Path to symbols.txt – expected in the project root (one level above backend/)
SYMBOLS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "symbols.txt",
)


def _read_symbols_file() -> List[str]:
    """Parse symbols.txt: one symbol per line, ignore blanks and # comments."""
    p = pathlib.Path(SYMBOLS_FILE)
    if not p.exists():
        raise FileNotFoundError(f"symbols.txt not found at {p}")
    symbols: List[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        symbols.append(line.upper())
    return symbols


def _delete_all_records(db: Session) -> dict:
    """Delete all rows from all tables and return counts."""
    global _scan_running, _scan_progress
    # Clear in-memory scan state so a pending scan can't keep running after a wipe
    _scan_running = False
    _scan_progress.clear()

    deleted_logs = db.query(ScanLog).delete()
    deleted_recs = db.query(Recommendation).delete()
    deleted_tech = db.query(Technical).delete()
    deleted_fund = db.query(Fundamental).delete()
    deleted_scans = db.query(Scan).delete()
    deleted_symbols = db.query(Symbol).delete()
    db.commit()

    # Immediately repopulate symbols from symbols.txt so the next Run Scan works without manual reload
    reload_added = 0
    reload_total = 0
    try:
        symbols = _read_symbols_file()
        for s in symbols:
            exists = db.query(Symbol).filter_by(symbol=s).first()
            if not exists:
                db.add(Symbol(symbol=s))
                reload_added += 1
        db.commit()
        reload_total = db.query(Symbol).count()
        logger.info("After clear-all: reloaded symbols.txt (%d added, %d total)", reload_added, reload_total)
    except FileNotFoundError:
        logger.warning("symbols.txt not found; symbols table left empty after clear-all")

    return {
        "scan_logs": deleted_logs,
        "recommendations": deleted_recs,
        "technicals": deleted_tech,
        "fundamentals": deleted_fund,
        "scans": deleted_scans,
        "symbols": deleted_symbols,
        "symbols_reloaded": reload_added,
        "symbols_total": reload_total,
    }


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.post("/api/symbols/reload")
def reload_symbols(db: Session = Depends(get_db)):
    """Read symbols.txt, upsert into DB."""
    logger.info("=== RELOAD SYMBOLS from %s ===", SYMBOLS_FILE)
    try:
        syms = _read_symbols_file()
    except FileNotFoundError as exc:
        logger.error("symbols.txt not found: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc))

    logger.info("Parsed %d symbols from file: %s", len(syms), syms)
    count_added = 0
    for s in syms:
        exists = db.query(Symbol).filter_by(symbol=s).first()
        if not exists:
            db.add(Symbol(symbol=s))
            count_added += 1
            logger.debug("  + Added new symbol: %s", s)
        else:
            logger.debug("  . Symbol already exists: %s", s)
    db.commit()
    count_total = db.query(Symbol).count()
    logger.info("Reload complete: %d added, %d total in DB", count_added, count_total)
    return {"count_added": count_added, "count_total": count_total}


# Background scan state (simple in‑memory flag for the single‑worker case)
_scan_running = False

# In-memory progress tracking:  scan_id → { total, skipped, completed, current_symbol, errors }
_scan_progress: dict = {}


@app.post("/api/scan/run")
async def start_scan(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Kick off a scan in the background.  Returns {scan_id} immediately."""
    global _scan_running
    if _scan_running:
        raise HTTPException(status_code=409, detail="A scan is already running")
    _scan_running = True

    # Create the scan row up-front so we can return an ID
    scan = Scan(status="running")
    db.add(scan)
    db.commit()
    scan_id = scan.id
    logger.info("=== SCAN STARTED  scan_id=%d ===", scan_id)

    async def _do_scan():
        global _scan_running
        try:
            await run_scan_for_id(scan_id)
        except Exception as exc:
            logger.exception("SCAN %d CRASHED: %s", scan_id, exc)
        finally:
            _scan_running = False
            logger.info("=== SCAN FINISHED scan_id=%d ===", scan_id)

    # Run in background
    asyncio.ensure_future(_do_scan())
    return {"scan_id": scan_id}


@app.get("/api/scan/active")
def get_active_scan(db: Session = Depends(get_db)):
    """Check if there is a currently running scan (for page-load recovery)."""
    if _scan_running:
        # Find the running scan row
        scan = db.query(Scan).filter_by(status="running").order_by(desc(Scan.id)).first()
        if scan:
            progress = _scan_progress.get(scan.id)
            return {
                "active": True,
                "scan_id": scan.id,
                "status": "running",
                "progress": progress,
            }
    return {"active": False, "scan_id": None, "status": None, "progress": None}


@app.delete("/api/admin/clear-all")
def clear_all_records(confirm: bool = Query(False), db: Session = Depends(get_db)):
    """Delete all records from all tables. Requires confirm=true."""
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required")
    deleted = _delete_all_records(db)
    return {"status": "ok", "deleted": deleted}


async def run_scan_for_id(scan_id: int):
    """Run the scanner and update the pre-created scan row."""
    from db import get_db_context
    from models import Scan, Symbol
    import httpx

    with get_db_context() as db:
        symbols = db.query(Symbol).all()
        symbol_list = [(s.id, s.symbol) for s in symbols]

    logger.info("Scan %d: found %d symbols in DB", scan_id, len(symbol_list))
    for sid, sym_str in symbol_list:
        logger.debug("  Symbol id=%d  ticker=%s", sid, sym_str)

    if not symbol_list:
        logger.warning("Scan %d: NO symbols in DB – nothing to scan. Did you reload symbols.txt?", scan_id)
        with get_db_context() as db:
            sc = db.query(Scan).get(scan_id)
            sc.status = "completed"
            sc.finished_at = datetime.now(timezone.utc)
        return

    today = datetime.now(timezone.utc).date()
    skip_results = []
    to_process = []
    with get_db_context() as db:
        for sid, sym_str in symbol_list:
            tech = (
                db.query(Technical)
                .filter_by(symbol_id=sid)
                .order_by(desc(Technical.computed_at))
                .first()
            )
            fund = (
                db.query(Fundamental)
                .filter_by(symbol_id=sid)
                .order_by(desc(Fundamental.fetched_at))
                .first()
            )

            tech_today = tech and tech.computed_at and tech.computed_at.date() == today
            fund_today = fund and fund.fetched_at and fund.fetched_at.date() == today

            if tech_today or fund_today:
                rec = None
                if tech and tech.scan_id:
                    rec = (
                        db.query(Recommendation)
                        .filter_by(scan_id=tech.scan_id, symbol_id=sid)
                        .first()
                    )
                elif fund and fund.scan_id:
                    rec = (
                        db.query(Recommendation)
                        .filter_by(scan_id=fund.scan_id, symbol_id=sid)
                        .first()
                    )

                fund_snapshot = None
                if fund:
                    fund_snapshot = {
                        "name": fund.name,
                        "cmp": fund.cmp,
                        "pe": fund.pe,
                        "roce": fund.roce,
                        "bv": fund.bv,
                        "debt": fund.debt,
                        "industry": fund.industry,
                    }

                tech_snapshot = None
                if tech:
                    tech_snapshot = {
                        "rsi14": tech.rsi14,
                        "macd": tech.macd,
                        "macd_signal": tech.macd_signal,
                        "sma20": tech.sma20,
                        "close": tech.close,
                        "signals_json": tech.signals_json,
                        "price_series_json": tech.price_series_json,
                        "rsi_series_json": tech.rsi_series_json,
                        "macd_series_json": tech.macd_series_json,
                    }

                rec_snapshot = None
                if rec:
                    rec_snapshot = {
                        "recommended": rec.recommended,
                        "score": rec.score,
                        "reason": rec.reason,
                    }

                skip_results.append({
                    "symbol": sym_str,
                    "symbol_id": sid,
                    "status": "skipped",
                    "skip_reason": "Already pulled today",
                    "fund_snapshot": fund_snapshot,
                    "tech_snapshot": tech_snapshot,
                    "rec_snapshot": rec_snapshot,
                    "error": None,
                })
            else:
                to_process.append((sid, sym_str))

    logger.info(
        "Scan %d: %d symbols to process, %d skipped (already pulled today)",
        scan_id, len(to_process), len(skip_results),
    )

    # Initialise progress tracking
    _scan_progress[scan_id] = {
        "total": len(symbol_list),
        "to_process": len(to_process),
        "skipped": len(skip_results),
        "completed": 0,
        "current_symbol": None,
        "errors": 0,
    }

    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    logger.info("Scan %d: starting processing with concurrency=%d", scan_id, CONCURRENCY_LIMIT)

    async def _tracked_process(stub, scan_id, client, semaphore):
        """Wrap _process_symbol to update progress tracking."""
        _scan_progress[scan_id]["current_symbol"] = stub.symbol
        result = await _process_symbol(stub, scan_id, client, semaphore)
        _scan_progress[scan_id]["completed"] += 1
        if isinstance(result, dict) and result.get("status") == "error":
            _scan_progress[scan_id]["errors"] += 1
        return result

    async with httpx.AsyncClient(verify=False) as client:
        tasks = []
        for sid, sym_str in to_process:
            class _SymStub:
                pass
            stub = _SymStub()
            stub.id = sid
            stub.symbol = sym_str
            tasks.append(_tracked_process(stub, scan_id, client, semaphore))

        logger.info("Scan %d: awaiting %d symbol tasks...", scan_id, len(tasks))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Scan %d: all tasks returned (%d results)", scan_id, len(results))

    results = skip_results + results

    # Persist
    errors = []
    logger.info("Scan %d: persisting results to DB...", scan_id)
    with get_db_context() as db:
        for idx, res in enumerate(results):
            if isinstance(res, Exception):
                logger.error("Scan %d: result[%d] is an EXCEPTION: %s", scan_id, idx, res)
                errors.append(str(res))
                db.add(ScanLog(
                    scan_id=scan_id,
                    symbol_id=None,
                    status="error",
                    message=str(res),
                ))
                continue

            sym_id = res["symbol_id"]
            sym_name = res.get("symbol", "?")
            logger.debug(
                "Scan %d: saving result for %s (id=%d) – recommended=%s score=%s error=%s",
                scan_id, sym_name, sym_id,
                res.get("recommended"), res.get("score"), res.get("error"),
            )

            status = res.get("status", "ok")

            if status == "skipped":
                db.add(ScanLog(
                    scan_id=scan_id,
                    symbol_id=sym_id,
                    status="skipped",
                    message=res.get("skip_reason", "Already pulled today"),
                ))

                fund_snapshot = res.get("fund_snapshot")
                if fund_snapshot:
                    db.add(Fundamental(
                        scan_id=scan_id,
                        symbol_id=sym_id,
                        name=fund_snapshot.get("name"),
                        cmp=fund_snapshot.get("cmp"),
                        pe=fund_snapshot.get("pe"),
                        roce=fund_snapshot.get("roce"),
                        bv=fund_snapshot.get("bv"),
                        debt=fund_snapshot.get("debt"),
                        industry=fund_snapshot.get("industry"),
                    ))

                tech_snapshot = res.get("tech_snapshot")
                if tech_snapshot:
                    db.add(Technical(
                        scan_id=scan_id,
                        symbol_id=sym_id,
                        rsi14=tech_snapshot.get("rsi14"),
                        macd=tech_snapshot.get("macd"),
                        macd_signal=tech_snapshot.get("macd_signal"),
                        sma20=tech_snapshot.get("sma20"),
                        close=tech_snapshot.get("close"),
                        signals_json=tech_snapshot.get("signals_json"),
                        price_series_json=tech_snapshot.get("price_series_json"),
                        rsi_series_json=tech_snapshot.get("rsi_series_json"),
                        macd_series_json=tech_snapshot.get("macd_series_json"),
                    ))

                rec_snapshot = res.get("rec_snapshot")
                if rec_snapshot:
                    db.add(Recommendation(
                        scan_id=scan_id,
                        symbol_id=sym_id,
                        recommended=rec_snapshot.get("recommended", False),
                        score=rec_snapshot.get("score", 0.0),
                        reason=rec_snapshot.get("reason", ""),
                    ))
                else:
                    db.add(Recommendation(
                        scan_id=scan_id,
                        symbol_id=sym_id,
                        recommended=False,
                        score=0.0,
                        reason="Skipped (already pulled today)",
                    ))
                continue

            fd = res.get("fundamentals")
            if fd:
                db.add(Fundamental(
                    scan_id=scan_id,
                    symbol_id=sym_id,
                    name=fd.name,
                    cmp=fd.cmp,
                    pe=fd.pe,
                    roce=fd.roce,
                    bv=fd.bv,
                    debt=fd.debt,
                    industry=fd.industry,
                ))

            signals = res.get("signals", {})
            price_bars = res.get("price_bars", [])
            price_series = [{"date": b.date, "close": b.close} for b in price_bars] if price_bars else []

            rsi_s = res.get("rsi_series", [])
            macd_r = res.get("macd_result")
            rsi_chart = []
            macd_chart = []
            if price_bars and rsi_s:
                for i, b in enumerate(price_bars):
                    if i < len(rsi_s) and rsi_s[i] is not None:
                        rsi_chart.append({"date": b.date, "rsi": round(rsi_s[i], 2)})
            if price_bars and macd_r:
                for i, b in enumerate(price_bars):
                    entry = {"date": b.date}
                    if i < len(macd_r.macd_line) and macd_r.macd_line[i] is not None:
                        entry["macd"] = round(macd_r.macd_line[i], 4)
                    if i < len(macd_r.signal_line) and macd_r.signal_line[i] is not None:
                        entry["signal"] = round(macd_r.signal_line[i], 4)
                    if i < len(macd_r.histogram) and macd_r.histogram[i] is not None:
                        entry["histogram"] = round(macd_r.histogram[i], 4)
                    if len(entry) > 1:
                        macd_chart.append(entry)

            db.add(Technical(
                scan_id=scan_id,
                symbol_id=sym_id,
                rsi14=signals.get("latest_rsi"),
                macd=signals.get("latest_macd"),
                macd_signal=signals.get("latest_signal"),
                sma20=signals.get("latest_sma20"),
                close=signals.get("latest_close"),
                signals_json=json.dumps(signals),
                price_series_json=json.dumps(price_series),
                rsi_series_json=json.dumps(rsi_chart),
                macd_series_json=json.dumps(macd_chart),
            ))

            db.add(Recommendation(
                scan_id=scan_id,
                symbol_id=sym_id,
                recommended=res.get("recommended", False),
                score=res.get("score", 0.0),
                reason=res.get("reason", ""),
            ))

            if status == "ignored":
                db.add(ScanLog(
                    scan_id=scan_id,
                    symbol_id=sym_id,
                    status="ignored",
                    message=res.get("error") or res.get("reason"),
                ))
            elif status == "error":
                db.add(ScanLog(
                    scan_id=scan_id,
                    symbol_id=sym_id,
                    status="error",
                    message=res.get("error"),
                ))

        sc = db.query(Scan).get(scan_id)
        sc.finished_at = datetime.now(timezone.utc)
        sc.status = "completed"
        if errors:
            sc.error_message = "; ".join(errors[:10])
            logger.warning("Scan %d had %d errors: %s", scan_id, len(errors), sc.error_message)

    # Mark progress as complete (keep for a short while so frontend can read final state)
    if scan_id in _scan_progress:
        _scan_progress[scan_id]["current_symbol"] = None
        _scan_progress[scan_id]["completed"] = _scan_progress[scan_id]["to_process"]

    logger.info("═══ Scan %d COMPLETED ═══  errors=%d", scan_id, len(errors))

    # Clean up progress after a delay (let final poll read it)
    async def _cleanup_progress():
        await asyncio.sleep(30)
        _scan_progress.pop(scan_id, None)
    asyncio.ensure_future(_cleanup_progress())


@app.get("/api/scan/{scan_id}")
def get_scan(scan_id: int, db: Session = Depends(get_db)):
    """Return scan status, summary counts, and live progress if running."""
    scan = db.query(Scan).get(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    total = db.query(Recommendation).filter_by(scan_id=scan_id).count()
    recommended = db.query(Recommendation).filter_by(scan_id=scan_id, recommended=True).count()
    progress = _scan_progress.get(scan_id)
    return {
        "scan_id": scan.id,
        "status": scan.status,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "error_message": scan.error_message,
        "total_symbols": total,
        "recommended_count": recommended,
        "progress": progress,
    }


@app.delete("/api/scan/{scan_id}/symbol/{symbol}")
def delete_symbol_from_scan(scan_id: int, symbol: str, db: Session = Depends(get_db)):
    """Delete a symbol's records for a specific scan."""
    scan = db.query(Scan).get(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    sym = db.query(Symbol).filter_by(symbol=symbol.upper()).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Symbol not found")

    deleted_fund = db.query(Fundamental).filter_by(scan_id=scan_id, symbol_id=sym.id).delete()
    deleted_tech = db.query(Technical).filter_by(scan_id=scan_id, symbol_id=sym.id).delete()
    deleted_rec = db.query(Recommendation).filter_by(scan_id=scan_id, symbol_id=sym.id).delete()
    deleted_logs = db.query(ScanLog).filter_by(scan_id=scan_id, symbol_id=sym.id).delete()

    db.commit()

    return {
        "scan_id": scan_id,
        "symbol": sym.symbol,
        "deleted": {
            "fundamentals": deleted_fund,
            "technicals": deleted_tech,
            "recommendations": deleted_rec,
            "logs": deleted_logs,
        },
    }


@app.delete("/api/scan/latest/symbol/{symbol}")
def delete_symbol_from_latest_scan(symbol: str, db: Session = Depends(get_db)):
    """Delete a symbol's records for the latest scan."""
    scan = db.query(Scan).order_by(desc(Scan.id)).first()
    if not scan:
        raise HTTPException(status_code=404, detail="No scans available")
    return delete_symbol_from_scan(scan.id, symbol, db)


@app.get("/api/scan/{scan_id}/logs")
def get_scan_logs(scan_id: int, db: Session = Depends(get_db)):
    """Return skip/ignore/error logs for a specific scan."""
    scan = db.query(Scan).get(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    logs = (
        db.query(ScanLog, Symbol)
        .outerjoin(Symbol, ScanLog.symbol_id == Symbol.id)
        .filter(ScanLog.scan_id == scan_id)
        .order_by(ScanLog.created_at)
        .all()
    )

    rows = []
    for log, sym in logs:
        rows.append({
            "status": log.status,
            "symbol": sym.symbol if sym else None,
            "message": log.message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })

    return {
        "scan_id": scan.id,
        "scan_status": scan.status,
        "logs": rows,
    }


@app.get("/api/scan/latest/logs")
def latest_scan_logs(db: Session = Depends(get_db)):
    """Return logs for the latest scan."""
    scan = db.query(Scan).order_by(desc(Scan.id)).first()
    if not scan:
        return {"scan_id": None, "scan_status": None, "logs": []}
    return get_scan_logs(scan.id, db)


@app.get("/api/recommendations/latest")
def latest_recommendations(db: Session = Depends(get_db)):
    """Return the latest scan's recommended stocks."""
    scan = db.query(Scan).order_by(desc(Scan.id)).first()
    if not scan:
        return {"scan_id": None, "scan_status": None, "recommendations": []}
    recs = (
        db.query(Recommendation, Fundamental, Technical, Symbol)
        .join(Symbol, Recommendation.symbol_id == Symbol.id)
        .outerjoin(
            Fundamental,
            (Fundamental.scan_id == Recommendation.scan_id)
            & (Fundamental.symbol_id == Recommendation.symbol_id),
        )
        .outerjoin(
            Technical,
            (Technical.scan_id == Recommendation.scan_id)
            & (Technical.symbol_id == Recommendation.symbol_id),
        )
        .filter(Recommendation.scan_id == scan.id, Recommendation.recommended == True)
        .order_by(desc(Recommendation.score))
        .all()
    )
    rows = []
    for rec, fund, tech, sym in recs:
        signals = json.loads(tech.signals_json) if tech and tech.signals_json else {}
        rsi_div = "Bullish" if signals.get("rsi_divergence") else "Bearing"
        macd_div = "Bullish" if signals.get("macd_divergence") else "Bearing"
        rows.append({
            "symbol": sym.symbol,
            "stock_name": fund.name if fund else None,
            "cmp": fund.cmp if fund else None,
            "pe": fund.pe if fund else None,
            "roce": fund.roce if fund else None,
            "bv": fund.bv if fund else None,
            "debt": fund.debt if fund else None,
            "industry": fund.industry if fund else None,
            "rsi_divergence": rsi_div,
            "macd_divergence": macd_div,
            "score": rec.score,
            "reason": rec.reason,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })
    return {
        "scan_id": scan.id,
        "scan_status": scan.status,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "recommendations": rows,
    }


@app.get("/api/recommendations/latest/all")
def latest_all(db: Session = Depends(get_db)):
    """Return ALL scanned symbols from the latest scan (for debugging)."""
    scan = db.query(Scan).order_by(desc(Scan.id)).first()
    if not scan:
        return {"scan_id": None, "results": []}
    recs = (
        db.query(Recommendation, Fundamental, Technical, Symbol)
        .join(Symbol, Recommendation.symbol_id == Symbol.id)
        .outerjoin(
            Fundamental,
            (Fundamental.scan_id == Recommendation.scan_id)
            & (Fundamental.symbol_id == Recommendation.symbol_id),
        )
        .outerjoin(
            Technical,
            (Technical.scan_id == Recommendation.scan_id)
            & (Technical.symbol_id == Recommendation.symbol_id),
        )
        .filter(Recommendation.scan_id == scan.id)
        .order_by(desc(Recommendation.score))
        .all()
    )
    rows = []
    for rec, fund, tech, sym in recs:
        signals = json.loads(tech.signals_json) if tech and tech.signals_json else {}
        rsi_div = "Bullish" if signals.get("rsi_divergence") else "Bearing"
        macd_div = "Bullish" if signals.get("macd_divergence") else "Bearing"
        rows.append({
            "symbol": sym.symbol,
            "stock_name": fund.name if fund else None,
            "cmp": fund.cmp if fund else None,
            "pe": fund.pe if fund else None,
            "roce": fund.roce if fund else None,
            "bv": fund.bv if fund else None,
            "debt": fund.debt if fund else None,
            "industry": fund.industry if fund else None,
            "rsi14": tech.rsi14 if tech else None,
            "macd": tech.macd if tech else None,
            "macd_signal": tech.macd_signal if tech else None,
            "sma20": tech.sma20 if tech else None,
            "close": tech.close if tech else None,
            "rsi_divergence": rsi_div,
            "macd_divergence": macd_div,
            "recommended": rec.recommended,
            "score": rec.score,
            "reason": rec.reason,
            "created_at": rec.created_at.isoformat() if rec.created_at else None,
        })
    return {
        "scan_id": scan.id,
        "scan_status": scan.status,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "finished_at": scan.finished_at.isoformat() if scan.finished_at else None,
        "results": rows,
    }


@app.get("/api/symbol/{symbol}/details")
def symbol_details(
    symbol: str,
    scan_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return detailed data for the modal (price series, indicators, signals)."""
    sym = db.query(Symbol).filter_by(symbol=symbol.upper()).first()
    if not sym:
        raise HTTPException(status_code=404, detail="Symbol not found")

    if scan_id is None:
        scan = db.query(Scan).order_by(desc(Scan.id)).first()
        if not scan:
            raise HTTPException(status_code=404, detail="No scans available")
        scan_id = scan.id

    fund = (
        db.query(Fundamental)
        .filter_by(scan_id=scan_id, symbol_id=sym.id)
        .first()
    )
    tech = (
        db.query(Technical)
        .filter_by(scan_id=scan_id, symbol_id=sym.id)
        .first()
    )
    rec = (
        db.query(Recommendation)
        .filter_by(scan_id=scan_id, symbol_id=sym.id)
        .first()
    )

    return {
        "symbol": sym.symbol,
        "stock_name": fund.name if fund else None,
        "cmp": fund.cmp if fund else None,
        "pe": fund.pe if fund else None,
        "roce": fund.roce if fund else None,
        "bv": fund.bv if fund else None,
        "debt": fund.debt if fund else None,
        "industry": fund.industry if fund else None,
        "rsi14": tech.rsi14 if tech else None,
        "macd": tech.macd if tech else None,
        "macd_signal": tech.macd_signal if tech else None,
        "sma20": tech.sma20 if tech else None,
        "close": tech.close if tech else None,
        "signals": json.loads(tech.signals_json) if tech and tech.signals_json else {},
        "price_series": json.loads(tech.price_series_json) if tech and tech.price_series_json else [],
        "rsi_series": json.loads(tech.rsi_series_json) if tech and tech.rsi_series_json else [],
        "macd_series": json.loads(tech.macd_series_json) if tech and tech.macd_series_json else [],
        "recommended": rec.recommended if rec else False,
        "score": rec.score if rec else 0,
        "reason": rec.reason if rec else "",
        "created_at": rec.created_at.isoformat() if rec and rec.created_at else None,
    }


# ──────────────────────────────────────────────
# Run with: uvicorn main:app --reload
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
