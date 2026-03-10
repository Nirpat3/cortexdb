'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  BookOpen, ChevronDown, ChevronRight, Shield, AlertTriangle, Filter,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';

interface AttackVector {
  id: string;
  attack_id: string;
  name: string;
  category: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  description?: string;
  framework_ref?: string;
  payloads: string[];
  indicators: string[];
  created_at: string;
}

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400 border-red-500/30',
  high: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  medium: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
  low: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
  info: 'bg-white/10 text-white/50 border-white/20',
};

const ALL_CATEGORIES = [
  'sql_injection', 'xss', 'authentication', 'authorization', 'injection',
  'ssrf', 'path_traversal', 'csrf', 'rate_limiting', 'information_disclosure',
  'business_logic', 'api_abuse',
];

const PLACEHOLDER_VECTORS: AttackVector[] = [
  { id: 'v1', attack_id: 'SQLi-UNION-001', name: 'UNION-Based SQL Injection', category: 'sql_injection', severity: 'critical', description: 'Attempts UNION SELECT injection to extract data from other tables', framework_ref: 'CWE-89 / OWASP A03:2021', payloads: ["' UNION SELECT null,null,null --", "' UNION SELECT username,password,null FROM users --", "1 UNION ALL SELECT table_name,null,null FROM information_schema.tables --"], indicators: ['SQL error messages in response', 'Unexpected data columns in output', 'Response time anomaly on UNION payload'], created_at: '2026-01-15T10:00:00Z' },
  { id: 'v2', attack_id: 'SQLi-BLIND-002', name: 'Time-Based Blind SQL Injection', category: 'sql_injection', severity: 'high', description: 'Uses time delays to infer database responses without direct output', framework_ref: 'CWE-89 / OWASP A03:2021', payloads: ["' AND SLEEP(5) --", "' OR IF(1=1, SLEEP(5), 0) --", "'; WAITFOR DELAY '0:0:5' --"], indicators: ['Response time > 5s on payload', 'Consistent delay pattern', 'No error messages but delayed response'], created_at: '2026-01-15T10:00:00Z' },
  { id: 'v3', attack_id: 'XSS-REFLECTED-003', name: 'Reflected XSS via Query Params', category: 'xss', severity: 'high', description: 'Injects script tags via query parameters reflected in HTML response', framework_ref: 'CWE-79 / OWASP A07:2021', payloads: ['<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '"><svg onload=alert(1)>'], indicators: ['Unescaped HTML in response', 'Content-Type: text/html', 'No CSP headers'], created_at: '2026-01-20T10:00:00Z' },
  { id: 'v4', attack_id: 'AUTH-BYPASS-002', name: 'NoSQL Injection Auth Bypass', category: 'authentication', severity: 'high', description: 'Uses NoSQL operator injection to bypass authentication checks', framework_ref: 'CWE-943 / OWASP A07:2021', payloads: ['{"username":"admin","password":{"$gt":""}}', '{"username":{"$regex":"^admin"},"password":{"$ne":""}}'], indicators: ['Successful auth with operator payload', 'Token returned without valid credentials'], created_at: '2026-01-25T10:00:00Z' },
  { id: 'v5', attack_id: 'SSRF-INTERNAL-001', name: 'Internal Network SSRF', category: 'ssrf', severity: 'critical', description: 'Exploits URL-accepting endpoints to reach internal services and metadata endpoints', framework_ref: 'CWE-918 / OWASP A10:2021', payloads: ['http://169.254.169.254/latest/meta-data/', 'http://localhost:5432/', 'http://internal-service:8080/admin'], indicators: ['Internal IP content in response', 'Cloud metadata returned', 'Access to non-public services'], created_at: '2026-02-01T10:00:00Z' },
  { id: 'v6', attack_id: 'IDOR-USER-001', name: 'IDOR User Data Access', category: 'authorization', severity: 'medium', description: 'Direct object reference to access other users data without proper authorization', framework_ref: 'CWE-639 / OWASP A01:2021', payloads: ['GET /v1/users/{other-user-id}', 'GET /v1/users/{other-user-id}/settings', 'PUT /v1/users/{other-user-id}'], indicators: ['200 response with other user data', 'No ownership check', 'Sequential/predictable IDs'], created_at: '2026-02-05T10:00:00Z' },
  { id: 'v7', attack_id: 'RATE-BURST-001', name: 'Rate Limit Bypass - Burst', category: 'rate_limiting', severity: 'medium', description: 'Tests for missing or misconfigured rate limiting on sensitive endpoints', framework_ref: 'CWE-770 / OWASP A04:2021', payloads: ['1000 parallel requests to /auth/token', '100 requests/second to /login', 'Rotating headers to bypass per-IP limits'], indicators: ['All requests succeed (200)', 'No 429 responses', 'No X-RateLimit headers'], created_at: '2026-02-10T10:00:00Z' },
  { id: 'v8', attack_id: 'PATH-TRAV-002', name: 'Path Traversal File Read', category: 'path_traversal', severity: 'high', description: 'Attempts directory traversal to read sensitive files outside allowed paths', framework_ref: 'CWE-22 / OWASP A01:2021', payloads: ['../../../etc/passwd', '..\\..\\..\\windows\\system32\\config\\sam', '%2e%2e%2f%2e%2e%2fetc%2fpasswd'], indicators: ['File contents in response', 'System file data returned', '200 with unexpected content-length'], created_at: '2026-02-15T10:00:00Z' },
];

export default function KnowledgePage() {
  const [vectors, setVectors] = useState<AttackVector[]>(PLACEHOLDER_VECTORS);
  const [filterCategory, setFilterCategory] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await superadminApi.sentinelKnowledge(filterCategory || undefined);
      const v = (res as Record<string, unknown>).vectors as AttackVector[] | undefined;
      if (v && v.length > 0) setVectors(v);
    } catch { /* use placeholders */ }
    setLoading(false);
  }, [filterCategory]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const fmtCategory = (c: string) => c.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  const filtered = filterCategory ? vectors.filter(v => v.category === filterCategory) : vectors;

  const categoryCounts = vectors.reduce<Record<string, number>>((acc, v) => {
    acc[v.category] = (acc[v.category] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
          <BookOpen className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Attack Knowledge Base</h1>
          <p className="text-xs text-white/40">{vectors.length} attack vectors across {Object.keys(categoryCounts).length} categories</p>
        </div>
      </div>

      {/* Category Filter Tabs */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-4 h-4 text-white/30" />
        <button onClick={() => setFilterCategory('')}
          className={`px-2.5 py-1 rounded-lg text-xs transition ${!filterCategory ? 'bg-purple-500/20 text-purple-400' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}>
          All ({vectors.length})
        </button>
        {ALL_CATEGORIES.filter(c => categoryCounts[c]).map(cat => (
          <button key={cat} onClick={() => setFilterCategory(cat)}
            className={`px-2.5 py-1 rounded-lg text-xs transition ${filterCategory === cat ? 'bg-purple-500/20 text-purple-400' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}>
            {fmtCategory(cat)} ({categoryCounts[cat] || 0})
          </button>
        ))}
      </div>

      {/* Vector Cards */}
      <div className="space-y-3">
        {filtered.map(v => (
          <div key={v.id} className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
            {/* Card Header */}
            <div
              className="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-white/[0.02] transition"
              onClick={() => setExpandedId(expandedId === v.id ? null : v.id)}
            >
              <div className="text-white/20">
                {expandedId === v.id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </div>
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${SEV_COLORS[v.severity]}`}>{v.severity}</span>
              <span className="px-1.5 py-0.5 rounded bg-white/5 text-[10px] font-mono text-white/50">{v.attack_id}</span>
              <span className="text-sm font-medium text-white/80 flex-1">{v.name}</span>
              <span className="px-2 py-0.5 rounded bg-white/5 text-[10px] text-white/40">{fmtCategory(v.category)}</span>
              {v.framework_ref && <span className="text-[10px] text-white/25">{v.framework_ref}</span>}
              <span className="text-[10px] text-white/20">{v.payloads.length} payloads</span>
            </div>

            {/* Expanded Content */}
            {expandedId === v.id && (
              <div className="border-t border-white/5 px-4 py-3 space-y-3">
                {v.description && (
                  <p className="text-xs text-white/50">{v.description}</p>
                )}

                {/* Payloads */}
                <div>
                  <div className="text-[10px] text-white/30 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <AlertTriangle className="w-3 h-3" /> Payloads
                  </div>
                  <div className="space-y-1">
                    {v.payloads.map((p, i) => (
                      <pre key={i} className="bg-black/30 rounded-lg px-3 py-1.5 text-[10px] text-red-300 font-mono overflow-x-auto">{p}</pre>
                    ))}
                  </div>
                </div>

                {/* Indicators */}
                {v.indicators.length > 0 && (
                  <div>
                    <div className="text-[10px] text-white/30 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                      <Shield className="w-3 h-3" /> Detection Indicators
                    </div>
                    <ul className="space-y-0.5">
                      {v.indicators.map((ind, i) => (
                        <li key={i} className="text-xs text-white/40 flex items-center gap-1.5">
                          <span className="w-1 h-1 rounded-full bg-amber-400 shrink-0" />
                          {ind}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {filtered.length === 0 && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-8 text-center text-xs text-white/30">
            No attack vectors found for this category
          </div>
        )}
      </div>
    </div>
  );
}
