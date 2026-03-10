'use client';

import { useRouter } from 'next/navigation';
import { WallpaperLayer } from '@/components/springboard/WallpaperLayer';
import { StatusBar } from '@/components/springboard/StatusBar';
import { WidgetGrid } from '@/components/springboard/WidgetGrid';
import { SpringboardGrid } from '@/components/springboard/SpringboardGrid';
import { Dock } from '@/components/springboard/Dock';
import { Spotlight } from '@/components/springboard/Spotlight';
import type { AppDefinition } from '@/lib/constants';

export default function HomePage() {
  const router = useRouter();

  const handleAppOpen = (app: AppDefinition) => {
    router.push(app.route);
  };

  return (
    <div className="h-dvh flex flex-col">
      <WallpaperLayer />
      <StatusBar />
      <Spotlight onAppOpen={handleAppOpen} />

      <div className="flex-1 flex flex-col pt-12 pb-28 overflow-hidden">
        <WidgetGrid />
        <SpringboardGrid onAppOpen={handleAppOpen} />
      </div>

      <Dock onAppOpen={handleAppOpen} />
    </div>
  );
}
