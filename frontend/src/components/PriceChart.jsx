import React from 'react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Bar, BarChart,
  ComposedChart, Area,
} from 'recharts';

const COLORS = {
  price: '#4f8cff',
  rsi: '#eab308',
  macd: '#22c55e',
  signal: '#ef4444',
  histogram: '#6366f1',
};

function formatDate(d) {
  if (!d) return '';
  // "2025-08-15" → "Aug 15"
  const parts = d.split('-');
  if (parts.length < 3) return d;
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  return `${months[parseInt(parts[1], 10) - 1]} ${parseInt(parts[2], 10)}`;
}

export default function PriceChart({ priceSeries, rsiSeries, macdSeries, activeTab }) {
  if (activeTab === 'price') {
    if (!priceSeries?.length) {
      return <div className="empty-state"><p>No price data available</p></div>;
    }
    return (
      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={priceSeries}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
            <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: '#8b8fa3', fontSize: 11 }} />
            <YAxis domain={['auto', 'auto']} tick={{ fill: '#8b8fa3', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1a1d28', border: '1px solid #2a2d3a', borderRadius: 6 }}
              labelStyle={{ color: '#8b8fa3' }}
            />
            <Line
              type="monotone"
              dataKey="close"
              stroke={COLORS.price}
              dot={false}
              strokeWidth={1.5}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (activeTab === 'rsi') {
    if (!rsiSeries?.length) {
      return <div className="empty-state"><p>No RSI data available</p></div>;
    }
    return (
      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rsiSeries}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
            <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: '#8b8fa3', fontSize: 11 }} />
            <YAxis domain={[0, 100]} tick={{ fill: '#8b8fa3', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1a1d28', border: '1px solid #2a2d3a', borderRadius: 6 }}
              labelStyle={{ color: '#8b8fa3' }}
            />
            <ReferenceLine y={30} stroke="#ef4444" strokeDasharray="4 4" label={{ value: 'Oversold (30)', fill: '#ef4444', fontSize: 11 }} />
            <ReferenceLine y={70} stroke="#22c55e" strokeDasharray="4 4" label={{ value: 'Overbought (70)', fill: '#22c55e', fontSize: 11 }} />
            <Line
              type="monotone"
              dataKey="rsi"
              stroke={COLORS.rsi}
              dot={false}
              strokeWidth={1.5}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (activeTab === 'macd') {
    if (!macdSeries?.length) {
      return <div className="empty-state"><p>No MACD data available</p></div>;
    }
    return (
      <div className="chart-container">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={macdSeries}>
            <CartesianGrid strokeDasharray="3 3" stroke="#2a2d3a" />
            <XAxis dataKey="date" tickFormatter={formatDate} tick={{ fill: '#8b8fa3', fontSize: 11 }} />
            <YAxis tick={{ fill: '#8b8fa3', fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: '#1a1d28', border: '1px solid #2a2d3a', borderRadius: 6 }}
              labelStyle={{ color: '#8b8fa3' }}
            />
            <ReferenceLine y={0} stroke="#555" />
            <Bar dataKey="histogram" fill={COLORS.histogram} opacity={0.4} />
            <Line type="monotone" dataKey="macd" stroke={COLORS.macd} dot={false} strokeWidth={1.5} />
            <Line type="monotone" dataKey="signal" stroke={COLORS.signal} dot={false} strokeWidth={1.5} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    );
  }

  return null;
}
