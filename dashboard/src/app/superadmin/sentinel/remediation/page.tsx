'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Wrench, CheckCircle, Circle, Clock, AlertTriangle, ChevronDown, ChevronRight,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';

interface RemediationStep {
  id: string;
  description: string;
  completed: boolean;
}

interface RemediationPlan {
  id: string;
  finding_id: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  effort: string;
  status: 'pending' | 'in_progress' | 'completed' | 'deferred';
  steps: RemediationStep[];
  finding_attack_id?: string;
  finding_endpoint?: string;
  created_at: string;
}

const SEV_COLORS: Record<string, string> = {
  critical: 'bg-red-500/20 text-red-400',
  high: 'bg-orange-500/20 text-orange-400',
  medium: 'bg-amber-500/20 text-amber-400',
  low: 'bg-blue-500/20 text-blue-400',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-white/10 text-white/40',
  in_progress: 'bg-amber-500/20 text-amber-400',
  completed: 'bg-green-500/20 text-green-400',
  deferred: 'bg-purple-500/20 text-purple-400',
};

const ALL_STATUSES = ['pending', 'in_progress', 'completed', 'deferred'];

const PLACEHOLDER_PLANS: RemediationPlan[] = [
  {
    id: 'r1', finding_id: 'f1', title: 'Parameterize SQL Queries in /v1/query', description: 'Replace string concatenation with parameterized queries to prevent SQL injection in the main query endpoint.',
    severity: 'critical', effort: '2-4 hours', status: 'in_progress', finding_attack_id: 'SQLi-UNION-001', finding_endpoint: 'POST /v1/query',
    steps: [
      { id: 's1', description: 'Identify all raw SQL string concatenation points in query handler', completed: true },
      { id: 's2', description: 'Replace with parameterized query using $1, $2 placeholders', completed: true },
      { id: 's3', description: 'Add input validation for query parameters (type, length, pattern)', completed: false },
      { id: 's4', description: 'Deploy and run regression tests', completed: false },
      { id: 's5', description: 'Re-run Sentinel scan to verify fix', completed: false },
    ],
    created_at: '2026-03-08T09:30:00Z',
  },
  {
    id: 'r2', finding_id: 'f4', title: 'SSRF Protection for Webhook Endpoint', description: 'Implement URL allowlisting and internal IP blocking for the webhook URL parameter.',
    severity: 'critical', effort: '3-5 hours', status: 'pending', finding_attack_id: 'SSRF-INTERNAL-001', finding_endpoint: 'POST /v1/webhook',
    steps: [
      { id: 's1', description: 'Create URL allowlist configuration', completed: false },
      { id: 's2', description: 'Add DNS resolution check to block internal IPs (10.x, 172.16-31.x, 192.168.x, 169.254.x)', completed: false },
      { id: 's3', description: 'Block localhost and link-local addresses', completed: false },
      { id: 's4', description: 'Add request timeout and response size limits', completed: false },
      { id: 's5', description: 'Test with SSRF payloads to confirm mitigation', completed: false },
    ],
    created_at: '2026-03-08T09:35:00Z',
  },
  {
    id: 'r3', finding_id: 'f10', title: 'Fix Negative Amount Transfer Logic', description: 'Add server-side validation to reject negative transfer amounts and implement proper business logic checks.',
    severity: 'critical', effort: '1-2 hours', status: 'pending', finding_attack_id: 'BIZ-LOGIC-001', finding_endpoint: 'POST /v1/transfer',
    steps: [
      { id: 's1', description: 'Add amount > 0 validation in transfer handler', completed: false },
      { id: 's2', description: 'Add maximum transfer limit check', completed: false },
      { id: 's3', description: 'Implement sender != receiver validation', completed: false },
      { id: 's4', description: 'Add audit logging for all transfer attempts', completed: false },
    ],
    created_at: '2026-03-08T09:40:00Z',
  },
  {
    id: 'r4', finding_id: 'f2', title: 'Output Encoding for Search Results', description: 'Apply HTML entity encoding to all user-supplied data reflected in search responses.',
    severity: 'high', effort: '1-3 hours', status: 'pending', finding_attack_id: 'XSS-REFLECTED-003', finding_endpoint: 'GET /v1/search',
    steps: [
      { id: 's1', description: 'Identify all reflection points in search response', completed: false },
      { id: 's2', description: 'Apply context-appropriate output encoding (HTML, JS, URL)', completed: false },
      { id: 's3', description: 'Add Content-Security-Policy header', completed: false },
      { id: 's4', description: 'Set X-Content-Type-Options: nosniff', completed: false },
    ],
    created_at: '2026-03-08T09:45:00Z',
  },
  {
    id: 'r5', finding_id: 'f3', title: 'Fix NoSQL Injection in Login', description: 'Sanitize login input to prevent NoSQL operator injection in authentication flow.',
    severity: 'high', effort: '2-3 hours', status: 'completed', finding_attack_id: 'AUTH-BYPASS-002', finding_endpoint: 'POST /v1/admin/login',
    steps: [
      { id: 's1', description: 'Validate that username and password are strings (not objects)', completed: true },
      { id: 's2', description: 'Strip MongoDB operators ($gt, $ne, $regex, etc.) from input', completed: true },
      { id: 's3', description: 'Add schema validation using Pydantic model', completed: true },
      { id: 's4', description: 'Add rate limiting on login endpoint', completed: true },
    ],
    created_at: '2026-03-07T16:00:00Z',
  },
  {
    id: 'r6', finding_id: 'f7', title: 'Implement Rate Limiting on Auth Endpoints', description: 'Add sliding window rate limiter for authentication-related endpoints.',
    severity: 'medium', effort: '2-4 hours', status: 'deferred', finding_attack_id: 'RATE-BURST-001', finding_endpoint: 'POST /v1/auth/token',
    steps: [
      { id: 's1', description: 'Configure rate limit rules (e.g., 10 req/min per IP for /auth/*)', completed: false },
      { id: 's2', description: 'Return 429 with Retry-After header when limit exceeded', completed: false },
      { id: 's3', description: 'Add X-RateLimit-* response headers', completed: false },
      { id: 's4', description: 'Consider account lockout after N failed attempts', completed: false },
    ],
    created_at: '2026-03-07T17:00:00Z',
  },
];

