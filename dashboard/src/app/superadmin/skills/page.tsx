'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Star, RefreshCw, Trophy, BookOpen, Wrench, Brain, Users, Shield, Award } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

const CAT_ICONS: Record<string, any> = {
  technical: Wrench, domain: Brain, soft: Users, operational: Shield,
};

const CAT_COLORS: Record<string, string> = {
  technical: 'text-blue-400', domain: 'text-purple-400',
  soft: 'text-amber-400', operational: 'text-cyan-400',
};

const LEVEL_COLORS: Record<number, string> = {
  1: 'bg-gray-500/20 text-gray-400',
  2: 'bg-green-500/20 text-green-400',
  3: 'bg-blue-500/20 text-blue-400',
  4: 'bg-purple-500/20 text-purple-400',
  5: 'bg-amber-500/20 text-amber-400',
};

const LEVEL_NAMES: Record<number, string> = {
  1: 'novice', 2: 'beginner', 3: 'intermediate', 4: 'advanced', 5: 'expert',
};

export default function SkillsPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [tab, setTab] = useState<'profiles' | 'catalog' | 'leaderboard'>('profiles');
  const [profiles, setProfiles] = useState<any[]>([]);
  const [catalog, setCatalog] = useState<D | null>(null);
  const [leaderboard, setLeaderboard] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [p, c, l] = await Promise.allSettled([
        superadminApi.getAllSkillProfiles(),
        superadminApi.getSkillCatalog(),
        superadminApi.getSkillLeaderboard(),
      ]);
      if (p.status === 'fulfilled') setProfiles((p.value as D).profiles || []);
      if (c.status === 'fulfilled') setCatalog(c.value as D);
      if (l.status === 'fulfilled') setLeaderboard((l.value as D).leaderboard || []);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const TABS = [
    { id: 'profiles', label: 'Agent Profiles', icon: Users },
    { id: 'catalog', label: 'Skill Catalog', icon: BookOpen },
    { id: 'leaderboard', label: 'Leaderboard', icon: Trophy },
  ] as const;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center">
            <Star className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('skillsPage.title')}</h1>
            <p className="text-xs text-white/40">{t('skillsPage.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1">Total Agents</div>
          <div className="text-2xl font-bold">{profiles.length}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1">Unique Skills</div>
          <div className="text-2xl font-bold text-indigo-400">{catalog?.total_unique_skills || 0}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1">Expert-Level</div>
          <div className="text-2xl font-bold text-amber-400">{profiles.reduce((s: number, p: any) => s + (p.expert_skills || 0), 0)}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1">Total XP</div>
          <div className="text-2xl font-bold text-blue-400">{profiles.reduce((s: number, p: any) => s + (p.total_xp || 0), 0).toLocaleString()}</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white/5 rounded-lg p-1 w-fit">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs transition ${
              tab === t.id ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/60'
            }`}>
            <t.icon className="w-3.5 h-3.5" /> {t.label}
          </button>
        ))}
      </div>

      {/* Agent Profiles Tab */}
      {tab === 'profiles' && (
        <div className="glass rounded-xl border border-white/5 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-white/30 border-b border-white/5">
                <th className="text-left py-3 px-4 font-medium">Agent</th>
                <th className="text-left py-3 px-4 font-medium">Department</th>
                <th className="text-right py-3 px-4 font-medium">Skills</th>
                <th className="text-right py-3 px-4 font-medium">Total XP</th>
                <th className="text-right py-3 px-4 font-medium">Avg Level</th>
                <th className="text-right py-3 px-4 font-medium">Confidence</th>
                <th className="text-right py-3 px-4 font-medium">Expert</th>
                <th className="text-right py-3 px-4 font-medium">Endorsements</th>
              </tr>
            </thead>
            <tbody>
              {profiles.map((p: any) => (
                <tr key={p.agent_id}
                  onClick={() => router.push(`/superadmin/agents/${p.agent_id}`)}
                  className="border-b border-white/5 hover:bg-white/5 cursor-pointer transition">
                  <td className="py-3 px-4">
                    <div className="font-medium">{p.agent_name}</div>
                    <div className="text-[10px] text-white/20">{p.agent_id}</div>
                  </td>
                  <td className="py-3 px-4 text-white/50">{p.department}</td>
                  <td className="py-3 px-4 text-right">{p.total_skills}</td>
                  <td className="py-3 px-4 text-right font-medium text-blue-400">{p.total_xp}</td>
                  <td className="py-3 px-4 text-right">{p.avg_level}</td>
                  <td className="py-3 px-4 text-right text-green-400">{((p.avg_confidence || 0) * 100).toFixed(0)}%</td>
                  <td className="py-3 px-4 text-right text-amber-400">{p.expert_skills}</td>
                  <td className="py-3 px-4 text-right text-purple-400">{p.total_endorsements}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Skill Catalog Tab */}
      {tab === 'catalog' && catalog && (
        <div className="space-y-4">
          {Object.entries(catalog.by_category || {}).map(([cat, skills]: [string, any]) => {
            const CatIcon = CAT_ICONS[cat] || Wrench;
            const catColor = CAT_COLORS[cat] || 'text-white/40';
            return (
              <div key={cat} className="glass rounded-xl p-5 border border-white/5">
                <h3 className="text-sm font-medium mb-3 flex items-center gap-2 capitalize">
                  <CatIcon className={`w-4 h-4 ${catColor}`} /> {cat}
                  <span className="text-[10px] text-white/30 font-normal">({skills.length} skills)</span>
                </h3>
                <div className="grid grid-cols-3 gap-2">
                  {skills.map((skill: any) => (
                    <div key={skill.name} className="flex items-center justify-between p-2.5 rounded-lg bg-white/5">
                      <div>
                        <div className="text-xs font-medium">{skill.name}</div>
                        <div className="text-[10px] text-white/20">{skill.agent_count} agents</div>
                      </div>
                      <div className="text-right">
                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${LEVEL_COLORS[skill.max_level] || ''}`}>
                          {LEVEL_NAMES[skill.max_level] || 'novice'}
                        </span>
                        <div className="text-[10px] text-white/20 mt-0.5">{skill.total_xp} XP</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Leaderboard Tab */}
      {tab === 'leaderboard' && (
        <div className="glass rounded-xl p-5 border border-white/5">
          <div className="space-y-2">
            {leaderboard.map((entry: any, i: number) => (
              <div key={entry.agent_id}
                onClick={() => router.push(`/superadmin/agents/${entry.agent_id}`)}
                className="flex items-center gap-4 p-3 rounded-lg bg-white/5 hover:bg-white/10 cursor-pointer transition">
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold text-sm ${
                  i === 0 ? 'bg-amber-500/20 text-amber-400' :
                  i === 1 ? 'bg-gray-400/20 text-gray-300' :
                  i === 2 ? 'bg-orange-500/20 text-orange-400' :
                  'bg-white/5 text-white/30'
                }`}>
                  {i < 3 ? <Trophy className="w-4 h-4" /> : `#${i + 1}`}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-medium">{entry.agent_name}</div>
                  <div className="text-[10px] text-white/30">{entry.agent_id} · {entry.skill_count} skills · avg lv.{entry.avg_level}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold text-blue-400">{entry.total_xp} XP</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
