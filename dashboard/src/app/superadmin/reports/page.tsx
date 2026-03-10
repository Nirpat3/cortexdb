'use client';

import { useState, useEffect } from 'react';
import { FileText, Download, Clock, BarChart3, Users, DollarSign, GitBranch } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const REPORT_DESCRIPTIONS: Record<string, { label: string; desc: string; icon: any }> = {
  agent_actions: { label: 'Agent Actions', desc: 'Task executions, delegations, state changes', icon: Users },
  cost_summary: { label: 'Cost Summary', desc: 'Spending breakdown by provider/agent/department', icon: DollarSign },
  quality_audit: { label: 'Quality Audit', desc: 'Outcome grades, failure analysis, quality trends', icon: BarChart3 },
  delegation_audit: { label: 'Delegation Audit', desc: 'Delegation decisions and outcomes', icon: GitBranch },
};

function fmtDate(ts: number) {
  return new Date(ts * 1000).toLocaleString();
}

export default function ReportsPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'generate' | 'history'>('generate');
  const [reportTypes, setReportTypes] = useState<string[]>([]);
  const [selectedType, setSelectedType] = useState('');
  const [generating, setGenerating] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [reports, setReports] = useState<any[]>([]);
  const [viewReport, setViewReport] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      superadminApi.getReportTypes().then((r: any) => setReportTypes(r.types || [])),
      superadminApi.listReports().then((r: any) => setReports(r.reports || [])),
    ]).finally(() => setLoading(false));
  }, []);

  const generate = async () => {
    if (!selectedType) return;
    setGenerating(true);
    setReport(null);
    try {
      const r = await superadminApi.generateReport(selectedType);
      setReport(r);
      const updated = await superadminApi.listReports();
      setReports((updated as any).reports || []);
    } catch {}
    setGenerating(false);
  };

  const viewDetail = async (reportId: string) => {
    try {
      const r = await superadminApi.getReport(reportId);
      setViewReport(r);
    } catch {}
  };

  const renderData = (data: any) => {
    if (!data) return null;
    return (
      <div className="space-y-3">
        {Object.entries(data).map(([k, v]) => (
          <div key={k} className="bg-white/5 rounded-lg p-3">
            <div className="text-xs text-white/40 mb-1">{k}</div>
            {typeof v === 'object' && v !== null ? (
              Array.isArray(v) ? (
                <div className="text-xs text-white/60">{v.length} items</div>
              ) : (
                <div className="grid grid-cols-2 gap-1">
                  {Object.entries(v as any).map(([sk, sv]) => (
                    <div key={sk} className="flex justify-between text-xs">
                      <span className="text-white/50">{sk}</span>
                      <span className="text-white/80 font-mono">{String(sv)}</span>
                    </div>
                  ))}
                </div>
              )
            ) : (
              <div className="text-sm font-mono text-white/90">{String(v)}</div>
            )}
          </div>
        ))}
      </div>
    );
  };

  if (loading) return <div className="text-white/40 p-8">{t('common.loading')}</div>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-purple-500/20 flex items-center justify-center">
          <FileText className="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h1 className="text-xl font-bold">{t('reports.title')}</h1>
          <p className="text-xs text-white/40">{t('reports.subtitle')}</p>
        </div>
      </div>

      <div className="flex gap-2">
        {(['generate', 'history'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 rounded-lg text-sm transition ${tab === t ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'}`}>
            {t === 'generate' ? 'Generate Report' : 'Report History'}
          </button>
        ))}
      </div>

      {tab === 'generate' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {reportTypes.map(type => {
              const info = REPORT_DESCRIPTIONS[type] || { label: type, desc: '', icon: FileText };
              const Icon = info.icon;
              return (
                <button key={type} onClick={() => setSelectedType(type)}
                  className={`p-4 rounded-xl border text-left transition ${
                    selectedType === type
                      ? 'bg-purple-500/20 border-purple-500/40'
                      : 'bg-white/5 border-white/10 hover:bg-white/10'
                  }`}>
                  <Icon className="w-5 h-5 mb-2 text-purple-400" />
                  <div className="text-sm font-medium">{info.label}</div>
                  <div className="text-[10px] text-white/40 mt-1">{info.desc}</div>
                </button>
              );
            })}
          </div>

          <button onClick={generate} disabled={!selectedType || generating}
            className="px-6 py-2 rounded-lg bg-purple-500/20 text-purple-300 hover:bg-purple-500/30 transition text-sm disabled:opacity-40">
            {generating ? 'Generating...' : 'Generate Report'}
          </button>

          {report && (
            <div className="bg-white/5 border border-white/10 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-bold">{report.report_type}</div>
                  <div className="text-xs text-white/40">ID: {report.report_id} | Generated: {fmtDate(report.generated_at)}</div>
                </div>
                <Download className="w-4 h-4 text-white/30" />
              </div>
              {renderData(report.data)}
            </div>
          )}
        </div>
      )}

      {tab === 'history' && (
        <div className="space-y-3">
          {reports.length === 0 && <div className="text-white/30 text-sm">{t('common.noData')}</div>}
          {[...reports].reverse().map((r: any) => (
            <div key={r.report_id} className="bg-white/5 border border-white/10 rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{r.report_type}</div>
                <div className="text-xs text-white/40 flex items-center gap-2">
                  <Clock className="w-3 h-3" /> {fmtDate(r.generated_at)}
                  <span>|</span> {r.report_id}
                </div>
              </div>
              <button onClick={() => viewDetail(r.report_id)}
                className="text-xs px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 transition">
                View
              </button>
            </div>
          ))}

          {viewReport && (
            <div className="bg-white/5 border border-purple-500/20 rounded-xl p-5 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm font-bold">{viewReport.report_type} — {viewReport.report_id}</div>
                <button onClick={() => setViewReport(null)} className="text-xs text-white/40 hover:text-white/60">Close</button>
              </div>
              {renderData(viewReport.data)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
