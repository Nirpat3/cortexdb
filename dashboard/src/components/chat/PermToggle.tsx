'use client';
import { ShieldCheck, ShieldOff } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PermToggleProps {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  enabled: boolean;
  onChange: (v: boolean) => void;
  colorClass: string;
}

export function PermToggle({ label, icon: Icon, enabled, onChange, colorClass }: PermToggleProps) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={cn(
        'flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium transition-colors border',
        enabled
          ? `${colorClass} border-current/30`
          : 'border-[var(--border-default)] bg-[var(--bg-elevated)] text-[var(--text-muted)]',
      )}
      title={`${label}: ${enabled ? 'Hint allowed' : 'Hint denied'} (server enforces)`}
    >
      <Icon className="h-3 w-3" />
      {label}
      {enabled ? (
        <ShieldCheck className="h-3 w-3 ml-0.5 text-green-400" />
      ) : (
        <ShieldOff className="h-3 w-3 ml-0.5 text-red-400/60" />
      )}
    </button>
  );
}
