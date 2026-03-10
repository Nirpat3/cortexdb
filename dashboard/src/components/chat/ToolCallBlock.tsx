'use client';
import { useState } from 'react';
import { Play, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolCallEntry } from '@/lib/api';

export function ToolCallBlock({ tc }: { tc: ToolCallEntry }) {
  const [expanded, setExpanded] = useState(false);
  const isError = typeof tc.result === 'object' && tc.result !== null && 'error' in (tc.result as Record<string, unknown>);

  return (
    <div className="my-1 rounded border border-[var(--border-default)] bg-[#111] text-xs">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2 py-1 hover:bg-[var(--bg-hover)]"
      >
        <Play className="h-3 w-3 text-blue-400" />
        <span className={cn('font-mono', isError ? 'text-red-400' : 'text-cyan-400')}>
          {tc.tool}
        </span>
        <span className="ml-auto text-[var(--text-muted)]">{tc.durationMs}ms</span>
        <ChevronDown className={cn('h-3 w-3 transition-transform', expanded && 'rotate-180')} />
      </button>
      {expanded && (
        <div className="border-t border-[var(--border-default)] px-2 py-1 space-y-1">
          <div>
            <span className="text-[var(--text-muted)]">Input:</span>
            <pre className="mt-0.5 text-green-400/80 whitespace-pre-wrap break-all max-h-32 overflow-auto">
              {JSON.stringify(tc.input, null, 2)}
            </pre>
          </div>
          <div>
            <span className="text-[var(--text-muted)]">Output:</span>
            <pre
              className={cn(
                'mt-0.5 whitespace-pre-wrap break-all max-h-48 overflow-auto',
                isError ? 'text-red-400' : 'text-amber-400/80',
              )}
            >
              {typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
