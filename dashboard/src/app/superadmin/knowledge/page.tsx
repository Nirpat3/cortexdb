'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Share2, Brain, Users, TrendingUp, Search, RefreshCw, Layers } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, any>;

export default function KnowledgeNetworkPage() {
  const { t } = useTranslation();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [knowledgeStats, setKnowledgeStats] = useState<D>({});
  const [propagationStats, setPropagationStats] = useState<D>({});
  const [knowledgeNodes, setKnowledgeNodes] = useState<D[]>([]);
  const [contextPools, setContextPools] = useState<D[]>([]);
  const [propagating, setPropagating] = useState(false);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [stats, propStats, nodes, pools] = await Promise.all([
        superadminApi.getKnowledgeStats().catch(() => ({})),
        superadminApi.getPropagationStats().catch(() => ({})),
        superadminApi.getKnowledgeNodes({ limit: 20 }).catch(() => []),
        superadminApi.listContextPools().catch(() => []),
      ]);
      setKnowledgeStats(stats || {});
      setPropagationStats(propStats || {});
      setKnowledgeNodes(Array.isArray(nodes) ? nodes : []);
      setContextPools(Array.isArray(pools) ? pools : []);
    } catch {
      // handled per-call above
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleAutoPropagate = async () => {
    setPropagating(true);
    try {
      await superadminApi.autoPropagateHighGrade();
      await fetchData();
    } catch {
      // silent
    } finally {
      setPropagating(false);
    }
  };

  const acceptanceRate =
    propagationStats.total_propagations && propagationStats.total_propagations > 0
      ? ((propagationStats.accepted ?? 0) / propagationStats.total_propagations * 100).toFixed(1)
      : '—';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
            <Share2 className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">{t('knowledge.title')}</h1>
            <p className="text-sm text-white/40">{t('knowledge.subtitle')}</p>
          </div>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          {t('common.refresh')}
        </button>
      </div>

      {/* KPI Cards Row */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold">{knowledgeStats.total_nodes ?? '—'}</div>
              <div className="text-xs text-white/40 mt-1">Total Nodes</div>
            </div>
            <div className="w-10 h-10 rounded-xl bg-blue-500/20 flex items-center justify-center">
              <Brain className="w-5 h-5 text-blue-400" />
            </div>
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold">{knowledgeStats.total_edges ?? '—'}</div>
              <div className="text-xs text-white/40 mt-1">Total Edges</div>
            </div>
            <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
              <Share2 className="w-5 h-5 text-purple-400" />
            </div>
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold">{knowledgeStats.topics ?? '—'}</div>
              <div className="text-xs text-white/40 mt-1">Topics</div>
            </div>
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 flex items-center justify-center">
              <Layers className="w-5 h-5 text-cyan-400" />
            </div>
          </div>
        </div>

        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-2xl font-bold">
                {knowledgeStats.avg_confidence != null
                  ? `${(knowledgeStats.avg_confidence * 100).toFixed(1)}%`
                  : '—'}
              </div>
              <div className="text-xs text-white/40 mt-1">Avg Confidence</div>
            </div>
            <div className="w-10 h-10 rounded-xl bg-green-500/20 flex items-center justify-center">
              <TrendingUp className="w-5 h-5 text-green-400" />
            </div>
          </div>
        </div>
      </div>

      {/* Propagation Stats Row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="text-2xl font-bold">{propagationStats.total_propagations ?? '—'}</div>
          <div className="text-xs text-white/40 mt-1">Total Propagations</div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="text-2xl font-bold">{propagationStats.accepted ?? '—'}</div>
          <div className="text-xs text-white/40 mt-1">Accepted</div>
        </div>
        <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
          <div className="text-2xl font-bold">{acceptanceRate !== '—' ? `${acceptanceRate}%` : '—'}</div>
          <div className="text-xs text-white/40 mt-1">Acceptance Rate</div>
        </div>
      </div>

      {/* Recent Knowledge Nodes */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
        <h2 className="text-lg font-semibold mb-4">Recent Knowledge Nodes</h2>
        {knowledgeNodes.length === 0 ? (
          <p className="text-sm text-white/40">{t('common.noData')}</p>
        ) : (
          <div className="space-y-0">
            {knowledgeNodes.map((node: D, i: number) => (
              <div key={node.id ?? i} className="border-b border-white/5 py-3 flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium truncate">{node.topic ?? '—'}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] ${
                        node.node_type === 'fact'
                          ? 'bg-blue-500/20 text-blue-300'
                          : node.node_type === 'skill'
                            ? 'bg-green-500/20 text-green-300'
                            : node.node_type === 'procedure'
                              ? 'bg-orange-500/20 text-orange-300'
                              : 'bg-purple-500/20 text-purple-300'
                      }`}
                    >
                      {node.node_type ?? 'unknown'}
                    </span>
                  </div>
                  <p className="text-xs text-white/40 truncate">{node.content ?? '—'}</p>
                  <p className="text-xs text-white/30 mt-0.5">Source: {node.source_agent ?? '—'}</p>
                </div>
                <div className="w-24 flex-shrink-0">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                      <div
                        className="h-full rounded-full bg-emerald-400"
                        style={{ width: `${(node.confidence ?? 0) * 100}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-white/40 w-8 text-right">
                      {node.confidence != null ? `${(node.confidence * 100).toFixed(0)}%` : '—'}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Context Pools */}
      <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
        <h2 className="text-lg font-semibold mb-4">Context Pools</h2>
        {contextPools.length === 0 ? (
          <p className="text-sm text-white/40">{t('common.noData')}</p>
        ) : (
          <div className="grid grid-cols-3 gap-3">
            {contextPools.map((pool: D, i: number) => (
              <div
                key={pool.id ?? i}
                className="bg-white/5 border border-white/10 rounded-2xl p-5 flex items-center gap-3"
              >
                <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center">
                  <Users className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <div className="text-sm font-medium">{pool.department ?? pool.name ?? '—'}</div>
                  <div className="text-xs text-white/40 mt-1">
                    {pool.contributor_count ?? pool.contributors ?? 0} contributors
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Quick Actions */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.push('/superadmin/knowledge/graph')}
          className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition flex items-center gap-2"
        >
          <Search className="w-4 h-4" />
          {t('common.search')} Knowledge
        </button>
        <button
          onClick={() => router.push('/superadmin/knowledge/experts')}
          className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition flex items-center gap-2"
        >
          <Users className="w-4 h-4" />
          Find Expert
        </button>
        <button
          onClick={handleAutoPropagate}
          disabled={propagating}
          className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition flex items-center gap-2"
        >
          <RefreshCw className={`w-4 h-4 ${propagating ? 'animate-spin' : ''}`} />
          Auto-Propagate
        </button>
      </div>
    </div>
  );
}
