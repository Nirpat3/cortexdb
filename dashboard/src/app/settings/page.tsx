'use client';

import { Settings, Palette, LayoutGrid, Plug, Info } from 'lucide-react';
import { AppShell } from '@/components/shell/AppShell';
import { GlassCard } from '@/components/shared/GlassCard';
import { useAppStore } from '@/stores/app-store';
import { APPS, DEFAULT_DOCK_IDS } from '@/lib/constants';
import { WALLPAPER_OPTIONS } from '@/components/springboard/WallpaperLayer';

const WALLPAPER_PREVIEWS: Record<string, string> = {
  aurora: 'radial-gradient(ellipse at 20% 50%, #1a0533, #0a0e1a 70%)',
  midnight: 'radial-gradient(ellipse at 30% 30%, #0f0c29, #302b63 60%, #24243e)',
  ocean: 'radial-gradient(ellipse at 50% 50%, #0c1445, #1a3a5c 70%)',
  nebula: 'radial-gradient(ellipse at 60% 40%, #1b0a2e, #2d1b4e 70%)',
};

export default function SettingsPage() {
  const { wallpaper, setWallpaper, dockIds, setDockIds } = useAppStore();

  const toggleDock = (id: string) => {
    if (dockIds.includes(id)) {
      if (dockIds.length > 2) setDockIds(dockIds.filter((d) => d !== id));
    } else {
      if (dockIds.length < 6) setDockIds([...dockIds, id]);
    }
  };

  return (
    <AppShell title="Settings" icon={Settings} color="#6B7280">
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Wallpaper */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Palette className="w-4 h-4 text-white/50" />
            <h3 className="text-sm font-semibold">Wallpaper</h3>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {WALLPAPER_OPTIONS.map((wp) => (
              <button
                key={wp}
                onClick={() => setWallpaper(wp)}
                className={`relative aspect-[4/3] rounded-xl overflow-hidden transition-all ${
                  wallpaper === wp ? 'ring-2 ring-white/50 scale-105' : 'hover:ring-1 ring-white/20'
                }`}
                style={{ background: WALLPAPER_PREVIEWS[wp] || '#111' }}
              >
                <span className="absolute bottom-1.5 left-0 right-0 text-center text-[10px] text-white/60 capitalize">
                  {wp}
                </span>
              </button>
            ))}
          </div>
        </GlassCard>

        {/* Dock Config */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <LayoutGrid className="w-4 h-4 text-white/50" />
            <h3 className="text-sm font-semibold">Dock Apps</h3>
            <span className="text-[10px] text-white/30 ml-auto">{dockIds.length}/6 slots</span>
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
            {APPS.map((app) => {
              const Icon = app.icon;
              const inDock = dockIds.includes(app.id);
              return (
                <button
                  key={app.id}
                  onClick={() => toggleDock(app.id)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-colors ${
                    inDock ? 'bg-white/10 text-white' : 'bg-white/3 text-white/40 hover:bg-white/5'
                  }`}
                >
                  <Icon className="w-4 h-4 shrink-0" style={{ color: inDock ? app.color : undefined }} />
                  <span className="text-xs truncate">{app.name}</span>
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setDockIds(DEFAULT_DOCK_IDS)}
            className="mt-3 text-xs text-white/30 hover:text-white/50 transition-colors"
          >
            Reset to defaults
          </button>
        </GlassCard>

        {/* Connection */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-4">
            <Plug className="w-4 h-4 text-white/50" />
            <h3 className="text-sm font-semibold">Connection</h3>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-white/40">API Endpoint</span>
              <span className="font-mono text-white/60">localhost:5400</span>
            </div>
            <div className="flex justify-between">
              <span className="text-white/40">Dashboard Port</span>
              <span className="font-mono text-white/60">3400</span>
            </div>
          </div>
        </GlassCard>

        {/* About */}
        <GlassCard>
          <div className="flex items-center gap-2 mb-3">
            <Info className="w-4 h-4 text-white/50" />
            <h3 className="text-sm font-semibold">About</h3>
          </div>
          <div className="space-y-1 text-sm text-white/40">
            <div>CortexDB v4.0.0</div>
            <div>The Consciousness-Inspired Unified Database</div>
            <div className="text-white/20 text-xs mt-2">Copyright 2026 Nirlab Inc. All rights reserved.</div>
          </div>
        </GlassCard>
      </div>
    </AppShell>
  );
}
