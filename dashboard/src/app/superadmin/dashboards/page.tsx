'use client';

import { useEffect, useState, useCallback } from 'react';
import { LayoutDashboard, RefreshCw, Plus, Share2, Copy, Trash2, Pencil, X } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const WIDGET_TYPES = ['counter', 'line_chart', 'bar_chart', 'pie_chart', 'gauge', 'table', 'list', 'heatmap', 'text', 'status_grid'];
const WIDGET_COLORS: Record<string, string> = {
  counter: 'bg-cyan-500/30', line_chart: 'bg-blue-500/30', bar_chart: 'bg-purple-500/30',
  pie_chart: 'bg-amber-500/30', gauge: 'bg-emerald-500/30', table: 'bg-white/10',
  list: 'bg-indigo-500/30', heatmap: 'bg-red-500/30', text: 'bg-white/5', status_grid: 'bg-teal-500/30',
};
const DATA_SOURCES = ['agents_table', 'tasks_table', 'cost_metrics', 'health_checks', 'neural_signals', 'pipeline_runs', 'custom_query'];

const MOCK_DASHBOARDS: D[] = [
  { id: 'db-1', name: 'Operations Overview', description: 'Real-time ops metrics', widget_count: 6, owner: 'admin', shared: true, updated: '2026-03-08T08:00:00Z', widgets: [
    { id: 'w1', title: 'Active Agents', type: 'counter', col: 0, row: 0, w: 1, h: 1, source: 'agents_table' },
    { id: 'w2', title: 'Task Throughput', type: 'line_chart', col: 1, row: 0, w: 2, h: 1, source: 'tasks_table' },
    { id: 'w3', title: 'Cost Breakdown', type: 'pie_chart', col: 0, row: 1, w: 1, h: 1, source: 'cost_metrics' },
    { id: 'w4', title: 'System Health', type: 'status_grid', col: 1, row: 1, w: 1, h: 1, source: 'health_checks' },
    { id: 'w5', title: 'Error Rate', type: 'gauge', col: 2, row: 1, w: 1, h: 1, source: 'health_checks' },
    { id: 'w6', title: 'Recent Events', type: 'list', col: 0, row: 2, w: 3, h: 1, source: 'neural_signals' },
  ]},
  { id: 'db-2', name: 'Cost Analytics', description: 'Budget and spending analysis', widget_count: 4, owner: 'admin', shared: false, updated: '2026-03-07T14:00:00Z', widgets: [
    { id: 'w1', title: 'Monthly Spend', type: 'counter', col: 0, row: 0, w: 1, h: 1, source: 'cost_metrics' },
    { id: 'w2', title: 'Spend Trend', type: 'bar_chart', col: 1, row: 0, w: 2, h: 1, source: 'cost_metrics' },
    { id: 'w3', title: 'Department Costs', type: 'table', col: 0, row: 1, w: 2, h: 1, source: 'cost_metrics' },
    { id: 'w4', title: 'Budget Usage', type: 'heatmap', col: 2, row: 1, w: 1, h: 1, source: 'cost_metrics' },
  ]},
  { id: 'db-3', name: 'Agent Performance', description: 'Agent KPIs and metrics', widget_count: 3, owner: 'manager', shared: true, updated: '2026-03-06T10:00:00Z', widgets: [] },
];

