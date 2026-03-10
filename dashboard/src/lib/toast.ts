/**
 * Lightweight toast wrapper around sonner.
 * Replaces silent .catch(() => {}) with user-visible feedback.
 */
import { toast as sonnerToast } from 'sonner';

export const toast = {
  success: (msg: string) => sonnerToast.success(msg),
  error: (msg: string) => sonnerToast.error(msg),
  info: (msg: string) => sonnerToast.info(msg),
  /** Show error from caught exception */
  apiError: (action: string, err: unknown) => {
    const message = err instanceof Error ? err.message : 'Unknown error';
    sonnerToast.error(`${action}: ${message}`);
  },
};
