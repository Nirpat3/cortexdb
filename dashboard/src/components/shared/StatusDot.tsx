'use client';

import { cn } from '@/lib/utils';
import { statusColor } from '@/lib/utils';

interface StatusDotProps {
  status: string;
  size?: 'sm' | 'md' | 'lg';
  pulse?: boolean;
}

export function StatusDot({ status, size = 'md', pulse }: StatusDotProps) {
  const color = statusColor(status);
  const sizeClasses = { sm: 'w-2 h-2', md: 'w-3 h-3', lg: 'w-4 h-4' };

  return (
    <span className="relative inline-flex">
      {pulse && (
        <span
          className={cn('absolute inline-flex rounded-full opacity-50 animate-ping', sizeClasses[size])}
          style={{ backgroundColor: color }}
        />
      )}
      <span
        className={cn('relative inline-flex rounded-full', sizeClasses[size])}
        style={{ backgroundColor: color }}
      />
    </span>
  );
}
