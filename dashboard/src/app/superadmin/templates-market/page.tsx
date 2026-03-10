'use client';

import { useState, useEffect, useCallback } from 'react';
import { ShoppingBag, Search, Star, Download, Award, X } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface Template {
  id: string; name: string; author: string; version: string; description: string;
  rating: number; downloads: number; category: string; featured: boolean;
  skills: string[]; system_prompt: string;
}

const CATEGORIES = ['All', 'Analytics', 'Support', 'Security', 'DevOps', 'Content', 'Research', 'Sales', 'QA', 'Finance', 'HR', 'Legal', 'Marketing'];

const PLACEHOLDER_TEMPLATES: Template[] = [
  { id: '1', name: 'Data Analyst Pro', author: 'CortexDB Team', version: '2.1.0', description: 'Advanced data analysis agent with SQL generation, visualization recommendations, and automated report building capabilities.', rating: 4.8, downloads: 12540, category: 'Analytics', featured: true, skills: ['SQL Generation', 'Data Visualization', 'Report Building', 'Statistical Analysis'], system_prompt: 'You are an expert data analyst...' },
  { id: '2', name: 'Security Sentinel', author: 'SecOps Labs', version: '1.5.2', description: 'Continuous security monitoring agent that detects anomalies, scans for vulnerabilities, and enforces compliance policies.', rating: 4.9, downloads: 8920, category: 'Security', featured: true, skills: ['Threat Detection', 'Vulnerability Scanning', 'Compliance Audit', 'Incident Response'], system_prompt: 'You are a security operations specialist...' },
  { id: '3', name: 'DevOps Automator', author: 'CloudFirst', version: '3.0.1', description: 'CI/CD pipeline management agent with Kubernetes orchestration, monitoring, and infrastructure-as-code support.', rating: 4.6, downloads: 15200, category: 'DevOps', featured: false, skills: ['CI/CD', 'Kubernetes', 'Terraform', 'Monitoring'], system_prompt: 'You are a DevOps engineer...' },
  { id: '4', name: 'Customer Success Bot', author: 'SupportAI', version: '1.8.0', description: 'Multi-channel customer support agent with sentiment analysis, ticket routing, and knowledge base integration.', rating: 4.5, downloads: 6730, category: 'Support', featured: false, skills: ['Ticket Routing', 'Sentiment Analysis', 'Knowledge Base', 'Escalation'], system_prompt: 'You are a customer support specialist...' },
  { id: '5', name: 'Content Strategist', author: 'CreativeAI', version: '2.0.0', description: 'Content creation and strategy agent for blog posts, social media, SEO optimization, and editorial calendar management.', rating: 4.7, downloads: 9100, category: 'Content', featured: true, skills: ['SEO', 'Copywriting', 'Social Media', 'Editorial Planning'], system_prompt: 'You are a content strategist...' },
  { id: '6', name: 'Research Assistant', author: 'AcademicAI', version: '1.3.0', description: 'Academic and market research agent that gathers sources, synthesizes findings, and generates structured reports.', rating: 4.4, downloads: 4200, category: 'Research', featured: false, skills: ['Literature Review', 'Data Synthesis', 'Citation Management', 'Report Writing'], system_prompt: 'You are a research assistant...' },
  { id: '7', name: 'Sales Pipeline Manager', author: 'RevOps Inc', version: '1.6.0', description: 'Sales automation agent that qualifies leads, manages follow-ups, and provides revenue forecasting.', rating: 4.3, downloads: 5600, category: 'Sales', featured: false, skills: ['Lead Scoring', 'Pipeline Management', 'Forecasting', 'CRM Integration'], system_prompt: 'You are a sales operations specialist...' },
  { id: '8', name: 'QA Test Orchestrator', author: 'CortexDB Team', version: '1.2.0', description: 'Automated testing agent that generates test cases, runs suites, tracks coverage, and reports regressions.', rating: 4.6, downloads: 3800, category: 'QA', featured: false, skills: ['Test Generation', 'Coverage Analysis', 'Regression Detection', 'Performance Testing'], system_prompt: 'You are a QA engineer...' },
  { id: '9', name: 'Financial Analyst', author: 'FinTech AI', version: '2.2.0', description: 'Financial modeling agent with budget analysis, forecasting, compliance checking, and expense optimization.', rating: 4.7, downloads: 7300, category: 'Finance', featured: true, skills: ['Budget Analysis', 'Forecasting', 'Compliance', 'Cost Optimization'], system_prompt: 'You are a financial analyst...' },
];

