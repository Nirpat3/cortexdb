'use client';

import { useState, useEffect, useCallback } from 'react';
import { ShieldCheck, Plus, CheckCircle, XCircle, FileText, AlertTriangle } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Policy {
  id: string; name: string; type: 'allow' | 'deny' | 'require_auth';
  source: string; destination: string; priority: number; enabled: boolean;
  description: string;
}

interface Certificate {
  id: string; subject: string; issuer: string; status: 'valid' | 'expired' | 'revoked';
  not_before: string; not_after: string; serial: string;
}

interface AuditEntry {
  id: string; timestamp: string; source: string; destination: string;
  policy: string; result: 'allow' | 'deny'; reason: string;
}

const TYPE_COLORS: Record<string, string> = {
  allow: 'bg-green-500/20 text-green-400',
  deny: 'bg-red-500/20 text-red-400',
  require_auth: 'bg-amber-500/20 text-amber-400',
};

const CERT_COLORS: Record<string, string> = {
  valid: 'bg-green-500/20 text-green-400',
  expired: 'bg-red-500/20 text-red-400',
  revoked: 'bg-white/10 text-white/40',
};

const PLACEHOLDER_POLICIES: Policy[] = [
  { id: '1', name: 'Agent-to-Agent Auth', type: 'require_auth', source: 'T*-*-*-*', destination: 'T*-*-*-*', priority: 100, enabled: true, description: 'Require mutual TLS for all inter-agent communication' },
  { id: '2', name: 'Allow Gateway Traffic', type: 'allow', source: 'gateway-service', destination: '*', priority: 90, enabled: true, description: 'Allow all traffic originating from the API gateway' },
  { id: '3', name: 'Block External to Internal', type: 'deny', source: 'EXT-*', destination: 'SYS-*', priority: 200, enabled: true, description: 'Prevent BYOA agents from accessing system-level agents' },
  { id: '4', name: 'Require Auth for Vault', type: 'require_auth', source: '*', destination: 'vault-service', priority: 150, enabled: true, description: 'All vault access must be authenticated and authorized' },
  { id: '5', name: 'Allow Health Checks', type: 'allow', source: '*', destination: '*/health', priority: 50, enabled: true, description: 'Allow unauthenticated health check endpoints' },
  { id: '6', name: 'Block Suspended Agents', type: 'deny', source: 'status:suspended', destination: '*', priority: 300, enabled: true, description: 'Deny all traffic from quarantined/suspended agents' },
];

const PLACEHOLDER_CERTS: Certificate[] = [
  { id: '1', subject: 'T1-OPS-LEAD-001', issuer: 'CortexDB Root CA', status: 'valid', not_before: '2026-01-01', not_after: '2027-01-01', serial: 'A1B2C3D4' },
  { id: '2', subject: 'gateway-service', issuer: 'CortexDB Root CA', status: 'valid', not_before: '2026-02-01', not_after: '2026-08-01', serial: 'E5F6G7H8' },
  { id: '3', subject: 'EXT-ENG-DEV-001', issuer: 'CortexDB Intermediate CA', status: 'expired', not_before: '2025-06-01', not_after: '2026-02-28', serial: 'I9J0K1L2' },
  { id: '4', subject: '*.cortexdb.internal', issuer: 'CortexDB Root CA', status: 'valid', not_before: '2026-01-15', not_after: '2026-07-15', serial: 'M3N4O5P6' },
];

