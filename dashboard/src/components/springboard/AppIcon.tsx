'use client';

import { motion } from 'framer-motion';
import type { AppDefinition } from '@/lib/constants';

interface AppIconProps {
  app: AppDefinition;
  onClick: (app: AppDefinition) => void;
  index: number;
  compact?: boolean;
}

export function AppIcon({ app, onClick, index, compact }: AppIconProps) {
  const Icon = app.icon;
  const iconSize = compact ? 48 : 60;

  return (
    <motion.button
      className="flex flex-col items-center gap-1.5 outline-none"
      initial={{ opacity: 0, scale: 0.5 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: index * 0.04, type: 'spring', stiffness: 300, damping: 25 }}
      whileHover={{ scale: 1.08 }}
      whileTap={{ scale: 0.9 }}
      onClick={() => onClick(app)}
    >
      <div
        className="flex items-center justify-center rounded-[22%] icon-shadow"
        style={{
          width: iconSize,
          height: iconSize,
          background: `linear-gradient(135deg, ${app.color}dd, ${app.color}88)`,
        }}
      >
        <Icon className="text-white" style={{ width: iconSize * 0.45, height: iconSize * 0.45 }} />
      </div>
      <span className="text-[11px] font-medium text-white/80 drop-shadow-lg max-w-[72px] truncate">
        {app.name}
      </span>
    </motion.button>
  );
}
