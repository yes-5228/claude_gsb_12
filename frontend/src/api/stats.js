import { http } from './client.js';

export const statsApi = {
  overview: (params) => http.get('/stats/overview', params),
  dashboard: (params = {}) =>
    http.get('/stats/dashboard', {
      trend_days: params.trendDays ?? 14,
      district: params.district || '',
      grade: params.grade || '',
    }),
  methodology: () => http.get('/stats/methodology'),
  inspectionSummary: (params) => http.get('/stats/inspections/summary', params),
  issueSummary: (params) => http.get('/stats/issues/summary', params),
};
