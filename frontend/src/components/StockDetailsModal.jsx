import React, { useEffect, useState } from 'react';
import { getDetails } from '../api';
import PriceChart from './PriceChart';

export default function StockDetailsModal({ symbol, scanId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [chartTab, setChartTab] = useState('price'); // price | rsi | macd

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const d = await getDetails(symbol, scanId);
        if (!cancelled) setData(d);
      } catch (e) {
        if (!cancelled) setError(e.message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [symbol, scanId]);

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  const fmt = (v, d = 2) =>
    v === null || v === undefined ? 'N/A' : typeof v === 'number' ? v.toFixed(d) : v;

  const signals = data?.signals || {};
  const signalTags = [
    { key: 'rsi_oversold', label: 'RSI Oversold (<30)' },
    { key: 'macd_crossover', label: 'MACD Bullish Crossover' },
    { key: 'sma20_cross', label: 'Close > SMA20 Cross' },
    { key: 'rsi_rising_3d', label: 'RSI Rising 3 Days' },
    { key: 'rsi_divergence', label: 'RSI Bullish Divergence (5d)' },
    { key: 'macd_divergence', label: 'MACD Bullish Divergence (5d)' },
  ];

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>{data?.stock_name || symbol} ({symbol})</h2>
          <button className="modal-close" onClick={onClose}>&times;</button>
        </div>

        {loading && <div className="loading">Loading details...</div>}
        {error && <div className="error-msg">{error}</div>}

        {data && (
          <>
            {/* Fundamentals */}
            <div className="modal-section">
              <h3>Fundamentals</h3>
              <div className="detail-grid">
                <div className="detail-item">
                  <div className="label">CMP</div>
                  <div className="value">{fmt(data.cmp)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">PE</div>
                  <div className="value">{fmt(data.pe)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">ROCE</div>
                  <div className="value">{fmt(data.roce)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">Book Value</div>
                  <div className="value">{fmt(data.bv)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">Debt</div>
                  <div className="value">{fmt(data.debt)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">Industry</div>
                  <div className="value">{data.industry || 'N/A'}</div>
                </div>
              </div>
            </div>

            {/* Technical Indicators */}
            <div className="modal-section">
              <h3>Technical Indicators</h3>
              <div className="detail-grid">
                <div className="detail-item">
                  <div className="label">RSI(14)</div>
                  <div className="value" style={{
                    color: data.rsi14 !== null && data.rsi14 < 30 ? 'var(--red)' : 'inherit'
                  }}>
                    {fmt(data.rsi14)}
                  </div>
                </div>
                <div className="detail-item">
                  <div className="label">MACD</div>
                  <div className="value">{fmt(data.macd, 4)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">MACD Signal</div>
                  <div className="value">{fmt(data.macd_signal, 4)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">SMA(20)</div>
                  <div className="value">{fmt(data.sma20)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">Close</div>
                  <div className="value">{fmt(data.close)}</div>
                </div>
                <div className="detail-item">
                  <div className="label">Score</div>
                  <div className="value" style={{ color: 'var(--accent)' }}>
                    {fmt(data.score)}
                  </div>
                </div>
              </div>
            </div>

            {/* Signals */}
            <div className="modal-section">
              <h3>Triggered Signals</h3>
              <div>
                {signalTags.map(s => (
                  <span
                    key={s.key}
                    className={`signal-tag ${signals[s.key] ? '' : 'inactive'}`}
                  >
                    {signals[s.key] ? '✓ ' : '✗ '}{s.label}
                  </span>
                ))}
              </div>
            </div>

            {/* Scanned At */}
            {data.created_at && (
              <div className="modal-section">
                <h3>Record Info</h3>
                <div className="detail-grid">
                  <div className="detail-item">
                    <div className="label">Scanned At</div>
                    <div className="value">
                      {(() => {
                        try {
                          return new Date(data.created_at).toLocaleString(undefined, {
                            year: 'numeric', month: 'short', day: 'numeric',
                            hour: '2-digit', minute: '2-digit', second: '2-digit',
                          });
                        } catch {
                          return data.created_at;
                        }
                      })()}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Reason */}
            {data.reason && (
              <div className="modal-section">
                <h3>Reason</h3>
                <div className="reason-text">{data.reason}</div>
              </div>
            )}

            {/* Charts */}
            <div className="modal-section">
              <h3>Charts</h3>
              <div className="tabs" style={{ borderBottom: 'none', marginBottom: '0.5rem' }}>
                <button
                  className={`tab-btn ${chartTab === 'price' ? 'active' : ''}`}
                  onClick={() => setChartTab('price')}
                >
                  Price
                </button>
                <button
                  className={`tab-btn ${chartTab === 'rsi' ? 'active' : ''}`}
                  onClick={() => setChartTab('rsi')}
                >
                  RSI
                </button>
                <button
                  className={`tab-btn ${chartTab === 'macd' ? 'active' : ''}`}
                  onClick={() => setChartTab('macd')}
                >
                  MACD
                </button>
              </div>
              <PriceChart
                priceSeries={data.price_series}
                rsiSeries={data.rsi_series}
                macdSeries={data.macd_series}
                activeTab={chartTab}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
