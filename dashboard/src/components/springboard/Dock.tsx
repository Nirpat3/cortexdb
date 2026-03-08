'use client';

import { motion } from 'framer-motion';
import { APPS } from '@/lib/constants';
import { useAppStore } from '@/stores/app-store';
import { AppIcon } from './AppIcon';
import type { AppDefinition } from '@/lib/constants';

interface DockProps {
  onAppOpen: (app: AppDefinition) => void;
}

export function Dock({ onAppOpen }: DockProps) {
  const dockIds = useAppStore((s) => s.dockIds);
  const dockApps = dockIds.map((id) => APPS.find((a) => a.id === id)).filter(Boolean) as AppDefinition[];

  return (
    <motion.div
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 glass-dock rounded-3xl px-4 py-2.5 flex items-center gap-4 sm:gap-6"
      initial={{ y: 100, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ delay: 0.3, type: 'spring', stiffness: 200, damping: 25 }}
    >
      {dockApps.map((app, i) => (
        <AppIcon key={app.id} app={app} onClick={onAppOpen} index={i} compact />
      ))}
    </motion.div>
  );
}
