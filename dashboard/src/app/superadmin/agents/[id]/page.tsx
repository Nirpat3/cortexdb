'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Bot, ArrowLeft, RefreshCw, Star, TrendingUp, Plus, Trash2,
  Award, Zap, Target, Brain, Wrench, Users, Shield, BarChart3,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

const DEPT_COLORS: Record<string, string> = {
  EXEC: '#EF4444', ENG: '#3B82F6', QA: '#34D399', OPS: '#F59E0B', SEC: '#EC4899', DOC: '#8B5CF6',
};

const CATEGORY_ICONS: Record<string, any> = {
  technical: Wrench, domain: Brain, soft: Users, operational: Shield,
};

const CATEGORY_COLORS: Record<string, string> = {
  technical: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  domain: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  soft: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  operational: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
};

const LEVEL_COLORS: Record<string, string> = {
  novice: 'bg-gray-500/20 text-gray-400',
  beginner: 'bg-green-500/20 text-green-400',
  intermediate: 'bg-blue-500/20 text-blue-400',
  advanced: 'bg-purple-500/20 text-purple-400',
  expert: 'bg-amber-500/20 text-amber-400',
};

function XpBar({ xp, level, xpToNext }: { xp: number; level: number; xpToNext: number | null }) {
  const thresholds: Record<number, number> = { 1: 0, 2: 50, 3: 150, 4: 400, 5: 1000 };
  const currentThreshold = thresholds[level] || 0;
  const nextThreshold = thresholds[level + 1];
  const progress = nextThreshold
    ? ((xp - currentThreshold) / (nextThreshold - currentThreshold)) * 100
    : 100;

  return (
    <div className="w-full">
      <div className="flex justify-between text-[10px] text-white/30 mb-0.5">
        <span>{xp} XP</span>
        <span>{xpToNext !== null ? `${xpToNext} to next` : 'MAX'}</span>
      </div>
      <div className="w-full h-1.5 rounded-full bg-white/5">
        <div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all"
          style={{ width: `${Math.min(progress, 100)}%` }} />
      </div>
    </div>
  );
}

