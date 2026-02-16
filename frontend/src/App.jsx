import React, { useState, useEffect, useCallback, useRef } from 'react';
import ScanControls from './components/ScanControls';
import RecommendationsTable from './components/RecommendationsTable';
import StockDetailsModal from './components/StockDetailsModal';
import { getLatest, getLatestAll, getScan, getActiveScan, deleteFromLatestScan, deleteFromScan } from './api';

export default function App() {
  const [data, setData] = useState(null);           // latest recommended
  const [allData, setAllData] = useState(null);      // all scanned (debug)
  const [showAll, setShowAll] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState(null);
  const [scanId, setScanId] = useState(null);
  const [scanStatus, setScanStatus] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const refresh = useCallback(async () => {
    try {
      const d = await getLatest();
      setData(d);
      if (showAll) {
        const a = await getLatestAll();
        setAllData(a);
      }
    } catch (e) {
      // no scan yet – that's fine
    }
  }, [showAll]);

  const handleRefreshAfterClear = useCallback(async () => {
    setData(null);
    setAllData(null);
    setScanStatus(null);
    setSelectedSymbol(null);
    await refresh();
  }, [refresh]);

  useEffect(() => {
    refresh();
    // Check if a scan is already running (page-load recovery)
    (async () => {
      try {
        const active = await getActiveScan();
        if (active.active && active.scan_id) {
          setScanId(active.scan_id);
          setScanStatus({ scan_id: active.scan_id, status: 'running', progress: active.progress });
          startPolling(active.scan_id);
        }
      } catch (e) {
        // ignore – no active scan
      }
    })();
  }, []);

  // Poll scan status while running
  const startPolling = useCallback((id) => {
    console.log('[App] startPolling for scan_id=', id);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        console.log('[App] polling scan status for id=', id);
        const s = await getScan(id);
        console.log('[App] scan status:', s);
        setScanStatus(s);
        if (s.status !== 'running') {
          console.log('[App] scan finished, stopping poll');
          clearInterval(pollRef.current);
          pollRef.current = null;
          await refresh();
        }
      } catch (e) {
        console.warn('[App] poll error:', e);
      }
    }, 1500);
  }, [refresh]);

  const onScanStarted = useCallback((id) => {
    console.log('[App] onScanStarted scan_id=', id);
    setScanId(id);
    setScanStatus({ scan_id: id, status: 'running' });
    startPolling(id);
  }, [startPolling]);

  const handleToggleAll = async () => {
    const next = !showAll;
    setShowAll(next);
    if (next && !allData) {
      const a = await getLatestAll();
      setAllData(a);
    }
  };

  const handleDelete = async (symbol) => {
    const activeScanId = showAll ? allData?.scan_id : data?.scan_id;
    if (!activeScanId) {
      setError('No scan available to delete from. Run a scan first.');
      return;
    }
    const confirmDelete = window.confirm(`Delete ${symbol} from this scan?`);
    if (!confirmDelete) return;
    try {
      if (activeScanId) {
        await deleteFromScan(activeScanId, symbol);
      } else {
        await deleteFromLatestScan(symbol);
      }

      if (showAll) {
        setAllData(prev => prev ? {
          ...prev,
          results: (prev.results || []).filter(r => r.symbol !== symbol),
        } : prev);
      } else {
        setData(prev => prev ? {
          ...prev,
          recommendations: (prev.recommendations || []).filter(r => r.symbol !== symbol),
        } : prev);
      }
    } catch (e) {
      setError('Failed to delete record: ' + (e.response?.data?.detail || e.message));
    }
  };

  const displayRows = showAll
    ? (allData?.results || [])
    : (data?.recommendations || []);

  return (
    <>
      <header>
        <div className="container">
          <h1>Oversold Reversal Screener</h1>
          <p>Screens for RSI oversold + reversal confirmations (MACD crossover, SMA20 cross, RSI momentum)</p>
        </div>
      </header>

      <main className="container full-screen">
        {error && <div className="error-msg">{error}</div>}

        <ScanControls
          onScanStarted={onScanStarted}
          onRefresh={handleRefreshAfterClear}
          scanStatus={scanStatus}
          setError={setError}
        />

        <div className="controls" style={{ marginBottom: '0.5rem' }}>
          <button
            className={`tab-btn ${!showAll ? 'active' : ''}`}
            onClick={() => setShowAll(false)}
          >
            Recommended ({data?.recommendations?.length || 0})
          </button>
          <button
            className={`tab-btn ${showAll ? 'active' : ''}`}
            onClick={handleToggleAll}
          >
            All Scanned ({allData?.results?.length || '...'})
          </button>
        </div>

        <RecommendationsTable
          rows={displayRows}
          showAll={showAll}
          onRowClick={(sym) => setSelectedSymbol(sym)}
          onDelete={handleDelete}
        />

        {selectedSymbol && (
          <StockDetailsModal
            symbol={selectedSymbol}
            scanId={data?.scan_id}
            onClose={() => setSelectedSymbol(null)}
          />
        )}
      </main>
    </>
  );
}
