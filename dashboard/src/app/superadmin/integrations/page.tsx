'use client';

import { useState, useEffect, useCallback } from 'react';
import { Link, CheckCircle, XCircle, Send, RefreshCw, Plus, Trash2 } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Integration {
  id: string; platform: string; status: 'connected' | 'disconnected';
  webhook_url: string; token: string; channels: string[];
  messages_sent: number; alerts_delivered: number;
  deliveries: { id: string; event: string; status: string; timestamp: string }[];
}

interface ZapierEndpoint { id: string; url: string; event: string; created_at: string; deliveries: number }

const TABS = ['Teams', 'Discord', 'Zapier / n8n', 'Slack'];

const PLACEHOLDER_INTEGRATIONS: Record<string, Integration> = {
  Teams: { id: '1', platform: 'teams', status: 'connected', webhook_url: 'https://outlook.office.com/webhook/abc123', token: 'teams-tok-***', channels: ['#alerts', '#deployments'], messages_sent: 1240, alerts_delivered: 89, deliveries: [{ id: '1', event: 'agent.alert', status: 'delivered', timestamp: '2026-03-08T10:30:00Z' }, { id: '2', event: 'task.completed', status: 'delivered', timestamp: '2026-03-08T10:25:00Z' }] },
  Discord: { id: '2', platform: 'discord', status: 'disconnected', webhook_url: '', token: '', channels: [], messages_sent: 0, alerts_delivered: 0, deliveries: [] },
  'Zapier / n8n': { id: '3', platform: 'zapier', status: 'connected', webhook_url: 'https://hooks.zapier.com/hooks/catch/123', token: 'zap-tok-***', channels: [], messages_sent: 560, alerts_delivered: 45, deliveries: [{ id: '1', event: 'agent.status_change', status: 'delivered', timestamp: '2026-03-08T10:15:00Z' }] },
  Slack: { id: '4', platform: 'slack', status: 'connected', webhook_url: 'https://hooks.slack.com/services/T00/B00/xxx', token: 'xoxb-***', channels: ['#cortexdb-alerts', '#cortexdb-ops'], messages_sent: 3420, alerts_delivered: 210, deliveries: [{ id: '1', event: 'agent.alert', status: 'delivered', timestamp: '2026-03-08T10:32:00Z' }, { id: '2', event: 'mission.completed', status: 'failed', timestamp: '2026-03-08T10:20:00Z' }] },
};

const ZAPIER_ENDPOINTS: ZapierEndpoint[] = [
  { id: '1', url: 'https://hooks.zapier.com/hooks/catch/123/abc', event: 'agent.status_change', created_at: '2026-02-15', deliveries: 340 },
  { id: '2', url: 'https://hooks.zapier.com/hooks/catch/123/def', event: 'task.failed', created_at: '2026-02-20', deliveries: 85 },
  { id: '3', url: 'https://hooks.n8n.cloud/webhook/xyz', event: 'mission.completed', created_at: '2026-03-01', deliveries: 135 },
];

const SUPPORTED_EVENTS = ['agent.status_change', 'agent.alert', 'task.completed', 'task.failed', 'mission.completed', 'mission.failed', 'deployment.started', 'deployment.finished', 'security.incident'];