export default function RemediationPage() {
  const [plans, setPlans] = useState<RemediationPlan[]>(PLACEHOLDER_PLANS);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState('');
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const res = await superadminApi.sentinelRemediation(filterStatus || undefined);
      const p = (res as Record<string, unknown>).plans as RemediationPlan[] | undefined;
      if (p && p.length > 0) setPlans(p);
    } catch { /* use placeholders */ }
    setLoading(false);
  }, [filterStatus]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleStatusChange = async (planId: string, newStatus: string) => {
    try {
      await superadminApi.sentinelUpdateRemediation(planId, { status: newStatus });
      setPlans(prev => prev.map(p => p.id === planId ? { ...p, status: newStatus as RemediationPlan['status'] } : p));
    } catch { /* ignore */ }
  };

  const handleToggleStep = async (planId: string, stepId: string) => {
    setPlans(prev => prev.map(p => {
      if (p.id !== planId) return p;
      const newSteps = p.steps.map(s => s.id === stepId ? { ...s, completed: !s.completed } : s);
      return { ...p, steps: newSteps };
    }));
    // Optionally persist
    const plan = plans.find(p => p.id === planId);
    if (plan) {
      const updatedSteps = plan.steps.map(s => s.id === stepId ? { ...s, completed: !s.completed } : s);
      try {
        await superadminApi.sentinelUpdateRemediation(planId, { steps: updatedSteps } as unknown as Record<string, unknown>);
      } catch { /* ignore */ }
    }
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };

  // Sort: critical first, then high, medium, low; within same severity, pending before in_progress
  const sevOrder: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };
  const statOrder: Record<string, number> = { pending: 0, in_progress: 1, deferred: 2, completed: 3 };

  const filtered = plans
    .filter(p => !filterStatus || p.status === filterStatus)
    .sort((a, b) => (sevOrder[a.severity] || 9) - (sevOrder[b.severity] || 9) || (statOrder[a.status] || 9) - (statOrder[b.status] || 9));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-green-500/20 flex items-center justify-center">
          <Wrench className="w-5 h-5 text-green-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Remediation Plans</h1>
          <p className="text-xs text-white/40">{plans.length} plans &middot; {plans.filter(p => p.status === 'completed').length} completed</p>
        </div>
      </div>

      {/* Status Filter */}
      <div className="flex items-center gap-2">
        <button onClick={() => setFilterStatus('')}
          className={`px-2.5 py-1 rounded-lg text-xs transition ${!filterStatus ? 'bg-green-500/20 text-green-400' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}>
          All ({plans.length})
        </button>
        {ALL_STATUSES.map(s => {
          const count = plans.filter(p => p.status === s).length;
          return (
            <button key={s} onClick={() => setFilterStatus(s)}
              className={`px-2.5 py-1 rounded-lg text-xs transition ${filterStatus === s ? 'bg-green-500/20 text-green-400' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}>
              {s.replace(/_/g, ' ')} ({count})
            </button>
          );
        })}
      </div>

      {/* Plans List */}
      <div className="space-y-3">
        {filtered.map(p => {
          const completedSteps = p.steps.filter(s => s.completed).length;
          const totalSteps = p.steps.length;
          const pct = totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0;

          return (
            <div key={p.id} className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
              {/* Plan Header */}
              <div
                className="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-white/[0.02] transition"
                onClick={() => setExpandedId(expandedId === p.id ? null : p.id)}
              >
                <div className="text-white/20">
                  {expandedId === p.id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </div>
                <span className={`px-1.5 py-0.5 rounded text-[10px] ${SEV_COLORS[p.severity]}`}>{p.severity}</span>
                <div className="flex-1">
                  <div className="text-sm font-medium text-white/80">{p.title}</div>
                  {p.finding_attack_id && (
                    <div className="text-[10px] text-white/30 mt-0.5">
                      {p.finding_attack_id} &middot; {p.finding_endpoint}
                    </div>
                  )}
                </div>
                <span className="text-[10px] text-white/30 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {p.effort}
                </span>
                <div className="w-24 text-right">
                  <div className="text-[10px] text-white/30 mb-0.5">{completedSteps}/{totalSteps} steps</div>
                  <div className="w-full h-1 bg-white/5 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full transition-all ${pct === 100 ? 'bg-green-500' : 'bg-amber-500'}`} style={{ width: `${pct}%` }} />
                  </div>
                </div>
                <select
                  value={p.status}
                  onChange={e => { e.stopPropagation(); handleStatusChange(p.id, e.target.value); }}
                  onClick={e => e.stopPropagation()}
                  className={`px-2 py-1 rounded text-[10px] bg-transparent border border-white/10 focus:outline-none ${STATUS_COLORS[p.status] || ''}`}
                >
                  {ALL_STATUSES.map(s => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
                </select>
              </div>

              {/* Expanded Content */}
              {expandedId === p.id && (
                <div className="border-t border-white/5 px-4 py-3 space-y-3">
                  <p className="text-xs text-white/50">{p.description}</p>

                  {/* Steps Checklist */}
                  <div>
                    <div className="text-[10px] text-white/30 uppercase tracking-wider mb-2">Remediation Steps</div>
                    <div className="space-y-1.5">
                      {p.steps.map(step => (
                        <label key={step.id} className="flex items-start gap-2 cursor-pointer group">
                          <button
                            onClick={() => handleToggleStep(p.id, step.id)}
                            className="mt-0.5 shrink-0"
                          >
                            {step.completed ? (
                              <CheckCircle className="w-4 h-4 text-green-400" />
                            ) : (
                              <Circle className="w-4 h-4 text-white/20 group-hover:text-white/40" />
                            )}
                          </button>
                          <span className={`text-xs ${step.completed ? 'text-white/30 line-through' : 'text-white/60'}`}>
                            {step.description}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="text-[10px] text-white/20">Created {fmtTime(p.created_at)}</div>
                </div>
              )}
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-8 text-center text-xs text-white/30">
            No remediation plans match the current filter
          </div>
        )}
      </div>
    </div>
  );
}
