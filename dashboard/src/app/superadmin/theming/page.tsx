'use client';

import { useEffect, useState, useCallback } from 'react';
import { Palette, RefreshCw, Plus, Check, Pencil, Trash2, Eye } from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

type D = Record<string, unknown>;

const MOCK_THEMES: D[] = [
  { id: 'th-1', name: 'CortexDB Dark', active: true, colors: { primary: '#06b6d4', secondary: '#8b5cf6', accent: '#f59e0b', background: '#000000', surface: '#111111', text: '#ffffff', success: '#10b981', warning: '#f59e0b', error: '#ef4444' } },
  { id: 'th-2', name: 'Ocean Blue', active: false, colors: { primary: '#3b82f6', secondary: '#06b6d4', accent: '#14b8a6', background: '#0f172a', surface: '#1e293b', text: '#e2e8f0', success: '#22c55e', warning: '#eab308', error: '#f43f5e' } },
  { id: 'th-3', name: 'Midnight Purple', active: false, colors: { primary: '#a855f7', secondary: '#ec4899', accent: '#f97316', background: '#0a0014', surface: '#1a0030', text: '#f0e6ff', success: '#4ade80', warning: '#fbbf24', error: '#fb7185' } },
  { id: 'th-4', name: 'Forest Green', active: false, colors: { primary: '#22c55e', secondary: '#14b8a6', accent: '#84cc16', background: '#001a0a', surface: '#0a2d15', text: '#dcfce7', success: '#34d399', warning: '#facc15', error: '#f87171' } },
];

const MOCK_BRANDING: D = {
  company_name: 'CortexDB', tagline: 'Autonomous Database Intelligence', logo_url: '/logo.svg', favicon_url: '/favicon.ico',
  support_email: 'support@cortexdb.io', support_url: 'https://docs.cortexdb.io', terms_url: '/terms', privacy_url: '/privacy',
  custom_domain: '', custom_css: '',
};

const COLOR_FIELDS = ['primary', 'secondary', 'accent', 'background', 'surface', 'text', 'success', 'warning', 'error'];

