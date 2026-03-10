'use client';

import { useAppStore } from '@/stores/app-store';

const WALLPAPERS: Record<string, string> = {
  aurora: 'radial-gradient(ellipse at 20% 50%, #1a0533 0%, #0a0e1a 50%), radial-gradient(ellipse at 80% 20%, #0c2340 0%, transparent 50%), radial-gradient(ellipse at 50% 80%, #0d1f3c 0%, transparent 60%)',
  midnight: 'radial-gradient(ellipse at 30% 30%, #0f0c29 0%, #302b63 50%, #24243e 100%)',
  ocean: 'radial-gradient(ellipse at 20% 80%, #0c1445 0%, transparent 50%), radial-gradient(ellipse at 80% 30%, #1a3a5c 0%, transparent 50%), linear-gradient(135deg, #0a0e1a 0%, #0c1935 100%)',
  nebula: 'radial-gradient(ellipse at 60% 40%, #1b0a2e 0%, transparent 50%), radial-gradient(ellipse at 20% 70%, #2d1b4e 0%, transparent 50%), linear-gradient(180deg, #0a0e1a 0%, #150a20 100%)',
};

export function WallpaperLayer() {
  const wallpaper = useAppStore((s) => s.wallpaper);

  return (
    <div
      className="fixed inset-0 -z-10"
      style={{ background: WALLPAPERS[wallpaper] || WALLPAPERS.aurora }}
    >
      {/* Subtle noise overlay */}
      <div className="absolute inset-0 opacity-[0.03]"
        style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 256 256\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.9\' numOctaves=\'4\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")' }}
      />
    </div>
  );
}

export const WALLPAPER_OPTIONS = Object.keys(WALLPAPERS);
