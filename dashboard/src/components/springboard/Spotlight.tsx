'use client';

import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Search, X } from 'lucide-react';
import { APPS, type AppDefinition } from '@/lib/constants';
import { useAppStore } from '@/stores/app-store';

interface SpotlightProps {
  onAppOpen: (app: AppDefinition) => void;
}

export function Spotlight({ onAppOpen }: SpotlightProps) {
  const { spotlightOpen, closeSpotlight } = useAppStore();
  const [query, setQuery] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const results = query.trim()
    ? APPS.filter(
        (a) =>
          a.name.toLowerCase().includes(query.toLowerCase()) ||
          a.description.toLowerCase().includes(query.toLowerCase())
      )
    : [];

  useEffect(() => {
    if (spotlightOpen) {
      setQuery('');
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [spotlightOpen]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        useAppStore.getState().toggleSpotlight();
      }
      if (e.key === 'Escape') closeSpotlight();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [closeSpotlight]);

  return (
    <AnimatePresence>
      {spotlightOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={closeSpotlight}
          />
          <motion.div
            className="fixed top-[15%] left-1/2 z-[70] w-[90%] max-w-lg -translate-x-1/2"
            initial={{ opacity: 0, y: -30, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          >
            <div className="glass-heavy rounded-2xl overflow-hidden shadow-2xl">
              <div className="flex items-center gap-3 px-4 py-3 border-b border-white/10">
                <Search className="w-5 h-5 text-white/40 shrink-0" />
                <input
                  ref={inputRef}
                  type="text"
                  placeholder="Search modules..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="flex-1 bg-transparent outline-none text-white placeholder-white/30 text-base"
                />
                <button onClick={closeSpotlight} className="text-white/40 hover:text-white/70">
                  <X className="w-4 h-4" />
                </button>
              </div>

              {results.length > 0 && (
                <div className="max-h-64 overflow-y-auto py-1">
                  {results.map((app) => {
                    const Icon = app.icon;
                    return (
                      <button
                        key={app.id}
                        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/5 transition-colors text-left"
                        onClick={() => {
                          closeSpotlight();
                          onAppOpen(app);
                        }}
                      >
                        <div
                          className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0"
                          style={{ background: `${app.color}33` }}
                        >
                          <Icon className="w-4.5 h-4.5" style={{ color: app.color }} />
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-white">{app.name}</div>
                          <div className="text-xs text-white/40 truncate">{app.description}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}

              {query.trim() && results.length === 0 && (
                <div className="px-4 py-6 text-center text-white/30 text-sm">No results</div>
              )}

              {!query.trim() && (
                <div className="px-4 py-4 text-center text-white/20 text-xs">
                  Type to search modules &middot; <kbd className="px-1.5 py-0.5 rounded bg-white/10 text-white/40">Ctrl+K</kbd>
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
