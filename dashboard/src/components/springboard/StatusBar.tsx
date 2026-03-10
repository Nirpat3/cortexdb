'use client';

import { useEffect, useState } from 'react';
import { Wifi, WifiOff, Database } from 'lucide-react';
import { StatusDot } from '@/components/shared/StatusDot';
import { useHealth } from '@/lib/hooks/useHealth';
import { format } from 'date-fns';

export function StatusBar() {
  const [time, setTime] = useState('');
  const { data, error } = useHealth();

  useEffect(() => {
    const update = () => setTime(format(new Date(), 'h:mm a'));
    update();
    const interval = setInterval(update, 10000);
    return () => clearInterval(interval);
  }, []);

  const isConnected = !!data && !error;
  const overallStatus = data?.status || 'unknown';

  return (
    <div className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 py-2 text-xs text-white/70">
      <div className="flex items-center gap-3">
        <Database className="w-3.5 h-3.5 text-white/50" />
        <span className="font-medium text-white/90">CortexDB</span>
        <span className="text-white/30">v4.0</span>
      </div>

      <div className="font-medium text-white/90">{time}</div>

      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1.5">
          <StatusDot status={overallStatus} size="sm" pulse={isConnected} />
          <span className="capitalize">{overallStatus}</span>
        </div>
        {isConnected ? (
          <Wifi className="w-3.5 h-3.5" />
        ) : (
          <WifiOff className="w-3.5 h-3.5 text-red-400" />
        )}
      </div>
    </div>
  );
}
