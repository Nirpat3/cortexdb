'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Bot, Activity, Shield, Database, Boxes, Bell, Bug, Brain,
  RefreshCw, CheckCircle2, AlertTriangle, XCircle, Clock, Cpu,
  Server, ChevronDown, ChevronUp,
} from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { MetricBadge } from '@/components/shared/MetricBadge';
import { HealthRing } from '@/components/shared/HealthRing';
import { StatusDot } from '@/components/shared/StatusDot';
import { api } from '@/lib/api';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const AGENT_ICONS: Record<string, typeof Bot> = {
  'AGT-SYS-001': Activity,
  'AGT-DB-001': Database,
  'AGT-SVC-001': Boxes,
  'AGT-SEC-001': Shield,
  'AGT-ERR-001': Bug,
  'AGT-NTF-001': Bell,
  'AGT-FRC-001': Brain,
};

const AGENT_COLORS: Record<string, string> = {
  'AGT-SYS-001': '#3B82F6',
  'AGT-DB-001': '#F59E0B',
  'AGT-SVC-001': '#6366F1',
  'AGT-SEC-001': '#EF4444',
  'AGT-ERR-001': '#EC4899',
  'AGT-NTF-001': '#FBBF24',
  'AGT-FRC-001': '#34D399',
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<D[]>([]);
  const [summary, setSummary] = useState<D | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.getAgentRegistry();
      setAgents((data as D).agents ?? []);
      setSummary((data as D).summary ?? null);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 10000);
    return () => clearInterval(iv);
  }, [refresh]);

  const statusColor = (s: string) =>
    s === 'active' || s === 'running' ? 'healthy' : s === 'idle' ? 'warning' : 'error';

  const statusIcon = (s: string) => {
    if (s === 'active' || s === 'running') return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
    if (s === 'idle') return <Clock className="w-4 h-4 text-amber-400" />;
    if (s === 'error') return <XCircle className="w-4 h-4 text-red-400" />;
    return <AlertTriangle className="w-4 h-4 text-white/40" />;
  };

  const formatUptime = (started: number) => {
    if (!started) return '-';
    const seconds = Date.now() / 1000 - started;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
    return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
  };

  if (loading) {
    return (
      <AppShell title="Agents" icon={Bot} color="#22D3EE">
        <div className="flex items-center justify-center h-64 text-white/40">
          <RefreshCw className="w-6 h-6 animate-spin mr-2" /> Loading agents...
        </div>
      </AppShell>
    );
  }

  const activeCount = summary?.active ?? 0;
  const totalCount = summary?.total_agents ?? 0;
  const healthPct = totalCount > 0 ? Math.round((activeCount / totalCount) * 100) : 0;

  return (
    <AppShell title="Agents" icon={Bot} color="#22D3EE">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold mb-1">Agent Registry</h2>
          <p className="text-sm text-white/40">All active AI agents, their roles, and responsibilities</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/90 transition">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-[140px_1fr] gap-4 mb-6">
        <GlassCard className="flex flex-col items-center py-4">
          <HealthRing value={healthPct} size={80} strokeWidth={6} label="Health" />
          <div className="text-xs text-white/40 mt-2">{activeCount}/{totalCount} active</div>
        </GlassCard>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <GlassCard><MetricBadge label="Total Agents" value={String(totalCount)} color="#22D3EE" /></GlassCard>
          <GlassCard><MetricBadge label="Active" value={String(activeCount)} color="#34D399" /></GlassCard>
          <GlassCard><MetricBadge label="Total Runs" value={String(summary?.total_runs ?? 0)} color="#8B5CF6" /></GlassCard>
          <GlassCard><MetricBadge label="Total Errors" value={String(summary?.total_errors ?? 0)} color="#EF4444" /></GlassCard>
        </div>
      </div>

      {/* Categories */}
      {summary?.categories && (
        <div className="flex gap-2 mb-6 flex-wrap">
          {summary.categories.map((cat: string) => (
            <span key={cat} className="glass px-3 py-1 rounded-full text-xs text-white/60">{cat}</span>
          ))}
        </div>
      )}

      {/* Agent Cards */}
      <div className="space-y-3">
        {agents.map((agent: D) => {
          const Icon = AGENT_ICONS[agent.agent_id] ?? Bot;
          const color = AGENT_COLORS[agent.agent_id] ?? '#6366F1';
          const isExpanded = expanded === agent.agent_id;

          return (
            <GlassCard key={agent.agent_id} className="py-4 cursor-pointer hover:bg-white/[0.03] transition"
              onClick={() => setExpanded(isExpanded ? null : agent.agent_id)}>
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${color}20` }}>
                    <Icon className="w-5 h-5" style={{ color }} />
                  </div>
                  <div>
                    <div className="text-base font-semibold">{agent.title}</div>
                    <div className="text-xs text-white/40">{agent.role}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <StatusDot status={statusColor(agent.status)} pulse={agent.status === 'active'} />
                  {statusIcon(agent.status)}
                  <span className="text-xs font-mono text-white/30">{agent.agent_id}</span>
                  {isExpanded ? <ChevronUp className="w-4 h-4 text-white/30" /> : <ChevronDown className="w-4 h-4 text-white/30" />}
                </div>
              </div>

              {/* Quick Stats */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs mb-2">
                <div className="flex items-center gap-1 text-white/50">
                  <Server className="w-3 h-3" /> {agent.microservice}
                </div>
                <div className="flex items-center gap-1 text-white/50">
                  <Cpu className="w-3 h-3" /> {agent.run_count} runs
                </div>
                <div className="flex items-center gap-1 text-white/50">
                  <Clock className="w-3 h-3" /> {agent.avg_run_ms}ms avg
                </div>
                <div className="text-white/50">
                  Category: <span style={{ color }}>{agent.category}</span>
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div className="mt-4 pt-4 border-t border-white/5 space-y-4">
                  {/* Responsibilities */}
                  <div>
                    <div className="text-xs text-white/40 mb-2 font-medium">Responsibilities</div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                      {(agent.responsibilities ?? []).map((r: string, i: number) => (
                        <div key={i} className="flex items-center gap-2 text-sm text-white/60">
                          <CheckCircle2 className="w-3 h-3 shrink-0" style={{ color }} />
                          {r}
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Performance */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <GlassCard>
                      <MetricBadge label="Total Runs" value={String(agent.run_count)} color="#3B82F6" />
                    </GlassCard>
                    <GlassCard>
                      <MetricBadge label="Errors" value={String(agent.errors)} color={agent.errors > 0 ? '#EF4444' : '#34D399'} />
                    </GlassCard>
                    <GlassCard>
                      <MetricBadge label="Avg Runtime" value={`${agent.avg_run_ms}ms`} color="#F59E0B" />
                    </GlassCard>
                    <GlassCard>
                      <MetricBadge label="Uptime" value={formatUptime(agent.uptime_since)} color="#8B5CF6" />
                    </GlassCard>
                  </div>

                  {/* Last Run */}
                  {agent.last_run > 0 && (
                    <div className="text-xs text-white/30">
                      Last run: {new Date(agent.last_run * 1000).toLocaleString()}
                    </div>
                  )}
                </div>
              )}
            </GlassCard>
          );
        })}
      </div>

      {agents.length === 0 && (
        <GlassCard className="text-center py-12">
          <Bot className="w-12 h-12 text-white/20 mx-auto mb-3" />
          <div className="text-lg font-medium text-white/50">No Agents Registered</div>
          <div className="text-sm text-white/30">Agents will appear here once the backend is running</div>
        </GlassCard>
      )}
    </AppShell>
  );
}