const PLACEHOLDER_AUDIT: AuditEntry[] = [
  { id: '1', timestamp: '2026-03-08T10:32:15Z', source: 'T2-ENG-DEV-001', destination: 'T1-OPS-LEAD-001', policy: 'Agent-to-Agent Auth', result: 'allow', reason: 'mTLS verified' },
  { id: '2', timestamp: '2026-03-08T10:31:42Z', source: 'EXT-MKT-ANA-001', destination: 'SYS-SEC-CERT-001', policy: 'Block External to Internal', result: 'deny', reason: 'BYOA agent blocked from SYS namespace' },
  { id: '3', timestamp: '2026-03-08T10:30:58Z', source: 'gateway-service', destination: 'agent-service', policy: 'Allow Gateway Traffic', result: 'allow', reason: 'Gateway origin trusted' },
  { id: '4', timestamp: '2026-03-08T10:30:10Z', source: 'T1-ENG-LEAD-001', destination: 'vault-service', policy: 'Require Auth for Vault', result: 'allow', reason: 'Token valid, scope sufficient' },
  { id: '5', timestamp: '2026-03-08T10:29:30Z', source: 'unknown', destination: 'agent-service/api', policy: 'Agent-to-Agent Auth', result: 'deny', reason: 'No certificate presented' },
];

