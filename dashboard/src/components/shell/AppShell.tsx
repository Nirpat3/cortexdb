'use client';

import { motion } from 'framer-motion';
import { ChevronLeft } from 'lucide-react';
import { useRouter } from 'next/navigation';
import type { LucideIcon } from 'lucide-react';

interface AppShellProps {
  title: string;
  icon: LucideIcon;
  color: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
}

export function AppShell({ title, icon: Icon, color, children, actions }: AppShellProps) {
  const router = useRouter();

  return (
    <motion.div
      className="fixed inset-0 z-30 flex flex-col bg-[#0A0E1A]/95 backdrop-blur-xl"
      initial={{ opacity: 0, scale: 0.92, borderRadius: '24px' }}
      animate={{ opacity: 1, scale: 1, borderRadius: '0px' }}
      exit={{ opacity: 0, scale: 0.92, borderRadius: '24px' }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-3 border-b border-white/5 shrink-0">
        <button
          onClick={() => router.push('/')}
          className="flex items-center gap-1.5 text-white/60 hover:text-white transition-colors"
        >
          <ChevronLeft className="w-5 h-5" />
          <span className="text-sm hidden sm:inline">Home</span>
        </button>

        <div className="flex items-center gap-2">
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center"
            style={{ background: `${color}30` }}
          >
            <Icon className="w-4 h-4" style={{ color }} />
          </div>
          <h1 className="text-base font-semibold text-white">{title}</h1>
        </div>

        <div className="flex items-center gap-2">
          {actions}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden p-4 sm:p-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="max-w-7xl mx-auto"
        >
          {children}
        </motion.div>
      </div>

      {/* Home indicator */}
      <div className="flex justify-center pb-2 shrink-0">
        <button
          onClick={() => router.push('/')}
          className="w-32 h-1 rounded-full bg-white/20 hover:bg-white/40 transition-colors"
        />
      </div>
    </motion.div>
  );
}
