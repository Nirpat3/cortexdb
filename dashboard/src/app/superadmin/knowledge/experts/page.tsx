'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  Users,
  Search,
  ArrowLeft,
  Award,
  Brain,
  BarChart3,
  Target,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

export default function ExpertDiscoveryPage() {
  const { t } = useTranslation();
  const router = useRouter();

  // Search state
  const [query, setQuery] = useState('');
  const [domain, setDomain] = useState('');
  const [results, setResults] = useState<D[]>([]);
  const [searching, setSearching] = useState(false);

  // Task recommendation state
  const [taskDescription, setTaskDescription] = useState('');
  const [taskRecommendations, setTaskRecommendations] = useState<D[]>([]);
  const [recommending, setRecommending] = useState(false);

  // Expertise matrix state
  const [matrix, setMatrix] = useState<D | null>(null);
  const [matrixFilter, setMatrixFilter] = useState('');
  const [loadingMatrix, setLoadingMatrix] = useState(false);

  // Domain map state
  const [domainMap, setDomainMap] = useState<D[]>([]);
  const [loadingDomainMap, setLoadingDomainMap] = useState(false);

  const domains = [
    '',
    'operations',
    'engineering',
    'security',
    'analytics',
    'research',
    'communications',
  ];

  async function handleSearch() {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await superadminApi.findExpert(query, domain || undefined, 10);
      const r = res as D;
      setResults(Array.isArray(r) ? r : (r?.results ?? r?.data ?? []) as D[]);
    } catch (err) {
      console.error('Expert search failed:', err);
      setResults([]);
    } finally {
      setSearching(false);
    }
  }

  async function handleRecommend() {
    if (!taskDescription.trim()) return;
    setRecommending(true);
    try {
      const res = await superadminApi.recommendExpertForTask(taskDescription);
      const r = res as D;
      setTaskRecommendations(
        (Array.isArray(r) ? r : (r?.recommendations ?? r?.data ?? [])) as D[]
      );
    } catch (err) {
      console.error('Task recommendation failed:', err);
      setTaskRecommendations([]);
    } finally {
      setRecommending(false);
    }
  }

  async function loadMatrix() {
    setLoadingMatrix(true);
    try {
      const res = await superadminApi.getExpertiseMatrix();
      setMatrix(res);
    } catch (err) {
      console.error('Failed to load expertise matrix:', err);
    } finally {
      setLoadingMatrix(false);
    }
  }

  async function loadDomainMap() {
    setLoadingDomainMap(true);
    try {
      const res = await superadminApi.getDomainMap();
      const r = res as D;
      setDomainMap((Array.isArray(r) ? r : (r?.domains ?? r?.data ?? [])) as D[]);
    } catch (err) {
      console.error('Failed to load domain map:', err);
    } finally {
      setLoadingDomainMap(false);
    }
  }

  useEffect(() => {
    loadMatrix();
    loadDomainMap();
  }, []);

  function scoreColor(score: number): string {
    if (score > 0.7) return 'bg-emerald-500';
    if (score > 0.4) return 'bg-amber-500';
    return 'bg-red-500';
  }

  function proficiencyColor(level: number): string {
    const opacity = Math.min(level / 5, 1);
    if (level >= 4) return `bg-emerald-500/${Math.round(opacity * 100)}`;
    if (level >= 3) return `bg-blue-500/${Math.round(opacity * 100)}`;
    if (level >= 2) return `bg-amber-500/${Math.round(opacity * 100)}`;
    return `bg-white/${Math.round(opacity * 40)}`;
  }

  function proficiencyBg(level: number): React.CSSProperties {
    if (level >= 4) return { backgroundColor: `rgba(16,185,129,${level / 5})` };
    if (level >= 3) return { backgroundColor: `rgba(59,130,246,${level / 5})` };
    if (level >= 2) return { backgroundColor: `rgba(245,158,11,${level / 5})` };
    return { backgroundColor: `rgba(255,255,255,${level / 10})` };
  }

  const matrixAgents: D[] = matrix?.agents ?? [];
  const matrixSkills: string[] = matrix?.skills ?? matrix?.categories ?? [];
  const filteredMatrixAgents = matrixFilter
    ? matrixAgents.filter(
        (a: D) =>
          (a.department ?? '').toLowerCase() === matrixFilter.toLowerCase()
      )
    : matrixAgents;

  return (
    <div className="min-h-screen bg-black text-white p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => router.push('/superadmin/knowledge')}
          className="p-2 rounded-xl bg-white/5 border border-white/10 hover:bg-white/10 transition"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex items-center gap-3">
          <Users className="w-6 h-6 text-purple-400" />
          <h1 className="text-2xl font-bold">{t('knowledge.experts.title')}</h1>
        </div>
      </div>

      {/* Search Section */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Search className="w-5 h-5 text-purple-400" />
          Find Experts
        </h2>
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            placeholder="Search by skill, topic, or keyword..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-purple-500/50 focus:outline-none"
          />
          <select
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            className="w-full sm:w-48 bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-purple-500/50 focus:outline-none"
          >
            <option value="">{t('common.all')} Domains</option>
            {domains
              .filter((d) => d)
              .map((d) => (
                <option key={d} value={d}>
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </option>
              ))}
          </select>
          <button
            onClick={handleSearch}
            disabled={searching || !query.trim()}
            className="px-6 py-2.5 rounded-xl bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 text-sm font-medium transition disabled:opacity-50 whitespace-nowrap"
          >
            {searching ? `${t('common.search')}...` : 'Find Expert'}
          </button>
        </div>
      </div>

      {/* Results Section */}
      {results.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Award className="w-5 h-5 text-purple-400" />
            Search Results ({results.length})
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {results.map((expert: D, idx: number) => {
              const compositeScore: number =
                expert.composite_score ?? expert.score ?? 0;
              const skills: string[] =
                expert.skills_matched ?? expert.skills ?? [];
              return (
                <div
                  key={expert.agent_id ?? idx}
                  className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-3"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-semibold text-sm">
                        {expert.name ?? expert.agent_name ?? 'Unknown'}
                      </p>
                      <p className="text-xs text-white/50 font-mono">
                        {expert.agent_id ?? '—'}
                      </p>
                    </div>
                    {expert.department && (
                      <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-500/20 text-purple-300">
                        {expert.department}
                      </span>
                    )}
                  </div>

                  {/* Composite Score */}
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-white/60">Composite Score</span>
                      <span className="font-medium">
                        {(compositeScore * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${scoreColor(compositeScore)}`}
                        style={{ width: `${compositeScore * 100}%` }}
                      />
                    </div>
                  </div>

                  {/* Skills Matched */}
                  {skills.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {skills.map((skill: string, sIdx: number) => (
                        <span
                          key={sIdx}
                          className="px-2 py-0.5 rounded-full text-[10px] bg-blue-500/20 text-blue-300"
                        >
                          {skill}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Stats */}
                  <div className="flex items-center gap-4 text-xs text-white/50">
                    {expert.knowledge_count != null && (
                      <span>
                        Knowledge: {expert.knowledge_count}
                      </span>
                    )}
                    {expert.trust_score != null && (
                      <span>
                        Trust: {(expert.trust_score * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Task Recommendation Section */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Target className="w-5 h-5 text-purple-400" />
          Task Recommendation
        </h2>
        <textarea
          placeholder="Describe the task to find the best expert..."
          value={taskDescription}
          onChange={(e) => setTaskDescription(e.target.value)}
          rows={3}
          className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-purple-500/50 focus:outline-none resize-none"
        />
        <button
          onClick={handleRecommend}
          disabled={recommending || !taskDescription.trim()}
          className="px-6 py-2.5 rounded-xl bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 text-sm font-medium transition disabled:opacity-50"
        >
          {recommending ? 'Finding...' : 'Recommend Expert'}
        </button>

        {taskRecommendations.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
            {taskRecommendations.map((rec: D, idx: number) => (
              <div
                key={rec.agent_id ?? idx}
                className="bg-white/5 border border-white/10 rounded-2xl p-5 flex items-center gap-4"
              >
                <div className="flex-1">
                  <p className="font-semibold text-sm">
                    {rec.name ?? rec.agent_name ?? 'Unknown'}
                  </p>
                  <p className="text-xs text-white/50 font-mono">
                    {rec.agent_id ?? '—'}
                  </p>
                  {rec.reason && (
                    <p className="text-xs text-white/40 mt-1">{rec.reason}</p>
                  )}
                </div>
                {rec.score != null && (
                  <div className="text-right">
                    <p className="text-lg font-bold">
                      {(rec.score * 100).toFixed(0)}%
                    </p>
                    <p className="text-[10px] text-white/40">match</p>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Expertise Matrix Section */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-purple-400" />
            Expertise Matrix
          </h2>
          <select
            value={matrixFilter}
            onChange={(e) => setMatrixFilter(e.target.value)}
            className="bg-white/5 border border-white/10 rounded-xl px-3 py-1.5 text-xs focus:border-purple-500/50 focus:outline-none"
          >
            <option value="">{t('common.all')} Departments</option>
            {domains
              .filter((d) => d)
              .map((d) => (
                <option key={d} value={d}>
                  {d.charAt(0).toUpperCase() + d.slice(1)}
                </option>
              ))}
          </select>
        </div>

        {loadingMatrix ? (
          <p className="text-sm text-white/40">{t('common.loading')}</p>
        ) : matrix && matrixSkills.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr>
                  <th className="text-left py-2 px-2 text-white/50 font-medium">
                    Agent
                  </th>
                  {matrixSkills.map((skill: string) => (
                    <th
                      key={skill}
                      className="py-2 px-1 text-white/50 font-medium text-center"
                    >
                      <span className="writing-mode-vertical inline-block max-w-[80px] truncate">
                        {skill}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredMatrixAgents.map((agent: D, aIdx: number) => {
                  const proficiencies: Record<string, number> =
                    agent.proficiencies ?? agent.skills ?? {};
                  return (
                    <tr
                      key={agent.agent_id ?? aIdx}
                      className="border-t border-white/5"
                    >
                      <td className="py-2 px-2 whitespace-nowrap">
                        <span className="font-medium">
                          {agent.name ?? agent.agent_id ?? '—'}
                        </span>
                      </td>
                      {matrixSkills.map((skill: string) => {
                        const level: number = proficiencies[skill] ?? 0;
                        return (
                          <td key={skill} className="py-1 px-1 text-center">
                            <div
                              className="w-8 h-8 rounded flex items-center justify-center text-xs mx-auto"
                              style={proficiencyBg(level)}
                            >
                              {level > 0 ? level : ''}
                            </div>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-white/40">{t('common.noData')}</p>
        )}
      </div>

      {/* Domain Map Section */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5 space-y-4">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <Brain className="w-5 h-5 text-purple-400" />
          Domain Map
        </h2>

        {loadingDomainMap ? (
          <p className="text-sm text-white/40">{t('common.loading')}</p>
        ) : domainMap.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {domainMap.map((entry: D, idx: number) => (
              <div
                key={entry.topic ?? idx}
                className="bg-white/5 border border-white/10 rounded-2xl p-5"
              >
                <p className="font-semibold text-sm mb-2">
                  {entry.topic ?? entry.domain ?? 'Unknown Topic'}
                </p>
                <div className="space-y-1.5">
                  {(entry.agents ?? entry.top_agents ?? []).map(
                    (agent: D | string, aIdx: number) => {
                      const agentName =
                        typeof agent === 'string'
                          ? agent
                          : agent.name ?? agent.agent_id ?? '—';
                      const agentScore =
                        typeof agent === 'object' ? agent.score : null;
                      return (
                        <div
                          key={aIdx}
                          className="flex items-center justify-between text-xs"
                        >
                          <span className="text-white/70">{agentName}</span>
                          {agentScore != null && (
                            <span className="text-white/40">
                              {(agentScore * 100).toFixed(0)}%
                            </span>
                          )}
                        </div>
                      );
                    }
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-white/40">{t('common.noData')}</p>
        )}
      </div>
    </div>
  );
}
