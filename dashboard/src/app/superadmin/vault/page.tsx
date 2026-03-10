'use client';

import { useState, useEffect, useCallback } from 'react';
import { KeyRound, Lock, Unlock, Plus, RotateCw, Trash2, Eye, EyeOff, Clock, Shield } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Secret {
  id: string; path: string; type: string; version: number;
  last_rotated: string; lease_status: 'active' | 'expired' | 'none';
  lease_expires?: string; metadata: Record<string, string>;
  rotation_policy: string; access_log: { actor: string; action: string; timestamp: string }[];
}

interface Rotation { id: string; path: string; next_rotation: string; interval: string; status: string }

const PLACEHOLDER_SECRETS: Secret[] = [
  { id: '1', path: 'cortexdb/api/gateway-key', type: 'api_key', version: 3, last_rotated: '2026-03-05T08:00:00Z', lease_status: 'active', lease_expires: '2026-04-05T08:00:00Z', metadata: { env: 'production', service: 'gateway' }, rotation_policy: 'Every 30 days', access_log: [{ actor: 'admin', action: 'read', timestamp: '2026-03-08T09:00:00Z' }, { actor: 'gateway-service', action: 'read', timestamp: '2026-03-08T08:30:00Z' }] },
  { id: '2', path: 'cortexdb/db/connection-string', type: 'connection', version: 5, last_rotated: '2026-03-01T12:00:00Z', lease_status: 'active', lease_expires: '2026-03-15T12:00:00Z', metadata: { env: 'production', engine: 'cortexdb' }, rotation_policy: 'Every 14 days', access_log: [{ actor: 'agent-service', action: 'read', timestamp: '2026-03-08T10:00:00Z' }] },
  { id: '3', path: 'cortexdb/llm/anthropic-key', type: 'api_key', version: 2, last_rotated: '2026-02-20T10:00:00Z', lease_status: 'active', metadata: { provider: 'anthropic', model: 'claude' }, rotation_policy: 'Every 60 days', access_log: [{ actor: 'llm-router', action: 'read', timestamp: '2026-03-08T10:15:00Z' }] },
  { id: '4', path: 'cortexdb/tls/agent-cert', type: 'certificate', version: 1, last_rotated: '2026-01-15T00:00:00Z', lease_status: 'expired', metadata: { cn: '*.cortexdb.internal' }, rotation_policy: 'Every 90 days', access_log: [] },
  { id: '5', path: 'cortexdb/oauth/github-secret', type: 'oauth', version: 4, last_rotated: '2026-03-07T14:00:00Z', lease_status: 'none', metadata: { provider: 'github', scope: 'repo,read:org' }, rotation_policy: 'Manual', access_log: [{ actor: 'admin', action: 'rotate', timestamp: '2026-03-07T14:00:00Z' }] },
];

const PLACEHOLDER_ROTATIONS: Rotation[] = [
  { id: '1', path: 'cortexdb/db/connection-string', next_rotation: '2026-03-15T12:00:00Z', interval: '14d', status: 'scheduled' },
  { id: '2', path: 'cortexdb/llm/anthropic-key', next_rotation: '2026-04-21T10:00:00Z', interval: '60d', status: 'scheduled' },
  { id: '3', path: 'cortexdb/tls/agent-cert', next_rotation: '2026-04-15T00:00:00Z', interval: '90d', status: 'overdue' },
];

const TYPE_COLORS: Record<string, string> = {
  api_key: 'bg-blue-500/20 text-blue-400',
  connection: 'bg-green-500/20 text-green-400',
  certificate: 'bg-purple-500/20 text-purple-400',
  oauth: 'bg-amber-500/20 text-amber-400',
};

const LEASE_COLORS: Record<string, string> = {
  active: 'bg-green-500/20 text-green-400',
  expired: 'bg-red-500/20 text-red-400',
  none: 'bg-white/10 text-white/40',
};

