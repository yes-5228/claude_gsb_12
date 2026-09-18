import { statsApi } from '../api/stats.js';
import { useAsync } from './useAsync.js';

let cache = null;

/** 统计口径说明只需拉取一次，模块级缓存与字典保持一致。 */
export function useMethodology() {
  const { data, loading, error } = useAsync(async () => {
    if (cache) return cache;
    cache = await statsApi.methodology();
    return cache;
  }, []);

  return { methodology: data ?? cache, loading: loading && !cache, error };
}

export function clearMethodologyCache() {
  cache = null;
}
