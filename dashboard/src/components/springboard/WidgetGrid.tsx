'use client';

import { motion } from 'framer-motion';
import { Activity, Shield, Database } from 'lucide-react';
import { HealthRing } from '@/components/shared/HealthRing';
import { StatusDot } from '@/components/shared/StatusDot';
import { useHealth } from '@/lib/hooks/useHealth';

export function WidgetGrid() {
  const { data } = useHealth();
  const engines = data?.engines || {};
  const engineEntries = Object.entries(engines as Record<string, string>);
  const healthyCount = engineEntries.filter(([, v]) => v === 'ok').length;
  const totalCount = engineEntries.length || 7;
  const score = Math.round((healthyCount / totalCount) * 100);

  return (
    <div className="px-6 pt-2 pb-4 max-w-3xl mx-auto">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {/* System Health Widget */}
        <motion.div
          className="glass rounded-2xl p-4 col-span-2 sm:col-span-1 flex items-center gap-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <HealthRing value={score} size={56} label="health" />
          <div>
            <div className="text-xs text-white/40 flex items-center gap-1.5">
              <Activity className="w-3 h-3" /> System
            </div>
            <div className="text-lg font-semibold text-white">
              {healthyCount}/{totalCount}
            </div>
            <div className="text-[10px] text-white/30">engines online</div>
          </div>
        </motion.div>

        {/* Engine Status Widget */}
        <motion.div
          className="glass rounded-2xl p-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
        >
          <div className="text-xs text-white/40 flex items-center gap-1.5 mb-3">
            <Database className="w-3 h-3" /> Engines
          </div>
          <div className="grid grid-cols-4 gap-2">
            {engineEntries.length > 0
              ? engineEntries.map(([name, status]) => (
                  <div key={name} className="flex flex-col items-center gap-1">
                    <StatusDot status={status} size="md" />
                    <span className="text-[8px] text-white/30 truncate w-full text-center capitalize">
                      {name.slice(0, 4)}
                    </span>
                  </div>
                ))
              : Array.from({ length: 7 }).map((_, i) => (
                  <div key={i} className="flex flex-col items-center gap-1">
                    <div className="w-3 h-3 rounded-full bg-white/10 animate-pulse" />
                    <div className="w-6 h-1.5 rounded bg-white/5 animate-pulse" />
                  </div>
                ))}
          </div>
        </motion.div>

        {/* Compliance Widget */}
        <motion.div
          className="glass rounded-2xl p-4"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="text-xs text-white/40 flex items-center gap-1.5 mb-2">
            <Shield className="w-3 h-3" /> Compliance
          </div>
          <div className="flex items-center gap-2">
            {['FedRAMP', 'SOC2', 'HIPAA', 'PCI'].map((fw) => (
              <span
                key={fw}
                className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium"
              >
                {fw}
              </span>
            ))}
          </div>
          <div className="mt-2 text-xs text-white/50">All frameworks certified</div>
        </motion.div>
      </div>
    </div>
  );
}
