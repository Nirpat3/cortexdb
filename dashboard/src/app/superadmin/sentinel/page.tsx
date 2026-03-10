'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import {
  Target, Shield, AlertTriangle, Bug, Clock, ArrowUpRight, ArrowDownRight,
  Minus, Play, Loader2, CheckCircle, XCircle, ChevronRight,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';

interface CategoryScore {
  category: string;
  score: number;
  passed: number;
  failed: number;
  total: number;
}

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
}

interface Campaign {
  id: string;
  name: string;
  status: 'planned' | 'running' | 'completed' | 'failed';
  progress?: number;
  categories: string[];
  created_at: string;
}

interface PostureData {
  score: number;
  trend: number;
  category_scores: CategoryScore[];
  total_vectors: number;
  total_categories: number;
}

interface StatsData {
  open_findings: { total: number; critical: number; high: number; medium: number; low: number };
  last_scan: { timestamp: string; status: string } | null;
  active_campaigns: Campaign[];
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

const CAMPAIGN_COLORS: Record<string, string> = {
  planned: 'bg-blue-500/20 text-blue-400',
  running: 'bg-amber-500/20 text-amber-400',
  completed: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
};

const PLACEHOLDER_POSTURE: PostureData = {
  score: 72,
  trend: 3,
  category_scores: [
    { category: 'sql_injection', score: 85, passed: 42, failed: 8, total: 50 },
    { category: 'xss', score: 68, passed: 34, failed: 16, total: 50 },
    { category: 'authentication', score: 91, passed: 46, failed: 4, total: 50 },
    { category: 'authorization', score: 78, passed: 39, failed: 11, total: 50 },
    { category: 'injection', score: 82, passed: 41, failed: 9, total: 50 },
    { category: 'ssrf', score: 55, passed: 22, failed: 18, total: 40 },
    { category: 'path_traversal', score: 90, passed: 36, failed: 4, total: 40 },
    { category: 'csrf', score: 65, passed: 26, failed: 14, total: 40 },
    { category: 'rate_limiting', score: 45, passed: 18, failed: 22, total: 40 },
    { category: 'information_disclosure', score: 73, passed: 29, failed: 11, total: 40 },
    { category: 'business_logic', score: 60, passed: 24, failed: 16, total: 40 },
    { category: 'api_abuse', score: 52, passed: 21, failed: 19, total: 40 },
  ],
  total_vectors: 248,
  total_categories: 12,
};

const PLACEHOLDER_STATS: StatsData = {
  open_findings: { total: 37, critical: 3, high: 8, medium: 14, low: 12 },
  last_scan: { timestamp: '2026-03-08T09:15:00Z', status: 'completed' },
  active_campaigns: [
    { id: '1', name: 'API Security Sweep', status: 'running', progress: 64, categories: ['sql_injection', 'xss', 'authentication'], created_at: '2026-03-08T08:00:00Z' },
    { id: '2', name: 'Weekly Regression', status: 'planned', categories: ['injection', 'ssrf', 'path_traversal', 'csrf'], created_at: '2026-03-07T22:00:00Z' },
  ],
};

const PLACEHOLDER_FINDINGS: Finding[] = [
  { id: 'f1', attack_id: 'SQLi-UNION-001', category: 'sql_injection', endpoint: '/v1/query', method: 'POST', severity: 'critical', vulnerable: true, status: 'open', found_at: '2026-03-08T09:12:00Z' },
  { id: 'f2', attack_id: 'XSS-REFLECTED-003', category: 'xss', endpoint: '/v1/search', method: 'GET', severity: 'high', vulnerable: true, status: 'open', found_at: '2026-03-08T09:11:00Z' },
  { id: 'f3', attack_id: 'AUTH-BYPASS-002', category: 'authentication', endpoint: '/v1/admin/login', method: 'POST', severity: 'high', vulnerable: true, status: 'acknowledged', found_at: '2026-03-08T09:10:00Z' },
  { id: 'f4', attack_id: 'SSRF-INTERNAL-001', category: 'ssrf', endpoint: '/v1/webhook', method: 'POST', severity: 'critical', vulnerable: true, status: 'open', found_at: '2026-03-08T09:09:00Z' },
  { id: 'f5', attack_id: 'IDOR-USER-001', category: 'authorization', endpoint: '/v1/users/{id}', method: 'GET', severity: 'medium', vulnerable: true, status: 'open', found_at: '2026-03-08T09:08:00Z' },
  { id: 'f6', attack_id: 'CSRF-STATE-001', category: 'csrf', endpoint: '/v1/settings', method: 'PUT', severity: 'medium', vulnerable: false, status: 'remediated', found_at: '2026-03-07T15:20:00Z' },
  { id: 'f7', attack_id: 'RATE-BURST-001', category: 'rate_limiting', endpoint: '/v1/auth/token', method: 'POST', severity: 'medium', vulnerable: true, status: 'open', found_at: '2026-03-08T09:07:00Z' },
  { id: 'f8', attack_id: 'PATH-TRAV-002', category: 'path_traversal', endpoint: '/v1/files', method: 'GET', severity: 'high', vulnerable: false, status: 'false_positive', found_at: '2026-03-07T14:30:00Z' },
  { id: 'f9', attack_id: 'INFO-HEADER-001', category: 'information_disclosure', endpoint: '/v1/health', method: 'GET', severity: 'low', vulnerable: true, status: 'accepted_risk', found_at: '2026-03-07T12:00:00Z' },
  { id: 'f10', attack_id: 'BIZ-LOGIC-001', category: 'business_logic', endpoint: '/v1/transfer', method: 'POST', severity: 'critical', vulnerable: true, status: 'open', found_at: '2026-03-08T09:05:00Z' },
];

export default function SentinelPage() {
  const router = useRouter();
  const [posture, setPosture] = useState<PostureData>(PLACEHOLDER_POSTURE);
  const [stats, setStats] = useState<StatsData>(PLACEHOLDER_STATS);
  const [findings, setFindings] = useState<Finding[]>(PLACEHOLDER_FINDINGS);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [postureRes, statsRes, findingsRes] = await Promise.allSettled([
        superadminApi.sentinelPosture(),
        superadminApi.sentinelStats(),
        superadminApi.sentinelFindings(),
      ]);
      if (postureRes.status === 'fulfilled' && postureRes.value) setPosture(postureRes.value as unknown as PostureData);
      if (statsRes.status === 'fulfilled' && statsRes.value) setStats(statsRes.value as unknown as StatsData);
      if (findingsRes.status === 'fulfilled' && findingsRes.value) {
        const f = (findingsRes.value as Record<string, unknown>).findings as Finding[] | undefined;
        if (f && f.length > 0) setFindings(f.slice(0, 10));
      }
    } catch { /* use placeholders */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleQuickScan = async () => {
    setScanning(true);
    try {
      await superadminApi.sentinelQuickScan();
      await fetchData();
    } catch { /* ignore */ }
    setScanning(false);
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };

  const scoreColor = (s: number) => s > 80 ? 'text-green-400' : s > 50 ? 'text-amber-400' : 'text-red-400';
  const barColor = (s: number) => s > 80 ? 'bg-green-500' : s > 50 ? 'bg-amber-500' : 'bg-red-500';
  const trendIcon = (t: number) => t > 0 ? <ArrowUpRight className="w-4 h-4 text-green-400" /> : t < 0 ? <ArrowDownRight className="w-4 h-4 text-red-400" /> : <Minus className="w-4 h-4 text-white/30" />;

  const fmtCategory = (c: string) => c.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center">
          <Target className="w-5 h-5 text-red-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">CortexDB Sentinel</h1>
          <p className="text-xs text-white/40">Automated security testing &amp; posture management</p>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {/* Security Posture Score */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="text-xs text-white/40 mb-1">Security Posture Score</div>
          <div className="flex items-center gap-2">
            <span className={`text-3xl font-bold ${scoreColor(posture.score)}`}>{posture.score}</span>
            <span className="text-xs text-white/30">/100</span>
            {trendIcon(posture.trend)}
            <span className="text-[10px] text-white/30">{posture.trend > 0 ? '+' : ''}{posture.trend}%</span>
          </div>
        </div>

        {/* Open Findings */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="text-xs text-white/40 mb-1">Open Findings</div>
          <div className="text-3xl font-bold text-orange-400 mb-1">{stats.open_findings.total}</div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {stats.open_findings.critical > 0 && <span className="px-1.5 py-0.5 rounded text-[9px] bg-red-500/20 text-red-400">{stats.open_findings.critical} crit</span>}
            {stats.open_findings.high > 0 && <span className="px-1.5 py-0.5 rounded text-[9px] bg-orange-500/20 text-orange-400">{stats.open_findings.high} high</span>}
            {stats.open_findings.medium > 0 && <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-500/20 text-amber-400">{stats.open_findings.medium} med</span>}
            {stats.open_findings.low > 0 && <span className="px-1.5 py-0.5 rounded text-[9px] bg-blue-500/20 text-blue-400">{stats.open_findings.low} low</span>}
          </div>
        </div>

        {/* Attack Vectors */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="text-xs text-white/40 mb-1">Attack Vectors</div>
          <div className="text-3xl font-bold text-purple-400">{posture.total_vectors}</div>
          <div className="text-[10px] text-white/30">{posture.total_categories} categories</div>
        </div>

        {/* Last Scan */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="text-xs text-white/40 mb-1">Last Scan</div>
          {stats.last_scan ? (
            <>
              <div className="text-sm font-medium text-white/70 mb-1">{fmtTime(stats.last_scan.timestamp)}</div>
              <span className={`px-2 py-0.5 rounded-full text-[10px] ${stats.last_scan.status === 'completed' ? 'bg-green-500/20 text-green-400' : 'bg-amber-500/20 text-amber-400'}`}>
                {stats.last_scan.status}
              </span>
            </>
          ) : (
            <div className="text-sm text-white/30">No scans yet</div>
          )}
        </div>
      </div>

      {/* Middle Section: Two Columns */}
      <div className="grid grid-cols-2 gap-4">
        {/* Left: Category Security Scores */}
        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-white/10 text-sm font-medium flex items-center gap-2">
            <Shield className="w-4 h-4 text-white/30" /> Category Security Scores
          </div>
          <div className="p-4 space-y-3 max-h-[420px] overflow-y-auto">
            {posture.category_scores.map((cat) => (
              <div key={cat.category}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-white/60">{fmtCategory(cat.category)}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-green-400">{cat.passed} pass</span>
                    <span className="text-[10px] text-red-400">{cat.failed} fail</span>
                    <span className={`text-xs font-bold ${scoreColor(cat.score)}`}>{cat.score}</span>
                  </div>
                </div>
                <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all ${barColor(cat.score)}`} style={{ width: `${cat.score}%` }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Right: Recent Findings */}
        <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-white/10 text-sm font-medium flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bug className="w-4 h-4 text-white/30" /> Recent Findings
            </div>
            <button onClick={() => router.push('/superadmin/sentinel/findings')} className="text-[10px] text-white/30 hover:text-white/60 flex items-center gap-0.5">
              View all <ChevronRight className="w-3 h-3" />
            </button>
          </div>
          <div className="max-h-[420px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/10 text-white/40">
                  <th className="text-left px-3 py-2 font-medium">Severity</th>
                  <th className="text-left px-3 py-2 font-medium">Category</th>
                  <th className="text-left px-3 py-2 font-medium">Endpoint</th>
                  <th className="text-left px-3 py-2 font-medium">Status</th>
                  <th className="text-left px-3 py-2 font-medium">Found</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {findings.map((f) => (
                  <tr key={f.id} className="hover:bg-white/5 transition">
                    <td className="px-3 py-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${SEV_COLORS[f.severity]}`}>{f.severity}</span>
                    </td>
                    <td className="px-3 py-2 text-white/50">{fmtCategory(f.category)}</td>
                    <td className="px-3 py-2 font-mono text-white/50 text-[10px]">
                      <span className="text-white/30">{f.method}</span> {f.endpoint}
                    </td>
                    <td className="px-3 py-2">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${STATUS_COLORS[f.status] || 'bg-white/10 text-white/40'}`}>{f.status}</span>
                    </td>
                    <td className="px-3 py-2 text-white/30 text-[10px]">{fmtTime(f.found_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Bottom: Actions */}
      <div className="grid grid-cols-3 gap-4">
        {/* Quick Scan + Create Campaign */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 flex flex-col gap-3">
          <div className="text-sm font-medium">Actions</div>
          <button
            onClick={handleQuickScan}
            disabled={scanning}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-red-500/20 text-red-400 font-medium text-sm hover:bg-red-500/30 transition disabled:opacity-50"
          >
            {scanning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            {scanning ? 'Scanning...' : 'Run Quick Scan'}
          </button>
          <button
            onClick={() => router.push('/superadmin/sentinel/campaigns')}
            className="flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-white/5 text-white/60 font-medium text-sm hover:bg-white/10 transition border border-white/10"
          >
            <Target className="w-4 h-4" /> Create Campaign
          </button>
          <div className="flex gap-2 mt-1">
            <button onClick={() => router.push('/superadmin/sentinel/knowledge')} className="flex-1 text-center px-2 py-2 rounded-lg bg-white/5 text-white/40 text-xs hover:bg-white/10 transition">Knowledge Base</button>
            <button onClick={() => router.push('/superadmin/sentinel/remediation')} className="flex-1 text-center px-2 py-2 rounded-lg bg-white/5 text-white/40 text-xs hover:bg-white/10 transition">Remediation</button>
          </div>
        </div>

        {/* Active Campaigns */}
        <div className="col-span-2 bg-white/5 border border-white/10 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-white/10 text-sm font-medium flex items-center gap-2">
            <Clock className="w-4 h-4 text-white/30" /> Active Campaigns
          </div>
          <div className="divide-y divide-white/5">
            {stats.active_campaigns.length === 0 ? (
              <div className="px-4 py-6 text-center text-xs text-white/30">No active campaigns</div>
            ) : (
              stats.active_campaigns.map((c) => (
                <div key={c.id} className="px-4 py-3 flex items-center gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-sm font-medium text-white/80">{c.name}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${CAMPAIGN_COLORS[c.status]}`}>{c.status}</span>
                    </div>
                    <div className="text-[10px] text-white/30">{c.categories.map(fmtCategory).join(', ')}</div>
                  </div>
                  {c.status === 'running' && c.progress !== undefined && (
                    <div className="w-32">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[10px] text-white/40">Progress</span>
                        <span className="text-[10px] font-medium text-amber-400">{c.progress}%</span>
                      </div>
                      <div className="w-full h-1.5 bg-white/5 rounded-full overflow-hidden">
                        <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${c.progress}%` }} />
                      </div>
                    </div>
                  )}
                  <button onClick={() => router.push('/superadmin/sentinel/campaigns')} className="text-white/20 hover:text-white/50">
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
