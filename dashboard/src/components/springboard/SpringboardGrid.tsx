'use client';

import { APPS } from '@/lib/constants';
import { useAppStore } from '@/stores/app-store';
import { AppIcon } from './AppIcon';
import type { AppDefinition } from '@/lib/constants';

interface SpringboardGridProps {
  onAppOpen: (app: AppDefinition) => void;
}

export function SpringboardGrid({ onAppOpen }: SpringboardGridProps) {
  const dockIds = useAppStore((s) => s.dockIds);
  const nonDockApps = APPS.filter((a) => !dockIds.includes(a.id));

  return (
    <div className="flex-1 overflow-y-auto px-6 pt-4 pb-8">
      <div className="grid grid-cols-4 sm:grid-cols-5 lg:grid-cols-6 gap-y-8 gap-x-4 justify-items-center max-w-3xl mx-auto">
        {nonDockApps.map((app, i) => (
          <AppIcon key={app.id} app={app} onClick={onAppOpen} index={i} />
        ))}
      </div>
    </div>
  );
}
