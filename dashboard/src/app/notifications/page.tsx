'use client';

import { useState, useEffect, useCallback } from 'react';
import { Bell, AlertTriangle, CheckCircle2, Info, XCircle, Filter, BellOff, RefreshCw } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<D[]>([]);
  const [summary, setSummary] = useState<D | null>(null);
  const [filter, setFilter] = useState<string>('all');

  const refresh = useCallback(async () => {
    try {
      const severity = filter === 'all' ? undefined : filter;
      const [n, s] = await Promise.all([
        api.getNotifications({ severity, limit: 50 }).catch(() => null),
        api.notificationSummary().catch(() => null),
      ]);
      if (n) setNotifications((n as D).notifications ?? []);
      if (s) setSummary(s);
    } catch { /* silent */ }
  }, [filter]);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 8000);
    return () => clearInterval(iv);
  }, [refresh]);

  const handleMarkRead = async (id: string) => {
    try {
      await api.markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.notif_id === id ? { ...n, read: true } : n));
    } catch { /* silent */ }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllNotificationsRead();
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
    } catch { /* silent */ }
  };

  const sevIcon = (severity: string) => {
    if (severity === 'critical') return <XCircle className="w-4 h-4 text-red-400" />;
    if (severity === 'warning') return <AlertTriangle className="w-4 h-4 text-amber-400" />;
    if (severity === 'success') return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
    return <Info className="w-4 h-4 text-blue-400" />;
  };

  const sevBorder = (severity: string) =>
    severity === 'critical' ? 'border-red-500/30' : severity === 'warning' ? 'border-amber-500/20' : severity === 'success' ? 'border-emerald-500/20' : 'border-white/5';

  const timeAgo = (ts: number) => {
    const diff = Date.now() / 1000 - ts;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  };

  return (
    <AppShell title="Notifications" icon={Bell} color="#F59E0B">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Notifications</h2>
          <p className="text-sm text-white/40">Real-time alerts from Notification Agent</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={handleMarkAllRead} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition flex items-center gap-1">
            <BellOff className="w-3.5 h-3.5" /> Mark all read
          </button>
          <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Summary */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <GlassCard><MetricBadge label="Total" value={String(summary.total)} color="#6366F1" /></GlassCard>
          <GlassCard><MetricBadge label="Unread" value={String(summary.unread)} color="#EF4444" /></GlassCard>
          <GlassCard><MetricBadge label="Last Hour" value={String(summary.last_hour)} color="#F59E0B" /></GlassCard>
          <GlassCard>
            <div className="text-xs text-white/40 mb-1">By Severity</div>
            <div className="flex gap-2 text-xs">
              {Object.entries(summary.by_severity ?? {}).map(([s, c]) => (
                <span key={s} className={`${s === 'critical' ? 'text-red-400' : s === 'warning' ? 'text-amber-400' : 'text-white/50'}`}>
                  {String(c)} {s}
                </span>
              ))}
            </div>
          </GlassCard>
        </div>
      )}

      {/* Filter */}
      <div className="flex items-center gap-2 mb-4">
        <Filter className="w-4 h-4 text-white/40" />
        {['all', 'critical', 'warning', 'info', 'success'].map((f) => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1 rounded-lg text-xs capitalize transition ${filter === f ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {f}
          </button>
        ))}
      </div>

      {/* Notification List */}
      <div className="space-y-2">
        {notifications.map((n: D) => (
          <GlassCard key={n.notif_id}
            className={`py-3 border ${sevBorder(n.severity)} ${!n.read ? 'bg-white/[0.03]' : ''}`}
            onClick={() => !n.read && handleMarkRead(n.notif_id)}>
            <div className="flex items-start gap-3">
              <div className="mt-0.5">{sevIcon(n.severity)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-sm font-medium">{n.title}</span>
                  <div className="flex items-center gap-2">
                    {!n.read && <span className="w-2 h-2 rounded-full bg-blue-400" />}
                    <span className="text-[10px] text-white/30">{n.timestamp ? timeAgo(n.timestamp) : ''}</span>
                  </div>
                </div>
                <div className="text-xs text-white/50">{n.message}</div>
                <div className="flex items-center gap-2 mt-1 text-[10px] text-white/25">
                  <span>{n.source}</span>
                  <span>{n.category}</span>
                </div>
              </div>
            </div>
          </GlassCard>
        ))}
      </div>
    </AppShell>
  );
}