export default function CustomDashboardsPage() {
  const { t } = useTranslation();
  const [dashboards, setDashboards] = useState<D[]>(MOCK_DASHBOARDS);
  const [selected, setSelected] = useState<string | null>(null);
  const [editMode, setEditMode] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [addingWidget, setAddingWidget] = useState(false);
  const [widgetTitle, setWidgetTitle] = useState('');
  const [widgetType, setWidgetType] = useState('counter');
  const [widgetSource, setWidgetSource] = useState('agents_table');

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.customDashboardList() as D;
      if ((data as D).dashboards) setDashboards((data as D).dashboards as D[]);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const current = dashboards.find(d => d.id === selected);
  const stats = { total: dashboards.length, widgets: dashboards.reduce((s, d) => s + ((d.widget_count as number) || 0), 0), public: dashboards.filter(d => d.shared).length, shared: dashboards.filter(d => d.shared).length };

  const handleCreate = () => {
    if (!newName) return;
    setDashboards(prev => [...prev, { id: `db-${Date.now()}`, name: newName, description: newDesc, widget_count: 0, owner: 'admin', shared: false, updated: new Date().toISOString(), widgets: [] }]);
    setNewName(''); setNewDesc(''); setShowCreate(false);
  };

  const addWidget = () => {
    if (!widgetTitle || !current) return;
    const widgets = (current.widgets as D[]) || [];
    const w: D = { id: `w-${Date.now()}`, title: widgetTitle, type: widgetType, col: widgets.length % 3, row: Math.floor(widgets.length / 3), w: 1, h: 1, source: widgetSource };
    setDashboards(prev => prev.map(d => d.id === selected ? { ...d, widgets: [...widgets, w], widget_count: widgets.length + 1 } : d));
    setWidgetTitle(''); setAddingWidget(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <LayoutDashboard className="w-6 h-6 text-purple-400" /> Custom Dashboards
          </h1>
          <p className="text-sm text-white/40">Dashboard builder with widget management</p>
        </div>
        <div className="flex gap-2">
          {selected && <button onClick={() => { setSelected(null); setEditMode(false); }} className="glass px-3 py-2 rounded-lg text-xs text-white/60"><X className="w-3.5 h-3.5" /></button>}
          <button onClick={() => setShowCreate(!showCreate)} className="glass px-3 py-2 rounded-lg text-xs text-purple-400 flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Create Dashboard</button>
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        {[['Total Dashboards', stats.total, ''], ['Widgets', stats.widgets, 'text-purple-400'], ['Public', stats.public, 'text-emerald-400'], ['Shared', stats.shared, 'text-blue-400']].map(([l, v, c]) => (
          <div key={l as string} className="glass rounded-xl p-3">
            <div className="text-xs text-white/40">{l as string}</div>
            <div className={`text-2xl font-bold ${c}`}>{v as string}</div>
          </div>
        ))}
      </div>

      {showCreate && (
        <div className="glass-heavy rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold mb-3">New Dashboard</h3>
          <div className="flex gap-3">
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Dashboard name" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <input value={newDesc} onChange={e => setNewDesc(e.target.value)} placeholder="Description" className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
            <button onClick={handleCreate} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Create</button>
          </div>
        </div>
      )}

      {!selected ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {dashboards.map(d => (
            <div key={d.id as string} className="glass rounded-xl p-4 cursor-pointer hover:bg-white/5 transition" onClick={() => setSelected(d.id as string)}>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-sm font-semibold">{d.name as string}</h3>
                {d.shared ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-500/20 text-blue-300">Shared</span> : null}
              </div>
              <p className="text-xs text-white/40 mb-3">{d.description as string}</p>
              <div className="flex items-center justify-between text-[10px] text-white/30">
                <span>{d.widget_count as number} widgets</span>
                <span>{d.owner as string}</span>
                <span>{new Date(d.updated as string).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      ) : current && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">{current.name as string}</h2>
            <div className="flex gap-2">
              <button onClick={() => setEditMode(!editMode)} className={`glass px-3 py-1.5 rounded-lg text-xs flex items-center gap-1 ${editMode ? 'text-amber-400' : 'text-white/60'}`}><Pencil className="w-3 h-3" /> {editMode ? 'Editing' : 'Edit'}</button>
              <button className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 flex items-center gap-1"><Share2 className="w-3 h-3" /> Share</button>
              <button className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 flex items-center gap-1"><Copy className="w-3 h-3" /> Duplicate</button>
              <button className="glass px-3 py-1.5 rounded-lg text-xs text-red-400 flex items-center gap-1"><Trash2 className="w-3 h-3" /> Delete</button>
              {editMode && <button onClick={() => setAddingWidget(!addingWidget)} className="glass px-3 py-1.5 rounded-lg text-xs text-cyan-400 flex items-center gap-1"><Plus className="w-3 h-3" /> Add Widget</button>}
            </div>
          </div>
          {addingWidget && (
            <div className="glass-heavy rounded-xl p-4 mb-4">
              <div className="flex gap-3 items-end">
                <div className="flex-1"><label className="text-[10px] text-white/40 block mb-1">Title</label><input value={widgetTitle} onChange={e => setWidgetTitle(e.target.value)} className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" /></div>
                <div><label className="text-[10px] text-white/40 block mb-1">Type</label><select value={widgetType} onChange={e => setWidgetType(e.target.value)} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">{WIDGET_TYPES.map(wt => <option key={wt} value={wt}>{wt}</option>)}</select></div>
                <div><label className="text-[10px] text-white/40 block mb-1">Source</label><select value={widgetSource} onChange={e => setWidgetSource(e.target.value)} className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">{DATA_SOURCES.map(ds => <option key={ds} value={ds}>{ds}</option>)}</select></div>
                <button onClick={addWidget} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Add</button>
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            {((current.widgets as D[]) || []).map((w) => (
              <div key={w.id as string} className="glass rounded-xl p-3" style={{ gridColumn: `span ${(w.w as number) || 1}` }}>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-semibold">{w.title as string}</span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-white/40">{w.type as string}</span>
                </div>
                <div className={`${WIDGET_COLORS[(w.type as string)] ?? 'bg-white/5'} rounded-lg h-24 flex items-center justify-center`}>
                  <span className="text-xs text-white/30">{(w.type as string).replace('_', ' ')} preview</span>
                </div>
              </div>
            ))}
          </div>
          {((current.widgets as D[]) || []).length === 0 && <div className="text-center text-sm text-white/30 py-12">No widgets yet. Toggle edit mode and add widgets.</div>}
        </div>
      )}
    </div>
  );
}
