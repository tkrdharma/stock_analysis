import React, { useState, useMemo } from 'react';

const COLUMNS = [
  { key: 'stock_name', label: 'Stock Name' },
  { key: 'symbol', label: 'Symbol' },
  { key: 'cmp', label: 'CMP', numeric: true },
  { key: 'pe', label: 'PE', numeric: true },
  { key: 'roce', label: 'ROCE', numeric: true },
  { key: 'bv', label: 'BV', numeric: true },
  { key: 'industry', label: 'Industry' },
  { key: 'score', label: 'Score', numeric: true },
  { key: 'reason', label: 'Reason' },
];

const ALL_EXTRA_COLUMNS = [
  { key: 'rsi14', label: 'RSI(14)', numeric: true },
  { key: 'close', label: 'Close', numeric: true },
  { key: 'recommended', label: 'Rec?', numeric: false },
];

function fmt(val, digits = 2) {
  if (val === null || val === undefined) return <span className="na">N/A</span>;
  if (typeof val === 'number') return val.toFixed(digits);
  return val;
}

export default function RecommendationsTable({ rows, showAll, onRowClick, onDelete }) {
  const [search, setSearch] = useState('');
  const [sortKey, setSortKey] = useState('score');
  const [sortAsc, setSortAsc] = useState(false);

  const cols = showAll ? [...COLUMNS.slice(0, 7), ...ALL_EXTRA_COLUMNS, ...COLUMNS.slice(7)] : COLUMNS;

  const filtered = useMemo(() => {
    const q = search.toLowerCase();
    let arr = rows.filter(r =>
      !q ||
      (r.symbol || '').toLowerCase().includes(q) ||
      (r.stock_name || '').toLowerCase().includes(q) ||
      (r.industry || '').toLowerCase().includes(q) ||
      (r.reason || '').toLowerCase().includes(q)
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

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
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
          onChange={e => setSearch(e.target.value)}
        />
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          {filtered.length} result{filtered.length !== 1 ? 's' : ''}
        </span>
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
            {filtered.map((row, i) => (
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