export default function VaultPage() {
  const { t } = useTranslation();
  const [secrets, setSecrets] = useState<Secret[]>(PLACEHOLDER_SECRETS);
  const [rotations, setRotations] = useState<Rotation[]>(PLACEHOLDER_ROTATIONS);
  const [sealed, setSealed] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newPath, setNewPath] = useState('');
  const [newValue, setNewValue] = useState('');
  const [newLease, setNewLease] = useState('30d');

  const upcomingRotations = rotations.filter((r) => r.status === 'overdue').length;
  const activeLeases = secrets.filter((s) => s.lease_status === 'active').length;
  const accessEvents = secrets.reduce((s, sec) => s + sec.access_log.length, 0);

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };
  const fmtDate = (ts: string) => { try { return new Date(ts).toLocaleDateString(); } catch { return ts; } };

  const handleCreate = () => {
    if (!newPath.trim()) return;
    const secret: Secret = {
      id: Date.now().toString(), path: newPath, type: 'api_key', version: 1,
      last_rotated: new Date().toISOString(), lease_status: 'active',
      lease_expires: new Date(Date.now() + 30 * 86400000).toISOString(),
      metadata: {}, rotation_policy: newLease, access_log: [],
    };
    setSecrets((prev) => [secret, ...prev]);
    setNewPath(''); setNewValue(''); setShowCreate(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
          <KeyRound className="w-5 h-5 text-amber-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Secrets Vault</h1>
          <p className="text-xs text-white/40">Manage secrets, keys, and certificates</p>
        </div>
      </div>

      {/* Vault Status */}
      <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${sealed ? 'bg-red-500/10 border-red-500/30' : 'bg-green-500/10 border-green-500/30'}`}>
        {sealed ? <Lock className="w-5 h-5 text-red-400" /> : <Unlock className="w-5 h-5 text-green-400" />}
        <span className={`text-sm font-medium ${sealed ? 'text-red-400' : 'text-green-400'}`}>
          Vault {sealed ? 'Sealed' : 'Unsealed'}
        </span>
        <span className="text-xs text-white/30 ml-2">{secrets.length} secrets stored</span>
        {upcomingRotations > 0 && (
          <span className="text-xs text-amber-400 ml-auto">{upcomingRotations} rotation(s) overdue</span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Secrets', value: secrets.length, color: 'text-amber-400' },
          { label: 'Active Leases', value: activeLeases, color: 'text-green-400' },
          { label: 'Scheduled Rotations', value: rotations.length, color: 'text-blue-400' },
          { label: 'Access Events (24h)', value: accessEvents, color: 'text-purple-400' },
        ].map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-400 text-xs font-medium hover:bg-amber-500/30 transition">
          <Plus className="w-3.5 h-3.5" /> Create Secret
        </button>
      </div>

      {showCreate && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
          <div className="text-sm font-medium">Create New Secret</div>
          <input value={newPath} onChange={(e) => setNewPath(e.target.value)} placeholder="Secret path (e.g., cortexdb/api/new-key)"
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none" />
          <input value={newValue} onChange={(e) => setNewValue(e.target.value)} placeholder="Secret value" type="password"
            className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none" />
          <div className="flex items-center gap-3">
            <select value={newLease} onChange={(e) => setNewLease(e.target.value)}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none">
              <option value="7d">7 day lease</option>
              <option value="30d">30 day lease</option>
              <option value="90d">90 day lease</option>
              <option value="none">No lease</option>
            </select>
            <button onClick={handleCreate} className="px-4 py-2 rounded-lg bg-green-500/20 text-green-400 text-xs font-medium hover:bg-green-500/30 transition">Create</button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-white/5 text-white/40 text-xs hover:bg-white/10 transition">Cancel</button>
          </div>
        </div>
      )}

      {/* Secrets List */}
      <div className="space-y-2">
        {secrets.map((secret) => (
          <div key={secret.id} className="bg-white/5 border border-white/10 rounded-xl">
            <button onClick={() => setExpanded(expanded === secret.id ? null : secret.id)}
              className="w-full p-4 flex items-center gap-4 text-left text-xs">
              <Shield className="w-4 h-4 text-white/20 shrink-0" />
              <span className="font-mono text-white/70 flex-1">{secret.path}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] ${TYPE_COLORS[secret.type] ?? 'bg-white/10 text-white/40'}`}>{secret.type}</span>
              <span className="text-white/30">v{secret.version}</span>
              <span className="text-white/30">{fmtDate(secret.last_rotated)}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] ${LEASE_COLORS[secret.lease_status]}`}>{secret.lease_status}</span>
            </button>
            {expanded === secret.id && (
              <div className="px-4 pb-4 pt-0 border-t border-white/5 space-y-3">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-[10px] text-white/30 mb-1">Metadata</div>
                    {Object.entries(secret.metadata).map(([k, v]) => (
                      <div key={k} className="text-[11px]"><span className="text-white/30">{k}:</span> <span className="text-white/60">{v}</span></div>
                    ))}
                  </div>
                  <div>
                    <div className="text-[10px] text-white/30 mb-1">Rotation Policy</div>
                    <div className="text-[11px] text-white/60">{secret.rotation_policy}</div>
                    {secret.lease_expires && <div className="text-[10px] text-white/30 mt-1">Lease expires: {fmtDate(secret.lease_expires)}</div>}
                  </div>
                </div>
                {secret.access_log.length > 0 && (
                  <div>
                    <div className="text-[10px] text-white/30 mb-1">Recent Access</div>
                    {secret.access_log.map((log, i) => (
                      <div key={i} className="text-[11px] text-white/40">{log.actor} &middot; {log.action} &middot; {fmtTime(log.timestamp)}</div>
                    ))}
                  </div>
                )}
                <div className="flex gap-2">
                  <button className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-500/20 text-blue-400 text-[10px] hover:bg-blue-500/30 transition">
                    <RotateCw className="w-3 h-3" /> Rotate
                  </button>
                  <button className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 text-[10px] hover:bg-red-500/30 transition">
                    <Trash2 className="w-3 h-3" /> Delete
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Rotation Schedule */}
      <div className="bg-white/5 border border-white/10 rounded-xl">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium flex items-center gap-2">
          <Clock className="w-4 h-4 text-white/30" /> Rotation Schedule
        </div>
        <div className="divide-y divide-white/5">
          {rotations.map((r) => (
            <div key={r.id} className="px-4 py-3 flex items-center gap-4 text-xs">
              <span className="font-mono text-white/50 flex-1">{r.path}</span>
              <span className="text-white/30">every {r.interval}</span>
              <span className="text-white/30">{fmtDate(r.next_rotation)}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] ${r.status === 'overdue' ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}`}>{r.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
