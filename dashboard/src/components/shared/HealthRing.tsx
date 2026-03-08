'use client';

import { statusColor } from '@/lib/utils';

interface HealthRingProps {
  value: number; // 0-100
  size?: number;
  strokeWidth?: number;
  status?: string;
  label?: string;
}

export function HealthRing({ value, size = 64, strokeWidth = 5, status, label }: HealthRingProps) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const color = status ? statusColor(status) : value >= 80 ? '#34D399' : value >= 50 ? '#FBBF24' : '#EF4444';

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.1)"
          strokeWidth={strokeWidth}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 0.8s ease' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="text-sm font-bold" style={{ color }}>{value}</span>
        {label && <span className="text-[8px] text-white/40">{label}</span>}
      </div>
    </div>
  );
}
