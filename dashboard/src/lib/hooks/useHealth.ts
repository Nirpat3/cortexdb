import { api } from '@/lib/api';
import { useApi } from './useApi';

export function useHealth() {
  return useApi('health-ready', api.healthReady, { refreshInterval: 5000 });
}

export function useHealthDeep() {
  return useApi('health-deep', api.healthDeep, { refreshInterval: 10000 });
}
