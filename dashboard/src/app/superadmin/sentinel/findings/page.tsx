'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Bug, ChevronDown, ChevronRight, CheckCircle, XCircle, Filter, Wrench, Loader2,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';

interface Finding {
  id: string;
  attack_id: string;
  category: string;
  endpoint: string;
  method: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  vulnerable: boolean;
  status: string;
  found_at: string;
  response_status?: number;
  evidence?: { payload?: string; response_snippet?: string };
}

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400',
  high: 'bg-orange-500/20 text-orange-400',
  medium: 'bg-amber-500/20 text-amber-400',
  low: 'bg-blue-500/20 text-blue-400',
  info: 'bg-white/10 text-white/50',
};

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-red-500/20 text-red-400',
  acknowledged: 'bg-amber-500/20 text-amber-400',
  remediated: 'bg-green-500/20 text-green-400',
  false_positive: 'bg-white/10 text-white/40',
  accepted_risk: 'bg-purple-500/20 text-purple-400',
};

const ALL_CATEGORIES = [
  'sql_injection', 'xss', 'authentication', 'authorization', 'injection',
  'ssrf', 'path_traversal', 'csrf', 'rate_limiting', 'information_disclosure',
  'business_logic', 'api_abuse',
];

const ALL_SEVERITIES = ['critical', 'high', 'medium', 'low', 'info'];
const ALL_STATUSES = ['open', 'acknowledged', 'remediated', 'false_positive', 'accepted_risk'];

const PLACEHOLDER_FINDINGS: Finding[] = [
  { id: 'f1', attack_id: 'SQLi-UNION-001', category: 'sql_injection', endpoint: '/v1/query', method: 'POST', severity: 'critical', vulnerable: true, status: 'open', found_at: '2026-03-08T09:12:00Z', response_status: 500, evidence: { payload: "' UNION SELECT * FROM users --", response_snippet: 'ERROR: column "password_hash" does not exist...' } },
  { id: 'f2', attack_id: 'XSS-REFLECTED-003', category: 'xss', endpoint: '/v1/search', method: 'GET', severity: 'high', vulnerable: true, status: 'open', found_at: '2026-03-08T09:11:00Z', response_status: 200, evidence: { payload: '<script>alert(1)</script>', response_snippet: 'Results for: <script>alert(1)</script>' } },
  { id: 'f3', attack_id: 'AUTH-BYPASS-002', category: 'authentication', endpoint: '/v1/admin/login', method: 'POST', severity: 'high', vulnerable: true, status: 'acknowledged', found_at: '2026-03-08T09:10:00Z', response_status: 200, evidence: { payload: '{"username":"admin","password":{"$gt":""}}', response_snippet: '{"token":"eyJ...","role":"admin"}' } },
  { id: 'f4', attack_id: 'SSRF-INTERNAL-001', category: 'ssrf', endpoint: '/v1/webhook', method: 'POST', severity: 'critical', vulnerable: true, status: 'open', found_at: '2026-03-08T09:09:00Z', response_status: 200, evidence: { payload: '{"url":"http://169.254.169.254/latest/meta-data/"}', response_snippet: 'ami-id\nami-launch-index...' } },
  { id: 'f5', attack_id: 'IDOR-USER-001', category: 'authorization', endpoint: '/v1/users/{id}', method: 'GET', severity: 'medium', vulnerable: true, status: 'open', found_at: '2026-03-08T09:08:00Z', response_status: 200, evidence: { payload: 'GET /v1/users/other-user-uuid', response_snippet: '{"id":"other-user-uuid","email":"admin@..."} ' } },
  { id: 'f6', attack_id: 'CSRF-STATE-001', category: 'csrf', endpoint: '/v1/settings', method: 'PUT', severity: 'medium', vulnerable: false, status: 'remediated', found_at: '2026-03-07T15:20:00Z', response_status: 403 },
  { id: 'f7', attack_id: 'RATE-BURST-001', category: 'rate_limiting', endpoint: '/v1/auth/token', method: 'POST', severity: 'medium', vulnerable: true, status: 'open', found_at: '2026-03-08T09:07:00Z', response_status: 200, evidence: { payload: '1000 requests in 10s', response_snippet: 'All returned 200 OK — no rate limit detected' } },
  { id: 'f8', attack_id: 'PATH-TRAV-002', category: 'path_traversal', endpoint: '/v1/files', method: 'GET', severity: 'high', vulnerable: false, status: 'false_positive', found_at: '2026-03-07T14:30:00Z', response_status: 400 },
  { id: 'f9', attack_id: 'INFO-HEADER-001', category: 'information_disclosure', endpoint: '/v1/health', method: 'GET', severity: 'low', vulnerable: true, status: 'accepted_risk', found_at: '2026-03-07T12:00:00Z', response_status: 200, evidence: { payload: 'HEAD /v1/health', response_snippet: 'X-Powered-By: FastAPI\nServer: uvicorn' } },
  { id: 'f10', attack_id: 'BIZ-LOGIC-001', category: 'business_logic', endpoint: '/v1/transfer', method: 'POST', severity: 'critical', vulnerable: true, status: 'open', found_at: '2026-03-08T09:05:00Z', response_status: 200, evidence: { payload: '{"amount": -500, "to": "attacker"}', response_snippet: '{"status":"success","new_balance":1500}' } },
  { id: 'f11', attack_id: 'SQLi-BLIND-002', category: 'sql_injection', endpoint: '/v1/users', method: 'GET', severity: 'high', vulnerable: true, status: 'open', found_at: '2026-03-08T08:55:00Z', response_status: 200, evidence: { payload: "?name=admin' AND SLEEP(5)--", response_snippet: 'Response delayed 5.02s' } },
  { id: 'f12', attack_id: 'API-ENUM-001', category: 'api_abuse', endpoint: '/v1/users/exists', method: 'GET', severity: 'low', vulnerable: true, status: 'open', found_at: '2026-03-08T08:50:00Z', response_status: 200, evidence: { payload: '?email=test@example.com', response_snippet: '{"exists": true}' } },
];

