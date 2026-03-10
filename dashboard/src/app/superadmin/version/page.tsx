'use client';

import { useEffect, useState, useCallback } from 'react';
import { Tag, RefreshCw, ArrowUpCircle, GitBranch, FileText } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type D = Record<string, any>;

const BUMP_TYPES = ['patch', 'minor', 'major'] as const;

export default function VersionPage() {
  const { t } = useTranslation();
  const [versionInfo, setVersionInfo] = useState<D | null>(null);
  const [changelog, setChangelog] = useState('');
  const [showBump, setShowBump] = useState(false);
  const [bumpType, setBumpType] = useState<string>('patch');
  const [reason, setReason] = useState('');
  const [changes, setChanges] = useState('');
  const [syncing, setSyncing] = useState(false);
  const [bumping, setBumping] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [v, c] = await Promise.all([
        superadminApi.getVersion().catch(() => null),
        superadminApi.getChangelog(20).catch(() => null),
      ]);
      if (v) setVersionInfo(v);
      if (c) setChangelog((c as D).changelog ?? '');
    } catch { /* silent */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const handleBump = async () => {
    if (!reason) return;
    setBumping(true);
    try {
      const changeList = changes.split('\n').map(s => s.trim()).filter(Boolean);
      await superadminApi.bumpVersion(bumpType, reason, changeList);
      setShowBump(false);
      setReason('');
      setChanges('');
      refresh();
    } catch { /* silent */ }
    setBumping(false);
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      await superadminApi.syncVersion();
      refresh();
    } catch { /* silent */ }
    setSyncing(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Tag className="w-6 h-6 text-cyan-400" /> {t('version.title')}
          </h1>
          <p className="text-sm text-white/40">{t('version.subtitle')}</p>
        </div>
        <div className="flex gap-2">
          <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={handleSync} disabled={syncing}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl glass text-white/60 hover:text-white/90 text-sm">
            <GitBranch className="w-4 h-4" /> {syncing ? 'Syncing...' : 'Sync Files'}
          </button>
          <button onClick={() => setShowBump(!showBump)}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 text-sm">
            <ArrowUpCircle className="w-4 h-4" /> Bump Version
          </button>
        </div>
      </div>

      {/* Current Version */}
      <div className="glass rounded-xl p-6 mb-6">
        <div className="flex items-center gap-4">
          <div className="w-16 h-16 rounded-2xl bg-cyan-500/20 flex items-center justify-center">
            <Tag className="w-8 h-8 text-cyan-400" />
          </div>
          <div>
            <div className="text-4xl font-bold text-cyan-300">v{versionInfo?.version ?? '...'}</div>
            <div className="text-sm text-white/40 mt-1">
              Changelog: {versionInfo?.has_changelog ? 'Available' : 'Not generated yet'}
            </div>
          </div>
        </div>
      </div>

      {/* Bump Form */}
      {showBump && (
        <div className="glass rounded-xl p-4 mb-6 space-y-3">
          <div className="text-sm font-semibold">Bump Version</div>

          <div className="flex gap-2">
            {BUMP_TYPES.map((t) => (
              <button key={t} onClick={() => setBumpType(t)}
                className={`px-4 py-2 rounded-lg text-sm capitalize transition ${
                  bumpType === t ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'
                }`}>
                {t}
                <span className="text-[10px] text-white/30 ml-1.5">
                  {t === 'patch' ? '(bug fix)' : t === 'minor' ? '(feature)' : '(breaking)'}
                </span>
              </button>
            ))}
          </div>

          <input value={reason} onChange={(e) => setReason(e.target.value)}
            placeholder="Reason for version bump..."
            className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10" />

          <textarea value={changes} onChange={(e) => setChanges(e.target.value)}
            placeholder="Changes (one per line)..."
            rows={4}
            className="w-full glass rounded-lg px-3 py-2 text-sm bg-white/5 border border-white/10 resize-none" />

          <div className="flex gap-2">
            <button onClick={handleBump} disabled={bumping || !reason}
              className="px-4 py-2 rounded-lg text-sm bg-cyan-500/20 text-cyan-300 hover:bg-cyan-500/30 disabled:opacity-30">
              {bumping ? 'Bumping...' : 'Bump Version'}
            </button>
            <button onClick={() => setShowBump(false)}
              className="px-4 py-2 rounded-lg text-sm bg-white/5 text-white/40 hover:bg-white/10">{t('common.cancel')}</button>
          </div>
        </div>
      )}

      {/* Changelog */}
      <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
        <FileText className="w-5 h-5 text-white/40" /> Changelog
      </h2>
      <div className="glass rounded-xl p-4">
        {changelog ? (
          <pre className="text-sm text-white/70 whitespace-pre-wrap font-mono leading-relaxed">{changelog}</pre>
        ) : (
          <div className="text-center py-8 text-white/30">No changelog entries yet. Bump version to create the first entry.</div>
        )}
      </div>
    </div>
  );
}