export default function ZeroTrustPage() {
  const { t } = useTranslation();
  const [policies, setPolicies] = useState<Policy[]>(PLACEHOLDER_POLICIES);
  const [certs, setCerts] = useState<Certificate[]>(PLACEHOLDER_CERTS);
  const [audit, setAudit] = useState<AuditEntry[]>(PLACEHOLDER_AUDIT);
  const [showCreate, setShowCreate] = useState(false);
  const [newPolicy, setNewPolicy] = useState({ name: '', type: 'allow' as Policy['type'], source: '', destination: '', priority: 100 });

  const activePolicies = policies.filter((p) => p.enabled).length;
  const validCerts = certs.filter((c) => c.status === 'valid').length;
  const evaluations = audit.length;

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };
  const fmtDate = (ts: string) => { try { return new Date(ts).toLocaleDateString(); } catch { return ts; } };

  const togglePolicy = (id: string) => {
    setPolicies((prev) => prev.map((p) => p.id === id ? { ...p, enabled: !p.enabled } : p));
  };

  const handleCreate = () => {
    if (!newPolicy.name.trim()) return;
    const policy: Policy = { ...newPolicy, id: Date.now().toString(), enabled: true, description: '' };
    setPolicies((prev) => [policy, ...prev]);
    setNewPolicy({ name: '', type: 'allow', source: '', destination: '', priority: 100 });
    setShowCreate(false);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
          <ShieldCheck className="w-5 h-5 text-emerald-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Zero-Trust Network Policies</h1>
          <p className="text-xs text-white/40">Manage network policies, certificates, and access control</p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Total Policies', value: policies.length, color: 'text-emerald-400' },
          { label: 'Active', value: activePolicies, color: 'text-green-400' },
          { label: 'Certificates Issued', value: certs.length, color: 'text-blue-400' },
          { label: 'Requests Evaluated (24h)', value: evaluations, color: 'text-purple-400' },
        ].map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* Create Policy */}
      <div className="flex items-center gap-2">
        <button onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 text-xs font-medium hover:bg-emerald-500/30 transition">
          <Plus className="w-3.5 h-3.5" /> Create Policy
        </button>
      </div>

      {showCreate && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-3">
          <div className="text-sm font-medium">New Policy</div>
          <div className="grid grid-cols-2 gap-3">
            <input value={newPolicy.name} onChange={(e) => setNewPolicy({ ...newPolicy, name: e.target.value })}
              placeholder="Policy name" className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none" />
            <select value={newPolicy.type} onChange={(e) => setNewPolicy({ ...newPolicy, type: e.target.value as Policy['type'] })}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none">
              <option value="allow">Allow</option>
              <option value="deny">Deny</option>
              <option value="require_auth">Require Auth</option>
            </select>
            <input value={newPolicy.source} onChange={(e) => setNewPolicy({ ...newPolicy, source: e.target.value })}
              placeholder="Source pattern (e.g., T*-*-*-*)" className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none" />
            <input value={newPolicy.destination} onChange={(e) => setNewPolicy({ ...newPolicy, destination: e.target.value })}
              placeholder="Destination pattern" className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none" />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-xs text-white/40">Priority:</label>
            <input type="number" value={newPolicy.priority} onChange={(e) => setNewPolicy({ ...newPolicy, priority: parseInt(e.target.value) || 0 })}
              className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs focus:outline-none" />
            <button onClick={handleCreate} className="ml-auto px-4 py-2 rounded-lg bg-green-500/20 text-green-400 text-xs font-medium hover:bg-green-500/30 transition">Create</button>
            <button onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg bg-white/5 text-white/40 text-xs hover:bg-white/10 transition">Cancel</button>
          </div>
        </div>
      )}

      {/* Policy Table */}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium">Network Policies</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 text-white/40">
              <th className="text-left px-4 py-2 font-medium">Name</th>
              <th className="text-left px-4 py-2 font-medium">Type</th>
              <th className="text-left px-4 py-2 font-medium">Source</th>
              <th className="text-left px-4 py-2 font-medium">Destination</th>
              <th className="text-left px-4 py-2 font-medium">Priority</th>
              <th className="text-left px-4 py-2 font-medium">Enabled</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {policies.map((p) => (
              <tr key={p.id} className="hover:bg-white/5 transition">
                <td className="px-4 py-3">
                  <div className="font-medium text-white/80">{p.name}</div>
                  {p.description && <div className="text-[10px] text-white/30 mt-0.5">{p.description}</div>}
                </td>
                <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-full text-[10px] ${TYPE_COLORS[p.type]}`}>{p.type}</span></td>
                <td className="px-4 py-3 font-mono text-white/50">{p.source}</td>
                <td className="px-4 py-3 font-mono text-white/50">{p.destination}</td>
                <td className="px-4 py-3 text-white/40">{p.priority}</td>
                <td className="px-4 py-3">
                  <button onClick={() => togglePolicy(p.id)}
                    className={`w-8 h-4 rounded-full transition relative ${p.enabled ? 'bg-green-500' : 'bg-white/20'}`}>
                    <span className={`absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all ${p.enabled ? 'left-4' : 'left-0.5'}`} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Certificates */}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium flex items-center gap-2">
          <FileText className="w-4 h-4 text-white/30" /> Certificates
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 text-white/40">
              <th className="text-left px-4 py-2 font-medium">Subject</th>
              <th className="text-left px-4 py-2 font-medium">Issuer</th>
              <th className="text-left px-4 py-2 font-medium">Status</th>
              <th className="text-left px-4 py-2 font-medium">Valid From</th>
              <th className="text-left px-4 py-2 font-medium">Expires</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {certs.map((c) => (
              <tr key={c.id} className="hover:bg-white/5 transition">
                <td className="px-4 py-3 font-mono text-white/70">{c.subject}</td>
                <td className="px-4 py-3 text-white/50">{c.issuer}</td>
                <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-full text-[10px] ${CERT_COLORS[c.status]}`}>{c.status}</span></td>
                <td className="px-4 py-3 text-white/40">{fmtDate(c.not_before)}</td>
                <td className="px-4 py-3 text-white/40">{fmtDate(c.not_after)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Audit Log */}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-white/10 text-sm font-medium">Policy Evaluation Audit Log</div>
        <div className="divide-y divide-white/5">
          {audit.map((entry) => (
            <div key={entry.id} className="px-4 py-3 flex items-center gap-4 text-xs">
              {entry.result === 'allow' ? (
                <CheckCircle className="w-4 h-4 text-green-400 shrink-0" />
              ) : (
                <XCircle className="w-4 h-4 text-red-400 shrink-0" />
              )}
              <span className="font-mono text-white/50">{entry.source}</span>
              <span className="text-white/20">-&gt;</span>
              <span className="font-mono text-white/50">{entry.destination}</span>
              <span className="text-white/30">{entry.policy}</span>
              <span className={`px-2 py-0.5 rounded-full text-[10px] ${entry.result === 'allow' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>{entry.result}</span>
              <span className="text-white/20 ml-auto">{fmtTime(entry.timestamp)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