export default function FindingsPage() {
  const [findings, setFindings] = useState<Finding[]>(PLACEHOLDER_FINDINGS);
  const [filterCategory, setFilterCategory] = useState('');
  const [filterSeverity, setFilterSeverity] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [vulnerableOnly, setVulnerableOnly] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [generatingId, setGeneratingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (filterCategory) params.category = filterCategory;
      if (filterSeverity) params.severity = filterSeverity;
      if (filterStatus) params.status = filterStatus;
      if (vulnerableOnly) params.vulnerable_only = 'true';
      const res = await superadminApi.sentinelFindings(Object.keys(params).length > 0 ? params : undefined);
      const f = (res as Record<string, unknown>).findings as Finding[] | undefined;
      if (f && f.length > 0) setFindings(f);
    } catch { /* use placeholders */ }
    setLoading(false);
  }, [filterCategory, filterSeverity, filterStatus, vulnerableOnly]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleStatusChange = async (id: string, newStatus: string) => {
    try {
      await superadminApi.sentinelUpdateFinding(id, { status: newStatus });
      setFindings(prev => prev.map(f => f.id === id ? { ...f, status: newStatus } : f));
    } catch { /* ignore */ }
  };

  const handleGenerateRemediation = async (findingId: string) => {
    setGeneratingId(findingId);
    try {
      await superadminApi.sentinelGenerateRemediation(findingId);
    } catch { /* ignore */ }
    setGeneratingId(null);
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };
  const fmtCategory = (c: string) => c.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  const filtered = findings.filter(f => {
    if (filterCategory && f.category !== filterCategory) return false;
    if (filterSeverity && f.severity !== filterSeverity) return false;
    if (filterStatus && f.status !== filterStatus) return false;
    if (vulnerableOnly && !f.vulnerable) return false;
    return true;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-orange-500/20 flex items-center justify-center">
          <Bug className="w-5 h-5 text-orange-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Security Findings</h1>
          <p className="text-xs text-white/40">All vulnerabilities and test results from Sentinel scans</p>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex items-center gap-3 flex-wrap">
        <Filter className="w-4 h-4 text-white/30" />
        <select value={filterCategory} onChange={e => setFilterCategory(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs focus:outline-none">
          <option value="">All Categories</option>
          {ALL_CATEGORIES.map(c => <option key={c} value={c}>{fmtCategory(c)}</option>)}
        </select>
        <select value={filterSeverity} onChange={e => setFilterSeverity(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs focus:outline-none">
          <option value="">All Severities</option>
          {ALL_SEVERITIES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)}
          className="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs focus:outline-none">
          <option value="">All Statuses</option>
          {ALL_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-white/50 cursor-pointer">
          <input type="checkbox" checked={vulnerableOnly} onChange={e => setVulnerableOnly(e.target.checked)}
            className="rounded bg-white/5 border-white/10" />
          Vulnerable only
        </label>
        <span className="ml-auto text-xs text-white/30">{filtered.length} findings</span>
      </div>

      {/* Findings Table */}
      <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 text-white/40">
              <th className="w-8 px-2"></th>
              <th className="text-left px-3 py-2 font-medium">Severity</th>
              <th className="text-left px-3 py-2 font-medium">Attack ID</th>
              <th className="text-left px-3 py-2 font-medium">Category</th>
              <th className="text-left px-3 py-2 font-medium">Endpoint</th>
              <th className="text-left px-3 py-2 font-medium">Response</th>
              <th className="text-left px-3 py-2 font-medium">Vuln?</th>
              <th className="text-left px-3 py-2 font-medium">Status</th>
              <th className="text-left px-3 py-2 font-medium">Found</th>
              <th className="w-10"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {filtered.map(f => (
              <>
                <tr key={f.id} className="hover:bg-white/5 transition cursor-pointer" onClick={() => setExpandedId(expandedId === f.id ? null : f.id)}>
                  <td className="px-2 text-white/20">
                    {expandedId === f.id ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] ${SEV_COLORS[f.severity]}`}>{f.severity}</span>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-white/60 text-[10px]">{f.attack_id}</td>
                  <td className="px-3 py-2.5 text-white/50">{fmtCategory(f.category)}</td>
                  <td className="px-3 py-2.5 font-mono text-[10px]">
                    <span className="text-white/30">{f.method}</span> <span className="text-white/50">{f.endpoint}</span>
                  </td>
                  <td className="px-3 py-2.5 text-white/40">{f.response_status || '-'}</td>
                  <td className="px-3 py-2.5">
                    {f.vulnerable ? <CheckCircle className="w-3.5 h-3.5 text-red-400" /> : <XCircle className="w-3.5 h-3.5 text-green-400" />}
                  </td>
                  <td className="px-3 py-2.5">
                    <select
                      value={f.status}
                      onChange={e => { e.stopPropagation(); handleStatusChange(f.id, e.target.value); }}
                      onClick={e => e.stopPropagation()}
                      className={`px-1.5 py-0.5 rounded text-[10px] bg-transparent border border-white/10 focus:outline-none ${STATUS_COLORS[f.status] || ''}`}
                    >
                      {ALL_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                    </select>
                  </td>
                  <td className="px-3 py-2.5 text-white/30 text-[10px]">{fmtTime(f.found_at)}</td>
                  <td className="px-2">
                    <button
                      onClick={e => { e.stopPropagation(); handleGenerateRemediation(f.id); }}
                      disabled={generatingId === f.id}
                      className="p-1 rounded hover:bg-white/10 text-white/30 hover:text-white/60 transition"
                      title="Generate Remediation"
                    >
                      {generatingId === f.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Wrench className="w-3.5 h-3.5" />}
                    </button>
                  </td>
                </tr>
                {expandedId === f.id && f.evidence && (
                  <tr key={`${f.id}-evidence`} className="bg-white/[0.02]">
                    <td colSpan={10} className="px-6 py-3">
                      <div className="grid grid-cols-2 gap-4">
                        {f.evidence.payload && (
                          <div>
                            <div className="text-[10px] text-white/30 mb-1 uppercase tracking-wider">Payload</div>
                            <pre className="bg-black/30 rounded-lg p-2 text-[10px] text-red-300 font-mono overflow-x-auto whitespace-pre-wrap">{f.evidence.payload}</pre>
                          </div>
                        )}
                        {f.evidence.response_snippet && (
                          <div>
                            <div className="text-[10px] text-white/30 mb-1 uppercase tracking-wider">Response Snippet</div>
                            <pre className="bg-black/30 rounded-lg p-2 text-[10px] text-amber-300 font-mono overflow-x-auto whitespace-pre-wrap">{f.evidence.response_snippet}</pre>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="px-4 py-8 text-center text-xs text-white/30">No findings match the current filters</div>
        )}
      </div>
    </div>
  );
}
