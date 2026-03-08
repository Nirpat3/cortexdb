import useSWR, { type SWRConfiguration } from 'swr';

export function useApi<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  options?: SWRConfiguration<T>
) {
  return useSWR<T>(key, fetcher, {
    revalidateOnFocus: false,
    errorRetryCount: 3,
    ...options,
  });
}
