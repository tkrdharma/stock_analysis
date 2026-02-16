import React, { useState } from 'react';
import { reloadSymbols, runScan, clearAllRecords } from '../api';

export default function ScanControls({ onScanStarted, onRefresh, scanStatus, setError }) {
  const [reloading, setReloading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [reloadResult, setReloadResult] = useState(null);
  const [clearing, setClearing] = useState(false);

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

  const handleClearAll = async () => {
    const confirmed = window.confirm('Delete ALL records from all tables? This cannot be undone.');
    if (!confirmed) return;
    setClearing(true);
    setError(null);
    try {
      await clearAllRecords();
      setReloadResult(null);
      onRefresh?.();
    } catch (e) {
      setError('Failed to clear records: ' + (e.response?.data?.detail || e.message));
    } finally {
      setClearing(false);
    }
  };

  const isRunning = scanStatus?.status === 'running';
  const progress = scanStatus?.progress;

  // Compute progress percentage
  let pct = 0;
  let progressLabel = '';
  if (isRunning && progress) {
    const done = (progress.skipped || 0) + (progress.completed || 0);
    const total = progress.total || 1;
    pct = Math.round((done / total) * 100);
    const currentSym = progress.current_symbol;
    progressLabel = `${done} / ${total} symbols`;
    if (progress.skipped > 0) {
      progressLabel += ` (${progress.skipped} skipped)`;
    }
    if (progress.errors > 0) {
      progressLabel += ` · ${progress.errors} error${progress.errors !== 1 ? 's' : ''}`;
    }
    if (currentSym) {
      progressLabel += `  ·  Processing: ${currentSym}`;
    }
  }

  return (
    <div className="scan-controls-wrapper">
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

        <button
          className="btn btn-secondary"
          onClick={handleClearAll}
          disabled={clearing || isRunning}
        >
          {clearing ? '...' : '🧹'} Delete all records
        </button>

        <div className="scan-status">
          {scanStatus && !isRunning && (
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

      {/* Progress bar during scan */}
      {isRunning && (
        <div className="progress-container">
          <div className="progress-header">
            <span className="badge badge-running">Scanning</span>
            <span className="progress-label">{progressLabel || 'Initializing...'}</span>
            <span className="progress-pct">{pct}%</span>
          </div>
          <div className="progress-track">
            <div
              className="progress-bar"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
