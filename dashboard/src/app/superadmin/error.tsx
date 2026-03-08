'use client';

import { useEffect } from 'react';
import { AlertTriangle, RotateCcw, LayoutDashboard } from 'lucide-react';
import { useRouter } from 'next/navigation';

export default function SuperAdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const router = useRouter();

  useEffect(() => {
    console.error('[CortexDB SuperAdmin] Error:', error);
  }, [error]);

  return (
    <div className="flex items-center justify-center min-h-[60vh] p-4">
      <div className="glass-heavy rounded-2xl p-8 w-full max-w-lg text-center">
        <div className="w-14 h-14 rounded-xl bg-critical/20 flex items-center justify-center mx-auto mb-5">
          <AlertTriangle className="w-7 h-7 text-critical" />
        </div>

        <h1 className="text-xl font-bold text-white mb-2">SuperAdmin Error</h1>
        <p className="text-sm text-white/50 mb-2 leading-relaxed">
          An error occurred while loading this section of the admin panel.
        </p>
        <p className="text-xs text-white/30 font-mono mb-6 break-all">
          {error.message || 'Unknown error'}
        </p>

        {error.digest && (
          <p className="text-[10px] text-white/20 font-mono mb-6">
            Error ID: {error.digest}
          </p>
        )}

        <div className="flex items-center justify-center gap-3">
          <button
            onClick={reset}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-cortex-blue/20 text-cortex-blue hover:bg-cortex-blue/30 transition text-sm font-medium"
          >
            <RotateCcw className="w-4 h-4" />
            Try Again
          </button>
          <button
            onClick={() => router.push('/superadmin')}
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 transition text-sm font-medium"
          >
            <LayoutDashboard className="w-4 h-4" />
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
