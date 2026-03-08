'use client';

import { useEffect, useState, useCallback } from 'react';
import { ScrollText, RefreshCw, Filter } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const TYPE_COLORS: Record<string, string> = {
  task: 'bg-amber-500/20 text-amber-300',
  message: 'bg-blue-500/20 text-blue-300',
  agent: 'bg-purple-500/20 text-purple-300',
  instruction: 'bg-cyan-500/20 text-cyan-300',
};

export default function AuditLogPage() {
  const { t } = useTranslation();
  const [log, setLog] = useState<D[]>([]);
  const [filter, setFilter] = useState('all');

  const refresh = useCallback(async () => {
    try {
      const entityType = filter === 'all' ? undefined : filter;
      const data = await superadminApi.getAuditLog(entityType, 200);
      setLog((data as D).log ?? []);
    } catch { /* silent */ }
  }, [filter]);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <ScrollText className="w-6 h-6 text-emerald-400" /> {t('audit.title')}
          </h1>
          <p className="text-sm text-white/40">{t('audit.subtitle')}</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-2 mb-4">
        <Filter className="w-3.5 h-3.5 text-white/40" />
        {['all', 'task', 'message', 'agent', 'instruction'].map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs capitalize transition ${
              filter === f ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'
            }`}>
            {f === 'all' ? t('common.all') : f}
          </button>
        ))}
      </div>

      {/* Log Entries */}
      <div className="space-y-1">
        {log.length === 0 && (
          <div className="text-center py-12 text-white/30">{t('common.noData')}</div>
        )}
        {log.map((entry: D, i: number) => (
          <div key={i} className="glass rounded-lg px-4 py-3 flex items-center gap-3">
            <div className="text-[10px] text-white/20 font-mono w-20 shrink-0">
              {entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleTimeString() : ''}
            </div>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full shrink-0 ${TYPE_COLORS[entry.entity_type] ?? 'bg-white/10 text-white/40'}`}>
              {entry.entity_type}
            </span>
            <div className="flex-1 min-w-0">
              <span className="text-sm text-white/70">{entry.action}</span>
              <span className="text-xs text-white/30 ml-2 font-mono">{entry.entity_id}</span>
            </div>
            <div className="text-[10px] text-white/20 shrink-0">{entry.actor}</div>
            {entry.details && Object.keys(entry.details).length > 0 && (
              <div className="text-[10px] text-white/20 max-w-[200px] truncate">
                {JSON.stringify(entry.details)}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
