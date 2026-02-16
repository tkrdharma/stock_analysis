import React, { useState } from 'react';
import { reloadSymbols, runScan } from '../api';

export default function ScanControls({ onScanStarted, onRefresh, scanStatus, setError }) {
  const [reloading, setReloading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [reloadResult, setReloadResult] = useState(null);

  const handleReload = async () => {
    setReloading(true);
    setError(null);
    try {
      const res = await reloadSymbols();
      setReloadResult(res);
    } catch (e) {
      setError('Failed to reload symbols: ' + (e.response?.data?.detail || e.message));
    } finally {
      setReloading(false);
    }
  };

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    try {
      const res = await runScan();
      onScanStarted(res.scan_id);
    } catch (e) {
      setError('Failed to start scan: ' + (e.response?.data?.detail || e.message));
    } finally {
      setScanning(false);
    }
  };

  const isRunning = scanStatus?.status === 'running';

  return (
    <div className="controls">
      <button
        className="btn btn-secondary"
        onClick={handleReload}
        disabled={reloading}
      >
        {reloading ? '...' : '📄'} Reload symbols.txt
      </button>

      {reloadResult && (
        <span style={{ fontSize: '0.8rem', color: 'var(--green)' }}>
          +{reloadResult.count_added} new, {reloadResult.count_total} total
        </span>
      )}

      <button
        className="btn btn-primary"
        onClick={handleScan}
        disabled={scanning || isRunning}
      >
        {isRunning ? '⏳ Scanning...' : '🔍 Run Scan'}
      </button>

      <div className="scan-status">
        {scanStatus && (
          <>
            <span className={`badge badge-${scanStatus.status}`}>
              {scanStatus.status}
            </span>
            {scanStatus.finished_at && (
              <span style={{ marginLeft: '0.5rem' }}>
                {new Date(scanStatus.finished_at).toLocaleString()}
              </span>
            )}
            {scanStatus.total_symbols !== undefined && (
              <span style={{ marginLeft: '0.5rem' }}>
                ({scanStatus.recommended_count}/{scanStatus.total_symbols} recommended)
              </span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