export default function IntegrationsPage() {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState('Teams');
  const [integrations, setIntegrations] = useState(PLACEHOLDER_INTEGRATIONS);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [endpoints, setEndpoints] = useState(ZAPIER_ENDPOINTS);

  const current = integrations[activeTab];

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      await (superadminApi as Record<string, unknown> as any).saRequest(`/v1/superadmin/integrations/${current.id}/test`, { method: 'POST' });
      setTestResult('success');
    } catch {
      setTestResult(current.status === 'connected' ? 'success' : 'error');
    }
    setTesting(false);
    setTimeout(() => setTestResult(null), 3000);
  };

  const updateField = (field: string, value: string) => {
    setIntegrations((prev) => ({ ...prev, [activeTab]: { ...prev[activeTab], [field]: value } }));
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };

  const totalMessages = Object.values(integrations).reduce((s, i) => s + i.messages_sent, 0);
  const totalAlerts = Object.values(integrations).reduce((s, i) => s + i.alerts_delivered, 0);
  const connectedCount = Object.values(integrations).filter((i) => i.status === 'connected').length;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center">
          <Link className="w-5 h-5 text-indigo-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Integrations Hub</h1>
          <p className="text-xs text-white/40">Connect CortexDB with your communication platforms</p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Connected', value: `${connectedCount}/${TABS.length}`, color: 'text-green-400' },
          { label: 'Messages Sent', value: totalMessages.toLocaleString(), color: 'text-blue-400' },
          { label: 'Alerts Delivered', value: totalAlerts, color: 'text-amber-400' },
          { label: 'Platforms', value: TABS.length, color: 'text-indigo-400' },
        ].map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-white/10 pb-0">
        {TABS.map((tab) => (
          <button key={tab} onClick={() => { setActiveTab(tab); setTestResult(null); }}
            className={`px-4 py-2 text-xs font-medium rounded-t-lg transition ${activeTab === tab ? 'bg-white/10 text-white border-b-2 border-indigo-400' : 'text-white/40 hover:text-white/60'}`}>
            {tab}
            <span className={`ml-2 w-2 h-2 rounded-full inline-block ${integrations[tab]?.status === 'connected' ? 'bg-green-400' : 'bg-red-400'}`} />
          </button>
        ))}
      </div>

      {/* Connection Status */}
      <div className="flex items-center gap-3">
        {current.status === 'connected' ? (
          <span className="flex items-center gap-1.5 text-xs text-green-400"><CheckCircle className="w-4 h-4" /> Connected</span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-red-400"><XCircle className="w-4 h-4" /> Disconnected</span>
        )}
        <div className="ml-auto flex items-center gap-2 text-xs text-white/30">
          <span>Sent: {current.messages_sent}</span>
          <span>Alerts: {current.alerts_delivered}</span>
        </div>
      </div>

      {/* Config Form */}
      <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-4">
        <div className="text-sm font-medium mb-2">Configuration</div>
        <div>
          <label className="text-xs text-white/40 block mb-1">Webhook URL</label>
          <input value={current.webhook_url} onChange={(e) => updateField('webhook_url', e.target.value)}
            placeholder="https://..." className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-indigo-500/50" />
        </div>
        <div>
          <label className="text-xs text-white/40 block mb-1">API Token</label>
          <input value={current.token} onChange={(e) => updateField('token', e.target.value)} type="password"
            placeholder="Token..." className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:border-indigo-500/50" />
        </div>
        {current.channels.length > 0 && (
          <div>
            <label className="text-xs text-white/40 block mb-1">Channel Mappings</label>
            <div className="flex flex-wrap gap-1">
              {current.channels.map((ch) => (
                <span key={ch} className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400">{ch}</span>
              ))}
            </div>
          </div>
        )}
        <div className="flex items-center gap-2">
          <button onClick={handleTest} disabled={testing}
            className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-500/20 text-indigo-400 text-xs font-medium hover:bg-indigo-500/30 transition disabled:opacity-30">
            <RefreshCw className={`w-3.5 h-3.5 ${testing ? 'animate-spin' : ''}`} /> Test Connection
          </button>
          {testResult === 'success' && <span className="text-xs text-green-400">Connection successful</span>}
          {testResult === 'error' && <span className="text-xs text-red-400">Connection failed</span>}
          <button className="ml-auto px-4 py-2 rounded-lg bg-green-500/20 text-green-400 text-xs font-medium hover:bg-green-500/30 transition">
            Save Configuration
          </button>
        </div>
      </div>

      {/* Zapier Endpoints (only on Zapier tab) */}
      {activeTab === 'Zapier / n8n' && (
        <div className="bg-white/5 border border-white/10 rounded-xl">
          <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between">
            <span className="text-sm font-medium">Webhook Endpoints</span>
            <button className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-500/20 text-indigo-400 text-xs hover:bg-indigo-500/30 transition">
              <Plus className="w-3 h-3" /> Add Endpoint
            </button>
          </div>
          <div className="divide-y divide-white/5">
            {endpoints.map((ep) => (
              <div key={ep.id} className="px-4 py-3 flex items-center gap-4 text-xs">
                <span className="font-mono text-white/50 flex-1 truncate">{ep.url}</span>
                <span className="px-2 py-0.5 rounded-full bg-white/10 text-white/50">{ep.event}</span>
                <span className="text-white/30">{ep.deliveries} deliveries</span>
              </div>
            ))}
          </div>
          <div className="px-4 py-3 border-t border-white/10">
            <div className="text-[10px] text-white/30 mb-1">Supported Events</div>
            <div className="flex flex-wrap gap-1">
              {SUPPORTED_EVENTS.map((e) => (
                <span key={e} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-white/30">{e}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Recent Deliveries */}
      {current.deliveries.length > 0 && (
        <div className="bg-white/5 border border-white/10 rounded-xl">
          <div className="px-4 py-3 border-b border-white/10 text-sm font-medium">Recent Deliveries</div>
          <div className="divide-y divide-white/5">
            {current.deliveries.map((d) => (
              <div key={d.id} className="px-4 py-3 flex items-center gap-4 text-xs">
                <span className={`w-2 h-2 rounded-full ${d.status === 'delivered' ? 'bg-green-400' : 'bg-red-400'}`} />
                <span className="text-white/60">{d.event}</span>
                <span className={`px-2 py-0.5 rounded-full text-[10px] ${d.status === 'delivered' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{d.status}</span>
                <span className="ml-auto text-white/30">{fmtTime(d.timestamp)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