export default function AgentProfilePage() {
  const { t } = useTranslation();
  const params = useParams();
  const router = useRouter();
  const agentId = params.id as string;

  const [agent, setAgent] = useState<D | null>(null);
  const [profile, setProfile] = useState<D | null>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [scores, setScores] = useState<D | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'skills' | 'history' | 'scores'>('skills');

  // Add skill form
  const [showAdd, setShowAdd] = useState(false);
  const [newSkill, setNewSkill] = useState('');
  const [newCategory, setNewCategory] = useState('technical');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [a, p, h, s] = await Promise.allSettled([
        superadminApi.getTeamAgent(agentId),
        superadminApi.getSkillProfile(agentId),
        superadminApi.getSkillHistory(agentId),
        superadminApi.getAgentScores(agentId),
      ]);
      if (a.status === 'fulfilled') setAgent(a.value as D);
      if (p.status === 'fulfilled') setProfile(p.value as D);
      if (h.status === 'fulfilled') setHistory((h.value as D).history || []);
      if (s.status === 'fulfilled') setScores(s.value as D);
    } catch { /* silent */ }
    setLoading(false);
  }, [agentId]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleAddSkill = async () => {
    if (!newSkill.trim()) return;
    try {
      await superadminApi.addSkill(agentId, newSkill.trim(), newCategory);
      setNewSkill('');
      setShowAdd(false);
      await loadData();
    } catch { /* silent */ }
  };

  const handleRemoveSkill = async (skillName: string) => {
    try {
      await superadminApi.removeSkill(agentId, skillName);
      await loadData();
    } catch { /* silent */ }
  };

  if (!agent) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-white/30">{loading ? t('common.loading') : t('common.noData')}</p>
      </div>
    );
  }

  const color = DEPT_COLORS[agent.department] || '#6366F1';
  const skills = profile?.skills || [];
  const byCategory = profile?.by_category || {};
  const summary = profile?.summary || {};

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button onClick={() => router.push('/superadmin/agents')}
            className="p-2 rounded-lg glass hover:bg-white/10 transition">
            <ArrowLeft className="w-4 h-4 text-white/40" />
          </button>
          <div className="w-12 h-12 rounded-xl flex items-center justify-center"
            style={{ backgroundColor: `${color}20` }}>
            <Bot className="w-6 h-6" style={{ color }} />
          </div>
          <div>
            <h1 className="text-xl font-bold">{agent.name}</h1>
            <p className="text-xs text-white/40">{agent.title} · {agent.agent_id} · {agent.department}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] px-2 py-0.5 rounded-full ${
            agent.state === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
            agent.state === 'working' ? 'bg-blue-500/20 text-blue-300' : 'bg-white/10 text-white/40'
          }`}>{agent.state}</span>
          <span className="text-xs text-white/30">{agent.llm_provider}:{agent.llm_model}</span>
          <button onClick={loadData} disabled={loading}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
          </button>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-6 gap-3">
        <div className="glass rounded-xl p-3 border border-white/5">
          <div className="text-[10px] text-white/40 mb-1">Total Skills</div>
          <div className="text-xl font-bold">{summary.total_skills || 0}</div>
        </div>
        <div className="glass rounded-xl p-3 border border-white/5">
          <div className="text-[10px] text-white/40 mb-1">Total XP</div>
          <div className="text-xl font-bold text-blue-400">{summary.total_xp || 0}</div>
        </div>
        <div className="glass rounded-xl p-3 border border-white/5">
          <div className="text-[10px] text-white/40 mb-1">Avg Level</div>
          <div className="text-xl font-bold">{summary.avg_level || 0}</div>
        </div>
        <div className="glass rounded-xl p-3 border border-white/5">
          <div className="text-[10px] text-white/40 mb-1">Confidence</div>
          <div className="text-xl font-bold text-green-400">{((summary.avg_confidence || 0) * 100).toFixed(0)}%</div>
        </div>
        <div className="glass rounded-xl p-3 border border-white/5">
          <div className="text-[10px] text-white/40 mb-1">Expert Skills</div>
          <div className="text-xl font-bold text-amber-400">{summary.expert_skills || 0}</div>
        </div>
        <div className="glass rounded-xl p-3 border border-white/5">
          <div className="text-[10px] text-white/40 mb-1">Endorsements</div>
          <div className="text-xl font-bold text-purple-400">{summary.total_endorsements || 0}</div>
        </div>
      </div>

      {/* Agent Info Row */}
      <div className="grid grid-cols-2 gap-4">
        <div className="glass rounded-xl p-4 border border-white/5">
          <h3 className="text-xs font-medium text-white/40 mb-2">Responsibilities</h3>
          <div className="flex flex-wrap gap-1">
            {(agent.responsibilities || []).map((r: string, i: number) => (
              <span key={i} className="text-[10px] glass px-2 py-0.5 rounded-full text-white/60">{r}</span>
            ))}
          </div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <div className="text-white/30 mb-1">Tasks Done</div>
              <div className="text-lg font-bold">{agent.tasks_completed}</div>
            </div>
            <div>
              <div className="text-white/30 mb-1">Tasks Failed</div>
              <div className="text-lg font-bold text-red-400">{agent.tasks_failed}</div>
            </div>
            <div>
              <div className="text-white/30 mb-1">Quality Avg</div>
              <div className="text-lg font-bold text-green-400">{scores?.avg || '-'}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center justify-between">
        <div className="flex gap-1 bg-white/5 rounded-lg p-1 w-fit">
          {([
            { id: 'skills', label: 'Skills', icon: Star },
            { id: 'history', label: 'Enhancement History', icon: TrendingUp },
            { id: 'scores', label: 'Quality Scores', icon: BarChart3 },
          ] as const).map(t => (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition ${
                tab === t.id ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
              }`}>
              <t.icon className="w-3.5 h-3.5" /> {t.label}
            </button>
          ))}
        </div>
        {tab === 'skills' && (
          <button onClick={() => setShowAdd(!showAdd)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/20 text-xs text-blue-300 hover:bg-blue-500/30 transition">
            <Plus className="w-3.5 h-3.5" /> {t('common.add')} Skill
          </button>
        )}
      </div>

      {/* Add Skill Form */}
      {showAdd && tab === 'skills' && (
        <div className="glass rounded-xl p-4 border border-blue-500/20 flex items-end gap-3">
          <div className="flex-1">
            <label className="text-xs text-white/40 block mb-1">Skill Name</label>
            <input value={newSkill} onChange={e => setNewSkill(e.target.value)}
              placeholder="e.g., kubernetes, code-review"
              className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-blue-500/50 focus:outline-none" />
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Category</label>
            <select value={newCategory} onChange={e => setNewCategory(e.target.value)}
              className="glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-blue-500/50 focus:outline-none">
              <option value="technical">Technical</option>
              <option value="domain">Domain</option>
              <option value="soft">Soft</option>
              <option value="operational">Operational</option>
            </select>
          </div>
          <button onClick={handleAddSkill} disabled={!newSkill.trim()}
            className="px-4 py-2 rounded-lg bg-blue-500/20 text-blue-300 text-xs font-medium hover:bg-blue-500/30 transition disabled:opacity-50">
            {t('common.add')}
          </button>
        </div>
      )}

      {/* Skills Tab */}
      {tab === 'skills' && (
        <div className="space-y-4">
          {Object.entries(byCategory).length === 0 ? (
            <div className="glass rounded-xl p-8 border border-white/5 text-center">
              <p className="text-sm text-white/30">{t('common.noData')}</p>
            </div>
          ) : (
            Object.entries(byCategory).map(([cat, catSkills]: [string, any]) => {
              const CatIcon = CATEGORY_ICONS[cat] || Wrench;
              const catColor = CATEGORY_COLORS[cat] || CATEGORY_COLORS.technical;
              return (
                <div key={cat} className={`glass rounded-xl p-5 border ${catColor.split(' ')[2] || 'border-white/5'}`}>
                  <h3 className="text-sm font-medium mb-3 flex items-center gap-2 capitalize">
                    <CatIcon className={`w-4 h-4 ${catColor.split(' ')[0]}`} /> {cat} Skills
                    <span className="text-[10px] text-white/30 font-normal">({catSkills.length})</span>
                  </h3>
                  <div className="grid grid-cols-2 gap-3">
                    {catSkills.map((skill: any) => (
                      <div key={skill.name} className="rounded-lg bg-white/5 p-3 group">
                        <div className="flex items-center justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{skill.name}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${LEVEL_COLORS[skill.level_name] || ''}`}>
                              {skill.level_name}
                            </span>
                          </div>
                          <div className="flex items-center gap-1.5">
                            {skill.endorsements > 0 && (
                              <span className="text-[10px] text-amber-400 flex items-center gap-0.5">
                                <Award className="w-3 h-3" /> {skill.endorsements}
                              </span>
                            )}
                            <span className="text-[10px] text-white/20">
                              {(skill.confidence * 100).toFixed(0)}% conf
                            </span>
                            <button onClick={() => handleRemoveSkill(skill.name)}
                              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 transition">
                              <Trash2 className="w-3 h-3 text-red-400/60" />
                            </button>
                          </div>
                        </div>
                        <XpBar xp={skill.xp} level={skill.level} xpToNext={skill.xp_to_next} />
                        <div className="flex justify-between mt-1 text-[10px] text-white/20">
                          <span>Lv.{skill.level}</span>
                          <span>{skill.task_count} tasks</span>
                          {skill.last_used && (
                            <span>{new Date(skill.last_used * 1000).toLocaleDateString()}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Enhancement History Tab */}
      {tab === 'history' && (
        <div className="glass rounded-xl p-5 border border-white/5">
          {history.length === 0 ? (
            <p className="text-sm text-white/30 text-center py-4">{t('common.noData')}</p>
          ) : (
            <div className="space-y-2">
              {[...history].reverse().map((event: any, i: number) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-white/5">
                  <Zap className="w-4 h-4 text-amber-400 mt-0.5 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="text-[10px] text-white/30 mb-1">
                      {event.timestamp ? new Date(event.timestamp * 1000).toLocaleString() : ''}
                    </div>
                    {Object.entries(event.xp_awarded || {}).length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1">
                        {Object.entries(event.xp_awarded).map(([skill, xp]: [string, any]) => (
                          <span key={skill} className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-400">
                            {skill} +{xp} XP
                          </span>
                        ))}
                      </div>
                    )}
                    {(event.level_ups || []).map((lu: any, j: number) => (
                      <div key={j} className="text-xs text-amber-400 flex items-center gap-1">
                        <TrendingUp className="w-3 h-3" /> {lu.skill} leveled up to {lu.level_name}!
                      </div>
                    ))}
                    {(event.new_skills || []).map((ns: any, j: number) => (
                      <div key={j} className="text-xs text-green-400 flex items-center gap-1">
                        <Plus className="w-3 h-3" /> New skill discovered: {ns.skill} ({ns.category})
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Quality Scores Tab */}
      {tab === 'scores' && (
        <div className="glass rounded-xl p-5 border border-white/5">
          {!scores || scores.total === 0 ? (
            <p className="text-sm text-white/30 text-center py-4">{t('common.noData')}</p>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="glass rounded-lg p-3">
                  <div className="text-xs text-white/30">Overall Avg</div>
                  <div className="text-2xl font-bold text-green-400">{scores.avg}/10</div>
                </div>
                <div className="glass rounded-lg p-3">
                  <div className="text-xs text-white/30">Total Graded</div>
                  <div className="text-2xl font-bold">{scores.total}</div>
                </div>
                <div className="glass rounded-lg p-3">
                  <div className="text-xs text-white/30">Last Grade</div>
                  <div className="text-2xl font-bold">{scores.last_grade || '-'}</div>
                </div>
              </div>
              {scores.by_category && Object.keys(scores.by_category).length > 0 && (
                <div>
                  <h4 className="text-xs font-medium text-white/40 mb-2">By Category</h4>
                  <div className="grid grid-cols-2 gap-2">
                    {Object.entries(scores.by_category).map(([cat, data]: [string, any]) => (
                      <div key={cat} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                        <div>
                          <div className="text-xs font-medium capitalize">{cat}</div>
                          <div className="text-[10px] text-white/30">{data.total} tasks</div>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-bold text-green-400">{data.avg}/10</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
