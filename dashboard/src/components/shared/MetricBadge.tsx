'use client';

import { cn } from '@/lib/utils';

interface MetricBadgeProps {
  label: string;
  value: string | number;
  color?: string;
  className?: string;
}

export function MetricBadge({ label, value, color, className }: MetricBadgeProps) {
  return (
    <div className={cn('flex flex-col gap-0.5', className)}>
      <span className="text-[10px] uppercase tracking-wider text-white/40">{label}</span>
      <span className="text-lg font-semibold" style={color ? { color } : undefined}>
        {value}
      </span>
    </div>
  );
}