export default function TemplatesMarketPage() {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const [expanded, setExpanded] = useState<string | null>(null);

  const loadTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const res = await (superadminApi as Record<string, unknown> as any).saRequest('/v1/superadmin/templates-market');
      setTemplates(Array.isArray(res) ? res : (res as any)?.templates ?? []);
    } catch {
      setTemplates(PLACEHOLDER_TEMPLATES);
    }
    setLoading(false);
  }, []);

  useEffect(() => { loadTemplates(); }, [loadTemplates]);

  const filtered = templates.filter((t) => {
    if (category !== 'All' && t.category !== category) return false;
    if (search && !t.name.toLowerCase().includes(search.toLowerCase()) && !t.description.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const totalDownloads = templates.reduce((s, t) => s + t.downloads, 0);
  const avgRating = templates.length ? (templates.reduce((s, t) => s + t.rating, 0) / templates.length).toFixed(1) : '0';
  const categories = new Set(templates.map((t) => t.category));

  const statCards = [
    { label: 'Total Templates', value: templates.length, color: 'text-pink-400' },
    { label: 'Total Downloads', value: totalDownloads.toLocaleString(), color: 'text-blue-400' },
    { label: 'Avg Rating', value: avgRating, color: 'text-amber-400' },
    { label: 'Categories', value: categories.size, color: 'text-green-400' },
  ];

  const renderStars = (rating: number) => (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className={`w-3 h-3 ${i <= Math.round(rating) ? 'text-amber-400 fill-amber-400' : 'text-white/20'}`} />
      ))}
      <span className="text-[10px] text-white/40 ml-1">{rating}</span>
    </div>
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-pink-500/20 flex items-center justify-center">
          <ShoppingBag className="w-5 h-5 text-pink-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">Agent Template Marketplace</h1>
          <p className="text-xs text-white/40">Browse and install community agent templates</p>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        {statCards.map((s) => (
          <div key={s.label} className="bg-white/5 border border-white/10 rounded-xl p-4">
            <div className="text-xs text-white/40 mb-1">{s.label}</div>
            <div className={`text-2xl font-bold ${s.color}`}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search templates..."
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:border-pink-500/50" />
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {CATEGORIES.map((c) => (
          <button key={c} onClick={() => setCategory(c)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${category === c ? 'bg-pink-500/20 text-pink-400 border border-pink-500/30' : 'bg-white/5 text-white/40 hover:bg-white/10'}`}>
            {c}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-16 text-white/30 text-sm">Loading templates...</div>
      ) : filtered.length === 0 ? (
        <div className="bg-white/5 border border-white/10 rounded-xl p-12 text-center">
          <ShoppingBag className="w-10 h-10 text-white/10 mx-auto mb-3" />
          <p className="text-sm text-white/30">No templates found</p>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {filtered.map((tmpl) => (
            <div key={tmpl.id} className="bg-white/5 border border-white/10 rounded-xl p-4 hover:border-white/20 transition">
              <div className="flex items-start justify-between mb-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{tmpl.name}</span>
                    {tmpl.featured && <Award className="w-3.5 h-3.5 text-amber-400" />}
                  </div>
                  <div className="text-[10px] text-white/30">by {tmpl.author} &middot; v{tmpl.version}</div>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/10 text-white/50">{tmpl.category}</span>
              </div>
              <p className="text-xs text-white/50 mb-3 line-clamp-2">{tmpl.description}</p>
              <div className="flex items-center justify-between">
                {renderStars(tmpl.rating)}
                <div className="flex items-center gap-1 text-[10px] text-white/30">
                  <Download className="w-3 h-3" /> {tmpl.downloads.toLocaleString()}
                </div>
              </div>
              <div className="flex items-center gap-2 mt-3">
                <button onClick={() => setExpanded(expanded === tmpl.id ? null : tmpl.id)}
                  className="flex-1 text-center px-3 py-1.5 rounded-lg bg-white/5 text-white/50 text-xs hover:bg-white/10 transition">
                  {expanded === tmpl.id ? 'Collapse' : 'Details'}
                </button>
                <button className="flex-1 text-center px-3 py-1.5 rounded-lg bg-pink-500/20 text-pink-400 text-xs font-medium hover:bg-pink-500/30 transition">
                  Install
                </button>
              </div>
              {expanded === tmpl.id && (
                <div className="mt-3 pt-3 border-t border-white/10 space-y-2">
                  <div className="text-xs text-white/60">{tmpl.description}</div>
                  <div>
                    <div className="text-[10px] text-white/30 mb-1">Skills</div>
                    <div className="flex flex-wrap gap-1">
                      {tmpl.skills.map((s) => (
                        <span key={s} className="text-[10px] px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400">{s}</span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-[10px] text-white/30 mb-1">System Prompt Preview</div>
                    <div className="bg-black/30 rounded-lg p-2 text-[10px] text-white/40 font-mono">{tmpl.system_prompt}</div>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
