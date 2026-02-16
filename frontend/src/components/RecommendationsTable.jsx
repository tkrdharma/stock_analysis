import React, { useState, useMemo, useEffect } from 'react';

const COLUMNS = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'cmp', label: 'CMP', numeric: true },
  { key: 'pe', label: 'PE', numeric: true },
  { key: 'roce', label: 'ROCE', numeric: true },
  { key: 'debt', label: 'Debt', numeric: true },
  { key: 'rsi_divergence', label: 'RSI Divergence' },
  { key: 'macd_divergence', label: 'MACD Divergence' },
];

function fmt(val, digits = 2) {
  if (val === null || val === undefined) return <span className="na">N/A</span>;
  if (typeof val === 'number') return val.toFixed(digits);
  return val;
}

export default function RecommendationsTable({ rows, showAll, onRowClick, onDelete }) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState('symbol');
  const [sortAsc, setSortAsc] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const cols = COLUMNS;

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    let arr = rows.filter(r =>
      !q ||
      (r.symbol || '').toLowerCase().includes(q)
    );
    arr.sort((a, b) => {
      let va = a[sortKey], vb = b[sortKey];
      if (va === null || va === undefined) va = sortAsc ? Infinity : -Infinity;
      if (vb === null || vb === undefined) vb = sortAsc ? Infinity : -Infinity;
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortAsc ? -1 : 1;
      if (va > vb) return sortAsc ? 1 : -1;
      return 0;
    });
    return arr;
  }, [rows, search, sortKey, sortAsc]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const startIdx = (safePage - 1) * pageSize;
  const endIdx = startIdx + pageSize;
  const paged = filtered.slice(startIdx, endIdx);

  const resetPageIfNeeded = () => {
    if (page !== 1) setPage(1);
  };

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
    resetPageIfNeeded();
  };

  if (!rows.length) {
    return (
      <div className="empty-state">
        <p>No data yet. Load symbols and run a scan to see results.</p>
      </div>
    );
  }

  return (
    <>
      <div className="controls">
        <input
          className="search-box"
          placeholder="Search stocks..."
          value={search}
          onChange={e => {
            setSearch(e.target.value);
            resetPageIfNeeded();
          }}
        />
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {filtered.length} result{filtered.length !== 1 ? 's' : ''}
        </span>
        <div className="pager-controls">
          <label className="pager-label">
            Rows
            <select
              className="pager-select"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </label>
          <button
            className="btn btn-secondary"
            onClick={() => setPage(Math.max(1, safePage - 1))}
            disabled={safePage <= 1}
          >
            Prev
          </button>
          <span className="pager-info">Page {safePage} of {totalPages}</span>
          <button
            className="btn btn-secondary"
            onClick={() => setPage(Math.min(totalPages, safePage + 1))}
            disabled={safePage >= totalPages}
          >
            Next
          </button>
        </div>
      </div>

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {cols.map(c => (
                <th key={c.key} onClick={() => toggleSort(c.key)}>
                  {c.label}
                  {sortKey === c.key && (
                    <span className="sort-icon">{sortAsc ? '▲' : '▼'}</span>
                  )}
                </th>
              ))}
              <th>Delete</th>
            </tr>
          </thead>
          <tbody>
            {paged.map((row, i) => (
              <tr key={row.symbol + i} onClick={() => onRowClick(row.symbol)}>
                {cols.map(c => (
                  <td key={c.key}>
                    {c.key === 'recommended'
                      ? (row[c.key] ? '✅' : '—')
                      : c.numeric
                        ? fmt(row[c.key])
                        : (row[c.key] ?? <span className="na">N/A</span>)
                    }
                  </td>
                ))}
                <td>
                  <button
                    className="btn btn-secondary"
                    onClick={(e) => {
                      e.stopPropagation();
                      onDelete?.(row.symbol);
                    }}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
