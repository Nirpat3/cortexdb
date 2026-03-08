'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Radio, RefreshCw, Trash2, Wifi, WifiOff, Filter } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

interface FeedEvent {
  type: string;
  data: D;
  timestamp: number;
}

function badgeColor(type: string): string {
  if (type.startsWith('task_')) return 'bg-blue-500/20 text-blue-300';
  if (type.startsWith('agent_')) return 'bg-emerald-500/20 text-emerald-300';
  if (type.startsWith('bus_')) return 'bg-amber-500/20 text-amber-300';
  if (type.startsWith('autonomy_')) return 'bg-purple-500/20 text-purple-300';
  if (type.startsWith('tool_')) return 'bg-cyan-500/20 text-cyan-300';
  if (type.includes('error') || type.includes('alert')) return 'bg-red-500/20 text-red-300';
  return 'bg-white/10 text-white/40';
}

function formatTs(ts: number): string {
  return new Date(ts * 1000 > Date.now() + 86400000 ? ts : ts * 1000)
    .toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function truncate(data: D): string {
  const s = JSON.stringify(data);
  return s.length > 200 ? s.slice(0, 200) + '...' : s;
}

export default function LiveFeedPage() {
  const { t } = useTranslation();
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [wsConnected, setWsConnected] = useState(false);
  const [typeFilter, setTypeFilter] = useState('');
  const [expanded, setExpanded] = useState<number | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refresh = useCallback(async () => {
    try {
      const res = await superadminApi.getLiveFeed(200);
      const d = res as { events: FeedEvent[]; total: number };
      setEvents(d.events ?? []);
      setTotal(d.total ?? 0);
    } catch { /* silent */ }
  }, []);

  // WebSocket connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const saToken = sessionStorage.getItem('sa_token') ?? '';
    const wsUrl = `${protocol}//${window.location.hostname}:5400/ws/events?token=${encodeURIComponent(saToken)}`;

    function connect() {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setWsConnected(true);
      };

      ws.onmessage = (msg) => {
        try {
          const event: FeedEvent = JSON.parse(msg.data);
          setEvents((prev) => {
            const next = [event, ...prev];
            return next.slice(0, 500);
          });
          setTotal((prev) => prev + 1);
        } catch { /* ignore non-json */ }
      };

      ws.onclose = () => {
        setWsConnected(false);
        // Reconnect after 3 seconds
        setTimeout(connect, 3000);
      };

      ws.onerror = () => {
        setWsConnected(false);
      };
    }

    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, []);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Polling fallback when WebSocket is not connected
  useEffect(() => {
    if (autoRefresh && !wsConnected) {
      intervalRef.current = setInterval(refresh, 3000);
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [autoRefresh, wsConnected, refresh]);

  const handleClear = () => {
    setEvents([]);
    setTotal(0);
  };

  // Filter events by type
  const filteredEvents = typeFilter
    ? events.filter((e) => e.type.includes(typeFilter))
    : events;

  // Unique event types for filter dropdown
  const eventTypes = [...new Set(events.map((e) => e.type))].sort();

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Radio className="w-6 h-6 text-emerald-400" />
            {t('liveFeed.title')}
            <span className="relative flex h-2.5 w-2.5 ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
            </span>
          </h1>
          <p className="text-sm text-white/40">
            {total} {t('common.total')} · {filteredEvents.length} {t('common.shown')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {/* WebSocket status */}
          <div className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs ${
            wsConnected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
          }`}>
            {wsConnected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
            {wsConnected ? t('common.live') : t('common.polling')}
          </div>

          {/* Type filter */}
          <div className="relative">
            <Filter className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-white/30" />
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg pl-8 pr-3 py-2 text-xs text-white/60 appearance-none focus:outline-none"
            >
              <option value="">{t('liveFeed.allTypes')}</option>
              {eventTypes.map((evtType) => (
                <option key={evtType} value={evtType}>{evtType}</option>
              ))}
            </select>
          </div>

          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs transition ${
              autoRefresh
                ? 'bg-emerald-500/20 text-emerald-300'
                : 'bg-white/5 text-white/40 border border-white/10'
            }`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${autoRefresh && !wsConnected ? 'animate-spin' : ''}`} />
            {autoRefresh ? t('common.autoOn') : t('common.autoOff')}
          </button>
          <button
            onClick={refresh}
            className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs text-white/60 hover:text-white/90"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs bg-red-500/10 text-red-400 hover:bg-red-500/20"
          >
            <Trash2 className="w-3.5 h-3.5" /> {t('common.clear')}
          </button>
        </div>
      </div>

      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="max-h-[calc(100vh-200px)] overflow-y-auto divide-y divide-white/5">
          {filteredEvents.length === 0 && (
            <div className="text-center py-16 text-white/30">{t('liveFeed.noEvents')}</div>
          )}
          {filteredEvents.map((evt, i) => (
            <div
              key={`${evt.timestamp}-${i}`}
              className="px-4 py-3 hover:bg-white/[0.03] transition cursor-pointer"
              onClick={() => setExpanded(expanded === i ? null : i)}
            >
              <div className="flex items-center gap-3">
                <span className="text-[11px] font-mono text-white/30 shrink-0 w-20">
                  {formatTs(evt.timestamp)}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded-full shrink-0 ${badgeColor(evt.type)}`}>
                  {evt.type}
                </span>
                <span className="text-xs text-white/50 truncate flex-1">
                  {truncate(evt.data)}
                </span>
              </div>
              {expanded === i && (
                <pre className="mt-2 ml-24 text-[11px] text-white/40 bg-white/5 rounded-lg p-3 overflow-x-auto max-h-60">
                  {JSON.stringify(evt.data, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
