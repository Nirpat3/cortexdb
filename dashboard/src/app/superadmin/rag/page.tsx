'use client';

import { useState, useEffect, useCallback } from 'react';
import { BookOpen, Upload, Search, Trash2, RefreshCw, Database, FileText } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

export default function RAGPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'documents' | 'ingest' | 'search'>('documents');
  const [documents, setDocuments] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  // Ingest form
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<any>(null);

  // Search form
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [docs, st] = await Promise.allSettled([
        superadminApi.ragDocuments(),
        superadminApi.ragStats(),
      ]);
      if (docs.status === 'fulfilled') setDocuments((docs.value as any).documents || []);
      if (st.status === 'fulfilled') setStats(st.value);
    } catch { /* silent */ }
    setLoading(false);
  }, []);

  useEffect(() => { loadData(); }, [loadData]);

  const handleIngest = async () => {
    if (!title.trim() || !content.trim()) return;
    setIngesting(true);
    setIngestResult(null);
    try {
      const res = await superadminApi.ragIngest(title, content);
      setIngestResult(res);
      setTitle('');
      setContent('');
      await loadData();
    } catch (e: any) {
      setIngestResult({ error: e.message });
    }
    setIngesting(false);
  };

  const handleSearch = async () => {
    if (!query.trim()) return;
    setSearching(true);
    try {
      const res = await superadminApi.ragRetrieve(query);
      setResults((res as any).results || []);
    } catch { /* silent */ }
    setSearching(false);
  };

  const handleDelete = async (docId: string) => {
    try {
      await superadminApi.ragDelete(docId);
      await loadData();
    } catch { /* silent */ }
  };

  const TABS = [
    { id: 'documents', label: 'Documents', icon: FileText },
    { id: 'ingest', label: 'Ingest', icon: Upload },
    { id: 'search', label: 'Search', icon: Search },
  ] as const;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/20 flex items-center justify-center">
            <BookOpen className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('rag.title')}</h1>
            <p className="text-xs text-white/40">{t('rag.subtitle')}</p>
          </div>
        </div>
        <button onClick={loadData} disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg glass text-xs text-white/60 hover:text-white transition">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> {t('common.refresh')}
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4">
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Documents</div>
            <div className="text-2xl font-bold">{stats.total_documents}</div>
          </div>
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Total Chunks</div>
            <div className="text-2xl font-bold">{stats.total_chunks}</div>
          </div>
          <div className="glass rounded-xl p-4 border border-white/5">
            <div className="text-xs text-white/40 mb-1">Vector Store</div>
            <div className={`text-2xl font-bold ${stats.vector_store === 'connected' ? 'text-green-400' : 'text-amber-400'}`}>
              {stats.vector_store}
            </div>
          </div>
        </div>
      )}

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

      {/* Documents Tab */}
      {tab === 'documents' && (
        <div className="glass rounded-xl p-5 border border-white/5">
          {documents.length === 0 ? (
            <p className="text-sm text-white/30 text-center py-4">No documents ingested yet. Use the Ingest tab to add knowledge.</p>
          ) : (
            <div className="space-y-2">
              {documents.map((doc: any) => (
                <div key={doc.doc_id} className="flex items-center justify-between p-3 rounded-lg bg-white/5">
                  <div className="flex items-center gap-3">
                    <Database className="w-4 h-4 text-emerald-400" />
                    <div>
                      <div className="text-sm font-medium">{doc.title}</div>
                      <div className="text-[10px] text-white/30">
                        {doc.chunks} chunks | {doc.char_count?.toLocaleString()} chars | {doc.stored_vectors} vectors
                        {doc.ingested_at && ` | ${new Date(doc.ingested_at * 1000).toLocaleDateString()}`}
                      </div>
                    </div>
                  </div>
                  <button onClick={() => handleDelete(doc.doc_id)}
                    className="p-1.5 rounded-lg hover:bg-red-500/10 text-white/30 hover:text-red-400 transition">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Ingest Tab */}
      {tab === 'ingest' && (
        <div className="glass rounded-xl p-5 border border-white/5 space-y-4">
          <div>
            <label className="text-xs text-white/40 block mb-1">Document Title</label>
            <input value={title} onChange={e => setTitle(e.target.value)}
              placeholder="e.g., API Reference v2"
              className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-emerald-500/50 focus:outline-none" />
          </div>
          <div>
            <label className="text-xs text-white/40 block mb-1">Content (text/markdown)</label>
            <textarea value={content} onChange={e => setContent(e.target.value)} rows={10}
              placeholder="Paste document content here..."
              className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-emerald-500/50 focus:outline-none" />
          </div>
          <button onClick={handleIngest} disabled={ingesting || !title.trim() || !content.trim()}
            className="px-4 py-2 rounded-lg bg-emerald-500/20 text-emerald-300 text-xs font-medium hover:bg-emerald-500/30 transition disabled:opacity-50">
            {ingesting ? 'Ingesting...' : 'Ingest Document'}
          </button>
          {ingestResult && (
            <div className={`p-3 rounded-lg text-xs ${ingestResult.error ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
              {ingestResult.error || `Ingested: ${ingestResult.chunks} chunks, ${ingestResult.stored_vectors} vectors stored`}
            </div>
          )}
        </div>
      )}

      {/* Search Tab */}
      {tab === 'search' && (
        <div className="space-y-4">
          <div className="glass rounded-xl p-5 border border-white/5">
            <div className="flex gap-2">
              <input value={query} onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="Search knowledge base..."
                className="flex-1 glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 focus:border-emerald-500/50 focus:outline-none" />
              <button onClick={handleSearch} disabled={searching || !query.trim()}
                className="px-4 py-2 rounded-lg bg-emerald-500/20 text-emerald-300 text-xs font-medium hover:bg-emerald-500/30 transition disabled:opacity-50">
                {searching ? t('common.loading') : t('common.search')}
              </button>
            </div>
          </div>

          {results.length > 0 && (
            <div className="space-y-2">
              {results.map((r: any, i: number) => (
                <div key={i} className="glass rounded-xl p-4 border border-white/5">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-emerald-400">{r.title}</span>
                    <span className="text-[10px] text-white/30">Score: {r.score?.toFixed(3)} | Chunk {r.chunk_index}</span>
                  </div>
                  <p className="text-xs text-white/60 whitespace-pre-wrap">{r.content}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
