'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Target, Plus, Play, Trash2, Loader2, Clock, CheckCircle, XCircle,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';

interface Campaign {
  id: string;
  name: string;
  description: string;
  status: 'planned' | 'running' | 'completed' | 'failed';
  categories: string[];
  aggression: number;
  concurrency: number;
  progress?: number;
  total_tests?: number;
  completed_tests?: number;
  findings_count?: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

const STATUS_COLORS: Record<string, string> = {
  planned: 'bg-blue-500/20 text-blue-400',
  running: 'bg-amber-500/20 text-amber-400',
  completed: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
};

const AGGRESSION_LABELS = ['', 'Passive', 'Light', 'Standard', 'Aggressive', 'Full'];
const AGGRESSION_COLORS = ['', 'text-green-400', 'text-blue-400', 'text-amber-400', 'text-orange-400', 'text-red-400'];

const ALL_CATEGORIES = [
  'sql_injection', 'xss', 'authentication', 'authorization', 'injection',
  'ssrf', 'path_traversal', 'csrf', 'rate_limiting', 'information_disclosure',
  'business_logic', 'api_abuse',
];

const PLACEHOLDER_CAMPAIGNS: Campaign[] = [
  { id: '1', name: 'API Security Sweep', description: 'Full sweep of all API endpoints for injection and auth vulnerabilities', status: 'running', categories: ['sql_injection', 'xss', 'authentication'], aggression: 3, concurrency: 5, progress: 64, total_tests: 150, completed_tests: 96, findings_count: 7, created_at: '2026-03-08T08:00:00Z', started_at: '2026-03-08T08:01:00Z' },
  { id: '2', name: 'Weekly Regression', description: 'Weekly automated regression test for known vulnerability patterns', status: 'planned', categories: ['injection', 'ssrf', 'path_traversal', 'csrf'], aggression: 2, concurrency: 3, created_at: '2026-03-07T22:00:00Z' },
  { id: '3', name: 'Full Pentest Simulation', description: 'Aggressive full-spectrum penetration test simulation', status: 'completed', categories: ALL_CATEGORIES, aggression: 5, concurrency: 10, progress: 100, total_tests: 480, completed_tests: 480, findings_count: 37, created_at: '2026-03-06T10:00:00Z', started_at: '2026-03-06T10:01:00Z', completed_at: '2026-03-06T12:45:00Z' },
  { id: '4', name: 'Auth-Only Spot Check', description: 'Quick authentication and authorization check', status: 'failed', categories: ['authentication', 'authorization'], aggression: 4, concurrency: 5, progress: 32, total_tests: 80, completed_tests: 26, findings_count: 2, created_at: '2026-03-05T14:00:00Z', started_at: '2026-03-05T14:01:00Z', completed_at: '2026-03-05T14:15:00Z' },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>(PLACEHOLDER_CAMPAIGNS);
  const [showCreate, setShowCreate] = useState(false);
  const [loading, setLoading] = useState(true);
  const [executingId, setExecutingId] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    description: '',
    categories: [] as string[],
    aggression: 3,
    concurrency: 5,
  });

  const fetchData = useCallback(async () => {
    try {
      const res = await superadminApi.sentinelCampaigns();
      const c = (res as Record<string, unknown>).campaigns as Campaign[] | undefined;
      if (c && c.length > 0) setCampaigns(c);
    } catch { /* use placeholders */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const toggleCategory = (cat: string) => {
    setForm(prev => ({
      ...prev,
      categories: prev.categories.includes(cat) ? prev.categories.filter(c => c !== cat) : [...prev.categories, cat],
    }));
  };

  const handleCreate = async () => {
    if (!form.name.trim() || form.categories.length === 0) return;
    try {
      await superadminApi.sentinelCreateCampaign(form as unknown as Record<string, unknown>);
      setForm({ name: '', description: '', categories: [], aggression: 3, concurrency: 5 });
      setShowCreate(false);
      await fetchData();
    } catch { /* ignore */ }
  };

  const handleExecute = async (id: string) => {
    setExecutingId(id);
    try {
      await superadminApi.sentinelExecuteCampaign(id);
      await fetchData();
    } catch { /* ignore */ }
    setExecutingId(null);
  };

  const handleDelete = async (id: string) => {
    try {
      await superadminApi.sentinelDeleteCampaign(id);
      setCampaigns(prev => prev.filter(c => c.id !== id));
    } catch { /* ignore */ }
  };

  const fmtTime = (ts: string) => { try { return new Date(ts).toLocaleString(); } catch { return ts; } };
  const fmtCategory = (c: string) => c.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center">
            <Target className="w-5 h-5 text-blue-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">Test Campaigns</h1>
            <p className="text-xs text-white/40">Plan, execute, and monitor security testing campaigns</p>
          </div>
        </div>
        <button onClick={() => setShowCreate(!showCreate)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/20 text-blue-400 text-xs font-medium hover:bg-blue-500/30 transition">
          <Plus className="w-3.5 h-3.5" /> New Campaign
        </button>
      </div>

      {/* Create Form */}
      {showCreate && (
        <div className="bg-white/5 border border-white/10 rounded-xl p-4 space-y-4">
          <div className="text-sm font-medium">Create Campaign</div>
          <div className="grid grid-cols-2 gap-3">
            <input value={form.name} onChange={e => setForm({ ...form, name: e.target.value })}
              placeholder="Campaign name" className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none" />
            <input value={form.description} onChange={e => setForm({ ...form, description: e.target.value })}
              placeholder="Description" className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none" />
          </div>

          {/* Category Checkboxes */}
          <div>
            <div className="text-xs text-white/40 mb-2">Test Categories</div>
            <div className="grid grid-cols-4 gap-2">
              {ALL_CATEGORIES.map(cat => (
                <label key={cat} className="flex items-center gap-1.5 text-xs text-white/50 cursor-pointer hover:text-white/70">
                  <input type="checkbox" checked={form.categories.includes(cat)} onChange={() => toggleCategory(cat)}
                    className="rounded bg-white/5 border-white/10" />
                  {fmtCategory(cat)}
                </label>
              ))}
            </div>
            <button onClick={() => setForm(prev => ({ ...prev, categories: prev.categories.length === ALL_CATEGORIES.length ? [] : [...ALL_CATEGORIES] }))}
              className="text-[10px] text-white/30 hover:text-white/50 mt-1">
              {form.categories.length === ALL_CATEGORIES.length ? 'Deselect all' : 'Select all'}
            </button>
          </div>

          {/* Aggression Slider */}
          <div className="flex items-center gap-4">
            <div className="flex-1">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-white/40">Aggression Level</span>
                <span className={`text-xs font-medium ${AGGRESSION_COLORS[form.aggression]}`}>{AGGRESSION_LABELS[form.aggression]}</span>
              </div>
              <input type="range" min={1} max={5} value={form.aggression} onChange={e => setForm({ ...form, aggression: parseInt(e.target.value) })}
                className="w-full h-1.5 bg-white/10 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white" />
              <div className="flex justify-between text-[9px] text-white/20 mt-0.5">
                <span>Passive</span><span>Light</span><span>Standard</span><span>Aggressive</span><span>Full</span>
              </div>
            </div>
            <div>
              <label className="text-xs text-white/40 block mb-1">Concurrency</label>
              <input type="number" min={1} max={50} value={form.concurrency} onChange={e => setForm({ ...form, concurrency: parseInt(e.target.value) || 1 })}
                className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs focus:outline-none" />
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button onClick={handleCreate} disabled={!form.name.trim() || form.categories.length === 0}
              className="px-4 py-2 rounded-lg bg-blue-500/20 text-blue-400 text-xs font-medium hover:bg-blue-500/30 transition disabled:opacity-30">
              Create Campaign
            </button>
            <button onClick={() => setShowCreate(false)}
              className="px-4 py-2 rounded-lg bg-white/5 text-white/40 text-xs hover:bg-white/10 transition">Cancel</button>
          </div>
        </div>
      )}

      {/* Campaign List */}
      <div className="space-y-3">
        {campaigns.map(c => (
          <div key={c.id} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-3">
                <h3 className="text-sm font-medium text-white/80">{c.name}</h3>
                <span className={`px-2 py-0.5 rounded-full text-[10px] ${STATUS_COLORS[c.status]}`}>{c.status}</span>
                <span className={`text-[10px] ${AGGRESSION_COLORS[c.aggression]}`}>
                  {AGGRESSION_LABELS[c.aggression]}
                </span>
              </div>
              <div className="flex items-center gap-2">
                {c.status === 'planned' && (
                  <button onClick={() => handleExecute(c.id)} disabled={executingId === c.id}
                    className="flex items-center gap-1 px-2 py-1 rounded-lg bg-green-500/20 text-green-400 text-[10px] hover:bg-green-500/30 transition disabled:opacity-50">
                    {executingId === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                    Execute
                  </button>
                )}
                {(c.status === 'planned' || c.status === 'completed' || c.status === 'failed') && (
                  <button onClick={() => handleDelete(c.id)}
                    className="p-1 rounded hover:bg-red-500/20 text-white/20 hover:text-red-400 transition">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            {c.description && <p className="text-xs text-white/40 mb-2">{c.description}</p>}

            <div className="flex items-center gap-2 flex-wrap mb-2">
              {c.categories.map(cat => (
                <span key={cat} className="px-1.5 py-0.5 rounded bg-white/5 text-[10px] text-white/40">{fmtCategory(cat)}</span>
              ))}
            </div>

            {/* Progress bar for running campaigns */}
            {c.status === 'running' && c.progress !== undefined && (
              <div className="mb-2">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-[10px] text-white/30">{c.completed_tests || 0} / {c.total_tests || 0} tests</span>
                  <span className="text-[10px] font-medium text-amber-400">{c.progress}%</span>
                </div>
                <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full rounded-full bg-amber-500 transition-all" style={{ width: `${c.progress}%` }} />
                </div>
              </div>
            )}

            <div className="flex items-center gap-4 text-[10px] text-white/30">
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" /> Created {fmtTime(c.created_at)}</span>
              {c.started_at && <span>Started {fmtTime(c.started_at)}</span>}
              {c.completed_at && <span>Completed {fmtTime(c.completed_at)}</span>}
              {c.findings_count !== undefined && (
                <span className="flex items-center gap-1">
                  {c.findings_count > 0 ? <XCircle className="w-3 h-3 text-red-400" /> : <CheckCircle className="w-3 h-3 text-green-400" />}
                  {c.findings_count} findings
                </span>
              )}
              <span>Concurrency: {c.concurrency}</span>
            </div>
          </div>
        ))}

        {campaigns.length === 0 && (
          <div className="bg-white/5 border border-white/10 rounded-xl p-8 text-center text-xs text-white/30">
            No campaigns yet. Create your first security test campaign.
          </div>
        )}
      </div>
    </div>
  );
}
