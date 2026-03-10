import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* ── From HEAD: date/file helpers ── */

export function formatTime(d: Date) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function formatDate(d: Date) {
  const today = new Date();
  if (d.toDateString() === today.toDateString()) return 'Today';
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / 1048576).toFixed(1)}MB`;
}

/** Max file attachment size: 10MB */
export const MAX_FILE_SIZE = 10 * 1024 * 1024;

/** Validate file before reading into memory */
export function validateFile(file: File): string | null {
  if (file.size > MAX_FILE_SIZE) {
    return `File "${file.name}" exceeds ${formatFileSize(MAX_FILE_SIZE)} limit (${formatFileSize(file.size)})`;
  }
  return null;
}

/* ── From v5: metric/status formatters ── */

export function formatMs(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(1)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
}

export function formatPercent(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export function statusColor(status: string): string {
  switch (status?.toLowerCase()) {
    case 'ok':
    case 'healthy':
    case 'pass':
    case 'alive':
    case 'closed':
      return '#34D399';
    case 'degraded':
    case 'warning':
    case 'partial':
    case 'half_open':
      return '#FBBF24';
    case 'down':
    case 'unhealthy':
    case 'fail':
    case 'critical':
    case 'open':
      return '#EF4444';
    default:
      return '#6B7280';
  }
}

export function timeAgo(date: string | number): string {
  const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
