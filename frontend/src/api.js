import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 min for scans
});

export const reloadSymbols = () => api.post('/symbols/reload').then(r => r.data);
export const runScan       = () => api.post('/scan/run').then(r => r.data);
export const getScan       = (id) => api.get(`/scan/${id}`).then(r => r.data);
export const getLatest     = () => api.get('/recommendations/latest').then(r => r.data);
export const getLatestAll  = () => api.get('/recommendations/latest/all').then(r => r.data);
export const deleteFromLatestScan = (symbol) => api.delete(`/scan/latest/symbol/${symbol}`).then(r => r.data);
export const deleteFromScan = (scanId, symbol) => api.delete(`/scan/${scanId}/symbol/${symbol}`).then(r => r.data);
export const getDetails    = (symbol, scanId) => {
  const params = scanId ? { scan_id: scanId } : {};
  return api.get(`/symbol/${symbol}/details`, { params }).then(r => r.data);
};
