'use client';

import { useEffect, useState, useCallback } from 'react';
import { Network, ChevronDown, ChevronRight, Bot, Users } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const DEPT_COLORS: Record<string, string> = {
  EXEC: '#EF4444', ENG: '#3B82F6', QA: '#34D399', OPS: '#F59E0B', SEC: '#EC4899', DOC: '#8B5CF6',
};

const TIER_LABELS: Record<string, string> = {
  CHIEF: 'Chief', LEAD: 'Lead', SR: 'Senior', AGT: 'Agent',
};

function OrgNode({ node, depth = 0 }: { node: D; depth?: number }) {
  const [open, setOpen] = useState(depth < 2);
  const color = DEPT_COLORS[node.department] ?? '#6366F1';
  const hasChildren = node.children?.length > 0;

  return (
    <div className={depth > 0 ? 'ml-6 border-l border-white/5 pl-4' : ''}>
      <div
        className="glass rounded-xl p-3 mb-2 cursor-pointer hover:bg-white/[0.03] transition flex items-center gap-3"
        onClick={() => hasChildren && setOpen(!open)}
      >
        <div className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0" style={{ backgroundColor: `${color}20` }}>
          <Bot className="w-4 h-4" style={{ color }} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{node.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ backgroundColor: `${color}20`, color }}>
              {TIER_LABELS[node.tier] ?? node.tier}
            </span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
              node.state === 'active' ? 'bg-emerald-500/20 text-emerald-300' :
              node.state === 'working' ? 'bg-blue-500/20 text-blue-300' : 'bg-white/10 text-white/40'
            }`}>{node.state}</span>
          </div>
          <div className="text-xs text-white/40">{node.title}</div>
          <div className="text-[10px] text-white/20 font-mono">{node.agent_id} · {node.llm_provider}:{node.llm_model}</div>
        </div>
        {hasChildren && (
          open ? <ChevronDown className="w-4 h-4 text-white/30 shrink-0" /> : <ChevronRight className="w-4 h-4 text-white/30 shrink-0" />
        )}
      </div>
      {open && node.children?.map((child: D) => (
        <OrgNode key={child.agent_id} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

export default function OrgChartPage() {
  const { t } = useTranslation();
  const [chart, setChart] = useState<D | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.getOrgChart();
      setChart(data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const root = (chart as D)?.root ?? [];
  const depts = (chart as D)?.departments ?? {};

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
          <Network className="w-6 h-6 text-cyan-400" /> {t('orgChart.title')}
        </h1>
        <p className="text-sm text-white/40">
          {t('orgChart.subtitle')}
        </p>
      </div>

      {/* Department Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mb-8">
        {Object.entries(depts).map(([dept, data]) => {
          const d = data as D;
          const color = DEPT_COLORS[dept] ?? '#6366F1';
          return (
            <div key={dept} className="glass rounded-xl p-3">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-6 h-6 rounded flex items-center justify-center" style={{ backgroundColor: `${color}20` }}>
                  <Users className="w-3 h-3" style={{ color }} />
                </div>
                <span className="text-sm font-medium">{dept}</span>
              </div>
              <div className="text-lg font-bold">{d.agent_count}</div>
              <div className="text-[10px] text-white/30">agents</div>
            </div>
          );
        })}
      </div>

      {/* Naming Convention */}
      <div className="glass rounded-xl p-4 mb-8">
        <h3 className="text-sm font-semibold mb-2">Agent Naming Standard</h3>
        <div className="text-xs text-white/50 font-mono mb-2">CDB-{'{DEPT}'}-{'{ROLE}'}-{'{SEQ}'}</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[10px] text-white/30">
          <div><span className="text-white/50">CDB</span> = CortexDB prefix</div>
          <div><span className="text-white/50">DEPT</span> = EXEC, ENG, QA, OPS, SEC, DOC</div>
          <div><span className="text-white/50">ROLE</span> = CHIEF, LEAD, SR, AGT + specialty</div>
          <div><span className="text-white/50">SEQ</span> = 3-digit sequence number</div>
        </div>
      </div>

      {/* Hierarchical Tree */}
      <h2 className="text-lg font-semibold mb-4">Hierarchy</h2>
      <div className="space-y-1">
        {root.map((node: D) => (
          <OrgNode key={node.agent_id} node={node} />
        ))}
      </div>
    </div>
  );
}
