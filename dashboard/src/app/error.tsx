'use client';

import { useEffect } from 'react';
import { AlertTriangle, RotateCcw, Home } from 'lucide-react';
import Link from 'next/link';

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('[CortexDB] Unhandled error:', error);
  }, [error]);

  return (
    <div className="min-h-screen bg-black flex items-center justify-center p-4">
      <div className="glass-heavy rounded-2xl p-8 w-full max-w-lg text-center">
        <div className="w-14 h-14 rounded-xl bg-critical/20 flex items-center justify-center mx-auto mb-5">
          <AlertTriangle className="w-7 h-7 text-critical" />
        </div>

        <h1 className="text-xl font-bold text-white mb-2">Something went wrong</h1>
        <p className="text-sm text-white/50 mb-6 leading-relaxed">
          {error.message || 'An unexpected error occurred while loading this page.'}
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
          <Link
            href="/"
            className="flex items-center gap-2 px-5 py-2.5 rounded-xl bg-white/5 text-white/60 hover:bg-white/10 hover:text-white/80 transition text-sm font-medium"
          >
            <Home className="w-4 h-4" />
            Go Home
          </Link>
        </div>
      </div>
    </div>
  );
}
