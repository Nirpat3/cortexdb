'use client';

import { useState, useEffect, useCallback } from 'react';
import { Award, Shield, RefreshCw, Users, TrendingUp, CheckCircle } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

interface ReputationScore {
  agent_id: string;
  agent_name?: string;
  trust_score: number;
  quality_avg: number;
  completion_rate: number;
  delegation_success_rate: number;
}

function trustColor(score: number) {
  if (score >= 0.7) return 'bg-green-500';
  if (score >= 0.4) return 'bg-yellow-500';
  return 'bg-red-500';
}

function trustText(score: number) {
  if (score >= 0.7) return 'text-green-400';
  if (score >= 0.4) return 'text-yellow-400';
  return 'text-red-400';
}

export default function ReputationPage() {
  const { t } = useTranslation();
  const [scores, setScores] = useState<ReputationScore[]>([]);
  const [delegationMap, setDelegationMap] = useState<Record<string, boolean>>({});
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await superadminApi.getAllReputations() as { scores: ReputationScore[] };
      const sorted = (res.scores || []).sort((a, b) => b.trust_score - a.trust_score);
      setScores(sorted);

      const delegations: Record<string, boolean> = {};
      await Promise.allSettled(
        sorted.map(async (s) => {
          const d = await superadminApi.canDelegate(s.agent_id) as { can_delegate: boolean };
          delegations[s.agent_id] = d.can_delegate;
        })
      );
      setDelegationMap(delegations);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const avgTrust = scores.length ? scores.reduce((s, r) => s + r.trust_score, 0) / scores.length : 0;
  const aboveThreshold = scores.filter(s => s.trust_score >= 0.7).length;
  const delegationEligible = Object.values(delegationMap).filter(Boolean).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-amber-500/20 flex items-center justify-center">
            <Award className="w-5 h-5 text-amber-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('reputation.title')}</h1>
            <p className="text-xs text-white/40">{t('reputation.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1 flex items-center gap-1"><Users className="w-3 h-3" /> Total Agents</div>
          <div className="text-2xl font-bold">{scores.length}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1 flex items-center gap-1"><TrendingUp className="w-3 h-3" /> Avg Trust Score</div>
          <div className={`text-2xl font-bold ${trustText(avgTrust)}`}>{(avgTrust * 100).toFixed(1)}%</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1 flex items-center gap-1"><Shield className="w-3 h-3" /> Above Threshold</div>
          <div className="text-2xl font-bold text-green-400">{aboveThreshold}</div>
        </div>
        <div className="glass rounded-xl p-4 border border-white/5">
          <div className="text-xs text-white/40 mb-1 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Delegation-Eligible</div>
          <div className="text-2xl font-bold text-blue-400">{delegationEligible}</div>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-20">
          <RefreshCw className="w-6 h-6 animate-spin text-white/30" />
        </div>
      )}

      {/* Trust Score Table */}
      {!loading && (
        <div className="glass rounded-xl border border-white/5 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-white/30 border-b border-white/5">
                <th className="text-left py-3 px-4 font-medium">Agent</th>
                <th className="text-left py-3 px-4 font-medium">Trust Score</th>
                <th className="text-right py-3 px-4 font-medium">Quality Avg</th>
                <th className="text-right py-3 px-4 font-medium">Completion Rate</th>
                <th className="text-right py-3 px-4 font-medium">Delegation Rate</th>
                <th className="text-center py-3 px-4 font-medium">Can Delegate</th>
              </tr>
            </thead>
            <tbody>
              {scores.map((s) => (
                <tr key={s.agent_id} className="border-b border-white/5 hover:bg-white/5 transition">
                  <td className="py-3 px-4">
                    <div className="font-medium">{s.agent_name || s.agent_id}</div>
                    {s.agent_name && <div className="text-[10px] text-white/20">{s.agent_id}</div>}
                  </td>
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 bg-white/5 rounded-full overflow-hidden max-w-[120px]">
                        <div className={`h-full rounded-full ${trustColor(s.trust_score)}`}
                          style={{ width: `${Math.min(s.trust_score * 100, 100)}%` }} />
                      </div>
                      <span className={`font-medium ${trustText(s.trust_score)}`}>
                        {(s.trust_score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right text-purple-400">{(s.quality_avg * 100).toFixed(1)}%</td>
                  <td className="py-3 px-4 text-right text-cyan-400">{(s.completion_rate * 100).toFixed(1)}%</td>
                  <td className="py-3 px-4 text-right text-amber-400">{(s.delegation_success_rate * 100).toFixed(1)}%</td>
                  <td className="py-3 px-4 text-center">
                    {delegationMap[s.agent_id] !== undefined ? (
                      delegationMap[s.agent_id] ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px]">
                          <CheckCircle className="w-3 h-3" /> Yes
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-red-500/20 text-red-400 text-[10px]">
                          No
                        </span>
                      )
                    ) : (
                      <span className="text-white/20">--</span>
                    )}
                  </td>
                </tr>
              ))}
              {scores.length === 0 && (
                <tr><td colSpan={6} className="py-12 text-center text-white/30">{t('common.noData')}</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