export default function WhiteLabelThemingPage() {
  const { t } = useTranslation();
  const [tab, setTab] = useState<'themes' | 'branding'>('themes');
  const [themes, setThemes] = useState<D[]>(MOCK_THEMES);
  const [branding, setBranding] = useState<D>(MOCK_BRANDING);
  const [showCreate, setShowCreate] = useState(false);
  const [newTheme, setNewTheme] = useState({ name: '', colors: Object.fromEntries(COLOR_FIELDS.map(f => [f, '#000000'])) });
  const [previewTheme, setPreviewTheme] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await superadminApi.themeList() as D;
      if ((data as D).themes) setThemes((data as D).themes as D[]);
      if ((data as D).branding) setBranding((data as D).branding as D);
    } catch { /* use mock */ }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const activateTheme = (id: string) => {
    setThemes(prev => prev.map(th => ({ ...th, active: th.id === id })));
  };

  const handleCreateTheme = () => {
    if (!newTheme.name) return;
    setThemes(prev => [...prev, { id: `th-${Date.now()}`, name: newTheme.name, active: false, colors: { ...newTheme.colors } }]);
    setNewTheme({ name: '', colors: Object.fromEntries(COLOR_FIELDS.map(f => [f, '#000000'])) });
    setShowCreate(false);
  };

  const updateBranding = (key: string, val: string) => setBranding(prev => ({ ...prev, [key]: val }));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1 flex items-center gap-2">
            <Palette className="w-6 h-6 text-pink-400" /> White-Label &amp; Theming
          </h1>
          <p className="text-sm text-white/40">Theme and branding customization</p>
        </div>
        <button onClick={refresh} className="glass px-3 py-2 rounded-lg text-xs text-white/60 hover:text-white/90"><RefreshCw className="w-3.5 h-3.5" /></button>
      </div>

      <div className="flex gap-2 mb-6">
        {(['themes', 'branding'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)} className={`px-4 py-2 rounded-lg text-sm transition ${tab === t ? 'glass-heavy text-white' : 'glass text-white/50 hover:text-white/80'}`}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'themes' && (
        <div>
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">Themes</h2>
            <button onClick={() => setShowCreate(!showCreate)} className="glass px-3 py-2 rounded-lg text-xs text-pink-400 flex items-center gap-1"><Plus className="w-3.5 h-3.5" /> Create Theme</button>
          </div>

          {showCreate && (
            <div className="glass-heavy rounded-xl p-4 mb-6">
              <h3 className="text-sm font-semibold mb-3">New Theme</h3>
              <input value={newTheme.name} onChange={e => setNewTheme({ ...newTheme, name: e.target.value })} placeholder="Theme name" className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm mb-3" />
              <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 mb-3">
                {COLOR_FIELDS.map(f => (
                  <div key={f}>
                    <label className="text-[10px] text-white/40 block mb-1 capitalize">{f}</label>
                    <div className="flex items-center gap-2">
                      <input type="color" value={newTheme.colors[f]} onChange={e => setNewTheme({ ...newTheme, colors: { ...newTheme.colors, [f]: e.target.value } })} className="w-8 h-8 rounded cursor-pointer bg-transparent border-0" />
                      <span className="text-[10px] text-white/30 font-mono">{newTheme.colors[f]}</span>
                    </div>
                  </div>
                ))}
              </div>
              <button onClick={handleCreateTheme} className="glass px-4 py-2 rounded-lg text-xs text-emerald-400">Create</button>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
            {themes.map(th => {
              const colors = (th.colors as Record<string, string>) || {};
              return (
                <div key={th.id as string} className={`glass rounded-xl p-4 ${th.active ? 'ring-1 ring-pink-400/50' : ''}`}>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-semibold">{th.name as string}</span>
                    {th.active ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-pink-500/20 text-pink-300 flex items-center gap-1"><Check className="w-2.5 h-2.5" /> Active</span> : null}
                  </div>
                  <div className="flex gap-1.5 mb-3">
                    {['primary', 'secondary', 'accent', 'background'].map(c => (
                      <div key={c} className="w-7 h-7 rounded-full border border-white/10" style={{ backgroundColor: colors[c] ?? '#000' }} title={c} />
                    ))}
                  </div>
                  <div className="flex gap-1.5 mb-4">
                    {['success', 'warning', 'error', 'text'].map(c => (
                      <div key={c} className="w-5 h-5 rounded-full border border-white/10" style={{ backgroundColor: colors[c] ?? '#000' }} title={c} />
                    ))}
                  </div>
                  <div className="flex gap-2">
                    {!th.active && <button onClick={() => activateTheme(th.id as string)} className="glass px-2 py-1 rounded text-[10px] text-emerald-400">Activate</button>}
                    <button onClick={() => setPreviewTheme(previewTheme === th.id ? null : th.id as string)} className="glass px-2 py-1 rounded text-[10px] text-cyan-400 flex items-center gap-1"><Eye className="w-2.5 h-2.5" /> Preview</button>
                    <button className="glass px-2 py-1 rounded text-[10px] text-white/40 flex items-center gap-1"><Pencil className="w-2.5 h-2.5" /></button>
                    <button className="glass px-2 py-1 rounded text-[10px] text-red-400 flex items-center gap-1"><Trash2 className="w-2.5 h-2.5" /></button>
                  </div>
                  {previewTheme === th.id && (
                    <div className="mt-3 glass rounded-lg p-2">
                      <pre className="text-[9px] text-white/40 font-mono overflow-auto max-h-32">
{COLOR_FIELDS.map(f => `--color-${f}: ${colors[f] ?? '#000'};`).join('\n')}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tab === 'branding' && (
        <div className="glass-heavy rounded-xl p-6 max-w-2xl">
          <h2 className="text-lg font-semibold mb-4">Branding Configuration</h2>
          <div className="space-y-4">
            {[
              ['company_name', 'Company Name'], ['tagline', 'Tagline'],
              ['logo_url', 'Logo URL'], ['favicon_url', 'Favicon URL'],
              ['support_email', 'Support Email'], ['support_url', 'Support URL'],
              ['terms_url', 'Terms URL'], ['privacy_url', 'Privacy URL'],
              ['custom_domain', 'Custom Domain'],
            ].map(([key, label]) => (
              <div key={key}>
                <label className="text-xs text-white/50 block mb-1">{label}</label>
                <input value={(branding[key] as string) || ''} onChange={e => updateBranding(key, e.target.value)} className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm" />
              </div>
            ))}
            <div>
              <label className="text-xs text-white/50 block mb-1">Custom CSS</label>
              <textarea value={(branding.custom_css as string) || ''} onChange={e => updateBranding('custom_css', e.target.value)} rows={6} className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm font-mono" placeholder=":root { /* custom overrides */ }" />
            </div>
            <button className="glass px-6 py-2.5 rounded-lg text-sm text-emerald-400 hover:text-emerald-300 transition">Save Branding</button>
          </div>
        </div>
      )}
    </div>
  );
}
