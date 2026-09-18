import { http } from './client.js';

export const statsApi = {
  overview: (params) => http.get('/stats/overview', params),
  dashboard: ({ trendDays = 14, district = '', grade = '' } = {}) =>
    http.get('/stats/dashboard', {
      trend_days: trendDays,
      district,
      grade,
    }),
};
