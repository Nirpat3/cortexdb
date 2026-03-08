'use client';

import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Share2, Search, Plus, Link, ArrowLeft, X, ChevronRight } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const TYPE_COLORS: Record<string, string> = {
  insight: 'purple',
  fact: 'blue',
  rule: 'amber',
  pattern: 'emerald',
};

const TYPE_BADGE_CLASSES: Record<string, string> = {
  insight: 'bg-purple-500/20 text-purple-300',
  fact: 'bg-blue-500/20 text-blue-300',
  rule: 'bg-amber-500/20 text-amber-300',
  pattern: 'bg-emerald-500/20 text-emerald-300',
};

function confidenceColor(c: number): string {
  if (c >= 0.8) return 'bg-emerald-500';
  if (c >= 0.5) return 'bg-amber-500';
  return 'bg-red-500';
}

export default function KnowledgeGraphPage() {
  const { t } = useTranslation();
  const router = useRouter();

  const [nodes, setNodes] = useState<D[]>([]);
  const [selectedNode, setSelectedNode] = useState<D | null>(null);
  const [neighbors, setNeighbors] = useState<D[]>([]);
  const [edges, setEdges] = useState<D[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<D[] | null>(null);
  const [filterTopic, setFilterTopic] = useState('');
  const [filterType, setFilterType] = useState('');
  const [showAddNode, setShowAddNode] = useState(false);
  const [showAddEdge, setShowAddEdge] = useState(false);

  // Add node form
  const [nodeForm, setNodeForm] = useState<D>({
    topic: '',
    content: '',
    node_type: 'insight',
    source_agent: '',
    department: '',
    confidence: 0.5,
  });

  // Add edge form
  const [edgeForm, setEdgeForm] = useState<D>({
    from_node: '',
    to_node: '',
    relation: '',
    weight: 0.5,
  });

  const fetchNodes = useCallback(async () => {
    try {
      const data = await superadminApi.getKnowledgeNodes({ limit: 50 });
      setNodes(Array.isArray(data) ? data : (data as D).nodes ?? []);
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchNodes(); }, [fetchNodes]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      setSearchResults(null);
      return;
    }
    try {
      const data = await superadminApi.searchKnowledge(searchQuery);
      setSearchResults(Array.isArray(data) ? data : (data as D).results ?? []);
    } catch { /* silent */ }
  };

  const selectNode = async (node: D) => {
    setSelectedNode(node);
    const nodeId = node.id ?? node.node_id;
    if (!nodeId) return;
    try {
      const [n, e] = await Promise.all([
        superadminApi.getKnowledgeNeighbors(nodeId, 2),
        superadminApi.getKnowledgeEdges({ from_node: nodeId }),
      ]);
      setNeighbors(Array.isArray(n) ? n : (n as D).neighbors ?? []);
      setEdges(Array.isArray(e) ? e : (e as D).edges ?? []);
    } catch { /* silent */ }
  };

  const handleAddNode = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await superadminApi.addKnowledgeNode(nodeForm as any);
      setShowAddNode(false);
      setNodeForm({ topic: '', content: '', node_type: 'insight', source_agent: '', department: '', confidence: 0.5 });
      fetchNodes();
    } catch { /* silent */ }
  };

  const handleAddEdge = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await superadminApi.addKnowledgeEdge(edgeForm as any);
      setShowAddEdge(false);
      setEdgeForm({ from_node: '', to_node: '', relation: '', weight: 0.5 });
      if (selectedNode) selectNode(selectedNode);
    } catch { /* silent */ }
  };

  // Filtered node list
  const displayNodes = searchResults ?? nodes;
  const filteredNodes = displayNodes.filter((n: D) => {
    if (filterTopic && !(n.topic ?? '').toLowerCase().includes(filterTopic.toLowerCase())) return false;
    if (filterType && n.node_type !== filterType) return false;
    return true;
  });

  const uniqueTypes = Array.from(new Set(nodes.map((n: D) => n.node_type).filter(Boolean))) as string[];

  return (
    <div className="min-h-screen bg-black text-white">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-5 border-b border-white/10">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push('/superadmin/knowledge')}
            className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition">
            <ArrowLeft className="w-4 h-4" />
          </button>
          <Share2 className="w-6 h-6 text-blue-400" />
          <div>
            <h1 className="text-2xl font-bold">{t('knowledge.graph.title')}</h1>
            <p className="text-sm text-white/40">{t('knowledge.graph.subtitle')}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowAddEdge(true)}
            className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition flex items-center gap-1.5">
            <Link className="w-4 h-4" /> Add Edge
          </button>
          <button onClick={() => setShowAddNode(true)}
            className="px-4 py-2 rounded-xl bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 text-sm transition flex items-center gap-1.5">
            <Plus className="w-4 h-4" /> Add Node
          </button>
        </div>
      </div>

      {/* Search Bar */}
      <div className="px-6 py-4 border-b border-white/10">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search knowledge graph..."
              className="w-full bg-white/5 border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
            />
          </div>
          <button type="submit"
            className="px-4 py-2 rounded-xl bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 text-sm transition">
            {t('common.search')}
          </button>
          {searchResults && (
            <button type="button" onClick={() => { setSearchResults(null); setSearchQuery(''); }}
              className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition">
              Clear
            </button>
          )}
        </form>
      </div>

      {/* Main Content */}
      <div className="flex" style={{ height: 'calc(100vh - 150px)' }}>
        {/* Left Panel - Node List */}
        <div className="w-80 border-r border-white/10 flex flex-col overflow-hidden">
          {/* Filters */}
          <div className="p-4 border-b border-white/10 space-y-2">
            <input
              type="text"
              value={filterTopic}
              onChange={(e) => setFilterTopic(e.target.value)}
              placeholder="Filter by topic..."
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
            />
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none appearance-none"
            >
              <option value="">{t('common.all')} types</option>
              {uniqueTypes.map((ut) => (
                <option key={ut} value={ut}>{ut}</option>
              ))}
            </select>
          </div>

          {/* Node List */}
          <div className="flex-1 overflow-y-auto p-3 space-y-1">
            {filteredNodes.length === 0 && (
              <p className="text-sm text-white/30 text-center py-8">{t('common.noData')}</p>
            )}
            {filteredNodes.map((node: D) => {
              const nodeId = node.id ?? node.node_id;
              const isSelected = selectedNode && (selectedNode.id ?? selectedNode.node_id) === nodeId;
              const badgeClass = TYPE_BADGE_CLASSES[node.node_type] ?? 'bg-white/10 text-white/60';
              const conf = typeof node.confidence === 'number' ? node.confidence : 0;

              return (
                <div
                  key={nodeId}
                  onClick={() => selectNode(node)}
                  className={`p-3 rounded-xl hover:bg-white/5 cursor-pointer transition ${isSelected ? 'bg-white/10' : ''}`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium truncate flex-1">{node.topic ?? 'Untitled'}</span>
                    <ChevronRight className="w-3.5 h-3.5 text-white/20 flex-shrink-0 ml-2" />
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium ${badgeClass}`}>
                      {node.node_type ?? 'unknown'}
                    </span>
                    <div className="flex-1 flex items-center gap-1.5">
                      <div className="h-1.5 rounded-full bg-white/10 w-full">
                        <div
                          className={`h-1.5 rounded-full ${confidenceColor(conf)}`}
                          style={{ width: `${conf * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-white/30 flex-shrink-0">{Math.round(conf * 100)}%</span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Panel - Detail View */}
        <div className="flex-1 overflow-y-auto p-6">
          {!selectedNode ? (
            <div className="flex flex-col items-center justify-center h-full text-white/20">
              <Share2 className="w-16 h-16 mb-4" />
              <p className="text-lg font-medium">Select a node to explore</p>
              <p className="text-sm mt-1">Click any node in the left panel to view details</p>
            </div>
          ) : (
            <div className="space-y-5 max-w-3xl">
              {/* Node Info Card */}
              <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-bold">{selectedNode.topic ?? 'Untitled'}</h2>
                  <span className={`text-xs px-2 py-1 rounded-lg font-medium ${TYPE_BADGE_CLASSES[selectedNode.node_type] ?? 'bg-white/10 text-white/60'}`}>
                    {selectedNode.node_type ?? 'unknown'}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm mb-4">
                  <div>
                    <span className="text-white/40 block text-xs mb-1">Node ID</span>
                    <span className="font-mono text-white/70">{selectedNode.id ?? selectedNode.node_id ?? '-'}</span>
                  </div>
                  <div>
                    <span className="text-white/40 block text-xs mb-1">Type</span>
                    <span className="text-white/70">{selectedNode.node_type ?? '-'}</span>
                  </div>
                  <div>
                    <span className="text-white/40 block text-xs mb-1">Source Agent</span>
                    <span className="font-mono text-white/70">{selectedNode.source_agent ?? '-'}</span>
                  </div>
                  <div>
                    <span className="text-white/40 block text-xs mb-1">Department</span>
                    <span className="text-white/70">{selectedNode.department ?? '-'}</span>
                  </div>
                </div>

                {/* Confidence */}
                <div className="mb-4">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span className="text-white/40">Confidence</span>
                    <span className="text-white/60">{Math.round((selectedNode.confidence ?? 0) * 100)}%</span>
                  </div>
                  <div className="h-1.5 rounded-full bg-white/10 w-full">
                    <div
                      className={`h-1.5 rounded-full ${confidenceColor(selectedNode.confidence ?? 0)}`}
                      style={{ width: `${(selectedNode.confidence ?? 0) * 100}%` }}
                    />
                  </div>
                </div>

                {/* Content */}
                {selectedNode.content && (
                  <div>
                    <span className="text-white/40 block text-xs mb-1">Content</span>
                    <p className="text-sm text-white/70 whitespace-pre-wrap bg-white/5 rounded-xl p-3">
                      {selectedNode.content}
                    </p>
                  </div>
                )}

                {/* Metadata */}
                {selectedNode.metadata && Object.keys(selectedNode.metadata).length > 0 && (
                  <div className="mt-4">
                    <span className="text-white/40 block text-xs mb-1">Metadata</span>
                    <pre className="text-xs text-white/50 bg-white/5 rounded-xl p-3 overflow-x-auto">
                      {JSON.stringify(selectedNode.metadata, null, 2)}
                    </pre>
                  </div>
                )}
              </div>

              {/* Neighbors */}
              <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Share2 className="w-4 h-4 text-blue-400" />
                  Neighbors ({neighbors.length})
                </h3>
                {neighbors.length === 0 ? (
                  <p className="text-sm text-white/30">No neighbors found</p>
                ) : (
                  <div className="space-y-2">
                    {neighbors.map((nb: D, i: number) => {
                      const nbId = nb.id ?? nb.node_id ?? i;
                      const nbBadge = TYPE_BADGE_CLASSES[nb.node_type] ?? 'bg-white/10 text-white/60';
                      return (
                        <div
                          key={nbId}
                          onClick={() => selectNode(nb)}
                          className="p-3 rounded-xl hover:bg-white/5 cursor-pointer transition flex items-center justify-between"
                        >
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">{nb.topic ?? 'Untitled'}</span>
                            <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium ${nbBadge}`}>
                              {nb.node_type ?? ''}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            {nb.relation && (
                              <span className="text-[10px] px-2 py-0.5 rounded-md bg-white/10 text-white/50">
                                {nb.relation}
                              </span>
                            )}
                            <ChevronRight className="w-3.5 h-3.5 text-white/20" />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Edges */}
              <div className="bg-white/5 border border-white/10 rounded-2xl p-5">
                <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Link className="w-4 h-4 text-amber-400" />
                  Edges ({edges.length})
                </h3>
                {edges.length === 0 ? (
                  <p className="text-sm text-white/30">No edges found</p>
                ) : (
                  <div className="space-y-2">
                    {edges.map((edge: D, i: number) => {
                      const edgeId = edge.id ?? edge.edge_id ?? i;
                      return (
                        <div key={edgeId} className="p-3 rounded-xl bg-white/5 flex items-center justify-between">
                          <div className="flex items-center gap-2 text-sm">
                            <span className="font-mono text-white/50 text-xs">{edge.from_node ?? '-'}</span>
                            <span className="text-white/30">&rarr;</span>
                            <span className="px-2 py-0.5 rounded-md bg-amber-500/20 text-amber-300 text-xs">
                              {edge.relation ?? 'related'}
                            </span>
                            <span className="text-white/30">&rarr;</span>
                            <span className="font-mono text-white/50 text-xs">{edge.to_node ?? '-'}</span>
                          </div>
                          {typeof edge.weight === 'number' && (
                            <span className="text-xs text-white/30">w: {edge.weight.toFixed(2)}</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Add Node Modal */}
      {showAddNode && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-lg">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold">Add Knowledge Node</h2>
              <button onClick={() => setShowAddNode(false)} className="p-1.5 rounded-lg hover:bg-white/10 transition">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleAddNode} className="space-y-4">
              <div>
                <label className="text-xs text-white/40 block mb-1">Topic</label>
                <input
                  type="text"
                  value={nodeForm.topic}
                  onChange={(e) => setNodeForm({ ...nodeForm, topic: e.target.value })}
                  required
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">Content</label>
                <textarea
                  value={nodeForm.content}
                  onChange={(e) => setNodeForm({ ...nodeForm, content: e.target.value })}
                  rows={3}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none resize-none"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-xs text-white/40 block mb-1">Node Type</label>
                  <select
                    value={nodeForm.node_type}
                    onChange={(e) => setNodeForm({ ...nodeForm, node_type: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none appearance-none"
                  >
                    <option value="insight">Insight</option>
                    <option value="fact">Fact</option>
                    <option value="rule">Rule</option>
                    <option value="pattern">Pattern</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-white/40 block mb-1">Department</label>
                  <input
                    type="text"
                    value={nodeForm.department}
                    onChange={(e) => setNodeForm({ ...nodeForm, department: e.target.value })}
                    className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
                  />
                </div>
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">Source Agent</label>
                <input
                  type="text"
                  value={nodeForm.source_agent}
                  onChange={(e) => setNodeForm({ ...nodeForm, source_agent: e.target.value })}
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">
                  Confidence: {Math.round(nodeForm.confidence * 100)}%
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={nodeForm.confidence}
                  onChange={(e) => setNodeForm({ ...nodeForm, confidence: parseFloat(e.target.value) })}
                  className="w-full accent-blue-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowAddNode(false)}
                  className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition">
                  {t('common.cancel')}
                </button>
                <button type="submit"
                  className="px-4 py-2 rounded-xl bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 text-sm transition">
                  Add Node
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Edge Modal */}
      {showAddEdge && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-zinc-900 border border-white/10 rounded-2xl p-6 w-full max-w-lg">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-bold">Add Knowledge Edge</h2>
              <button onClick={() => setShowAddEdge(false)} className="p-1.5 rounded-lg hover:bg-white/10 transition">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleAddEdge} className="space-y-4">
              <div>
                <label className="text-xs text-white/40 block mb-1">From Node (ID)</label>
                <input
                  type="text"
                  value={edgeForm.from_node}
                  onChange={(e) => setEdgeForm({ ...edgeForm, from_node: e.target.value })}
                  required
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">To Node (ID)</label>
                <input
                  type="text"
                  value={edgeForm.to_node}
                  onChange={(e) => setEdgeForm({ ...edgeForm, to_node: e.target.value })}
                  required
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">Relation</label>
                <input
                  type="text"
                  value={edgeForm.relation}
                  onChange={(e) => setEdgeForm({ ...edgeForm, relation: e.target.value })}
                  required
                  placeholder="e.g. depends_on, related_to, contradicts"
                  className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-2.5 text-sm focus:border-blue-500/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="text-xs text-white/40 block mb-1">
                  Weight: {edgeForm.weight.toFixed(2)}
                </label>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={edgeForm.weight}
                  onChange={(e) => setEdgeForm({ ...edgeForm, weight: parseFloat(e.target.value) })}
                  className="w-full accent-blue-500"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button type="button" onClick={() => setShowAddEdge(false)}
                  className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-sm transition">
                  {t('common.cancel')}
                </button>
                <button type="submit"
                  className="px-4 py-2 rounded-xl bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 text-sm transition">
                  Add Edge
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
