'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  Store, Search, ToggleLeft, ToggleRight, Package, Shield, BarChart2,
  Globe, Code, Link, Lock, DollarSign, Hexagon, FileCode, MessageSquare,
  Smartphone, Database, RefreshCw, ChevronRight, Clock, Users, Share2,
  Crosshair, ClipboardCheck, Info, Sparkles, ShoppingBag, GitBranch,
  MessageCircle, Zap, Mic, ShieldCheck, KeyRound, Workflow, LayoutDashboard,
  RadioTower, Container, Palette,
} from 'lucide-react';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';

const ICON_MAP: Record<string, React.ElementType> = {
  users: Users,
  'share-2': Share2,
  'refresh-cw': RefreshCw,
  code: Code,
  hexagon: Hexagon,
  'file-code': FileCode,
  link: Link,
  shield: Shield,
  smartphone: Smartphone,
  'message-square': MessageSquare,
  'message-circle': MessageCircle,
  'clipboard-check': ClipboardCheck,
  lock: Lock,
  'bar-chart-2': BarChart2,
  'dollar-sign': DollarSign,
  globe: Globe,
  package: Package,
  database: Database,
  sparkles: Sparkles,
  'shopping-bag': ShoppingBag,
  'git-branch': GitBranch,
  zap: Zap,
  mic: Mic,
  'shield-check': ShieldCheck,
  'key-round': KeyRound,
  workflow: Workflow,
  'layout-dashboard': LayoutDashboard,
  'radio-tower': RadioTower,
  container: Container,
  palette: Palette,
};

const TIER_COLORS: Record<string, string> = {
  free: 'text-green-400 bg-green-500/10 border-green-500/20',
  pro: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  enterprise: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
};

const CATEGORY_LABELS: Record<string, string> = {
  core: 'Core',
  sdk: 'SDKs',
  integration: 'Integrations',
  security: 'Security',
  analytics: 'Analytics',
  infrastructure: 'Infrastructure',
};

interface Capability {
  id: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  version: string;
  enabled: boolean;
  config: Record<string, unknown>;
  dependencies: string[];
  tier: string;
  installed_at: string | null;
  updated_at: string | null;
}

interface Stats {
  total: number;
  enabled: number;
  disabled: number;
  by_category: Record<string, { total: number; enabled: number }>;
  by_tier: Record<string, { total: number; enabled: number }>;
  coming_soon: Array<{ id: string; name: string }>;
}

export default function MarketplacePage() {
  const { t } = useTranslation();
  const [capabilities, setCapabilities] = useState<Capability[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedCap, setSelectedCap] = useState<Capability | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [capsRes, statsRes] = await Promise.all([
        superadminApi.getMarketplaceCapabilities(activeCategory || undefined),
        superadminApi.getMarketplaceStats(),
      ]);
      setCapabilities((capsRes as { capabilities: Capability[] }).capabilities || []);
      setStats(statsRes as unknown as Stats);
    } catch {
      setError('Failed to load marketplace data');
    } finally {
      setLoading(false);
    }
  }, [activeCategory]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const handleToggle = async (cap: Capability) => {
    setToggling(cap.id);
    setError(null);
    try {
      if (cap.enabled) {
        await superadminApi.disableCapability(cap.id);
      } else {
        await superadminApi.enableCapability(cap.id);
      }
      await fetchData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Toggle failed';
      setError(msg);
    } finally {
      setToggling(null);
    }
  };

  const filtered = searchQuery
    ? capabilities.filter(c =>
        c.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        c.description.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : capabilities;

  const grouped = filtered.reduce<Record<string, Capability[]>>((acc, cap) => {
    if (!acc[cap.category]) acc[cap.category] = [];
    acc[cap.category].push(cap);
    return acc;
  }, {});

  const isComingSoon = (cap: Capability) => cap.config?.status === 'coming_soon';

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="w-6 h-6 animate-spin text-white/30" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center">
            <Store className="w-5 h-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold">{t('marketplace.title')}</h1>
            <p className="text-xs text-white/40">{t('marketplace.subtitle')}</p>
          </div>
        </div>
        <button onClick={fetchData} className="glass px-3 py-1.5 rounded-lg text-xs text-white/60 hover:text-white/80 transition flex items-center gap-1.5">
          <RefreshCw className="w-3.5 h-3.5" /> {t('common.refresh')}
        </button>
      </div>

      {/* Stats Row */}
      {stats && (
        <div className="grid grid-cols-4 gap-3">
          <div className="glass rounded-xl p-4 text-center">
            <div className="text-2xl font-bold">{stats.total}</div>
            <div className="text-xs text-white/40">{t('marketplace.totalCapabilities')}</div>
          </div>
          <div className="glass rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-green-400">{stats.enabled}</div>
            <div className="text-xs text-white/40">{t('common.enabled')}</div>
          </div>
          <div className="glass rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-white/40">{stats.disabled}</div>
            <div className="text-xs text-white/40">{t('common.disabled')}</div>
          </div>
          <div className="glass rounded-xl p-4 text-center">
            <div className="text-2xl font-bold text-amber-400">{stats.coming_soon.length}</div>
            <div className="text-xs text-white/40">{t('marketplace.comingSoon')}</div>
          </div>
        </div>
      )}

      {/* Search + Category Filters */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t('marketplace.searchPlaceholder')}
            className="w-full glass rounded-xl pl-10 pr-4 py-2.5 text-sm bg-white/5 border border-white/10 focus:border-indigo-500/50 focus:outline-none transition"
          />
        </div>
        <div className="flex gap-1">
          <button
            onClick={() => setActiveCategory(null)}
            className={`px-3 py-2 rounded-lg text-xs transition ${
              !activeCategory ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
            }`}
          >
            {t('common.all')}
          </button>
          {Object.entries(CATEGORY_LABELS).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setActiveCategory(key === activeCategory ? null : key)}
              className={`px-3 py-2 rounded-lg text-xs transition ${
                activeCategory === key ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="glass rounded-xl p-3 border border-red-500/20 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Capability Grid */}
      {Object.entries(grouped).map(([category, caps]) => (
        <div key={category} className="space-y-3">
          <h2 className="text-sm font-semibold text-white/60 uppercase tracking-wider">
            {CATEGORY_LABELS[category] || category}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {caps.map((cap) => {
              const IconComponent = ICON_MAP[cap.icon] || Package;
              const comingSoon = isComingSoon(cap);
              return (
                <div
                  key={cap.id}
                  className={`glass rounded-xl p-4 transition hover:bg-white/5 cursor-pointer ${
                    comingSoon ? 'opacity-60' : ''
                  }`}
                  onClick={() => setSelectedCap(selectedCap?.id === cap.id ? null : cap)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-3">
                      <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                        cap.enabled ? 'bg-green-500/20' : 'bg-white/5'
                      }`}>
                        <IconComponent className={`w-4.5 h-4.5 ${
                          cap.enabled ? 'text-green-400' : 'text-white/40'
                        }`} />
                      </div>
                      <div>
                        <div className="text-sm font-medium flex items-center gap-2">
                          {cap.name}
                          {comingSoon && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                              {t('marketplace.comingSoon')}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-2 mt-0.5">
                          <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${TIER_COLORS[cap.tier]}`}>
                            {cap.tier}
                          </span>
                          <span className="text-[10px] text-white/30">v{cap.version}</span>
                        </div>
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleToggle(cap); }}
                      disabled={toggling === cap.id || comingSoon}
                      className="transition disabled:opacity-40"
                    >
                      {cap.enabled ? (
                        <ToggleRight className="w-7 h-7 text-green-400" />
                      ) : (
                        <ToggleLeft className="w-7 h-7 text-white/20" />
                      )}
                    </button>
                  </div>

                  <p className="text-xs text-white/50 leading-relaxed">{cap.description}</p>

                  {comingSoon && cap.config?.eta ? (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-amber-400/70">
                      <Clock className="w-3 h-3" />
                      ETA: {String(cap.config.eta)}
                    </div>
                  ) : null}

                  {cap.dependencies.length > 0 && (
                    <div className="mt-2 flex items-center gap-1 text-[10px] text-white/30">
                      <Link className="w-3 h-3" />
                      Requires: {cap.dependencies.join(', ')}
                    </div>
                  )}

                  {/* Expanded Detail */}
                  {selectedCap?.id === cap.id && (
                    <div className="mt-3 pt-3 border-t border-white/5 space-y-2">
                      <div className="flex items-center gap-2 text-xs text-white/40">
                        <Info className="w-3.5 h-3.5" />
                        <span>{t('marketplace.capabilityId')}: <span className="text-white/60 font-mono">{cap.id}</span></span>
                      </div>
                      {cap.installed_at && (
                        <div className="flex items-center gap-2 text-xs text-white/40">
                          <Clock className="w-3.5 h-3.5" />
                          <span>{t('marketplace.installed')}: {new Date(cap.installed_at).toLocaleDateString()}</span>
                        </div>
                      )}
                      {Object.keys(cap.config).length > 0 && cap.config.status !== 'coming_soon' && (
                        <div className="text-xs text-white/40">
                          <span className="text-white/50">{t('marketplace.config')}:</span>
                          <pre className="mt-1 text-[10px] text-white/30 bg-white/5 rounded p-2 overflow-auto">
                            {JSON.stringify(cap.config, null, 2)}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {filtered.length === 0 && (
        <div className="text-center py-12 text-white/30 text-sm">
          {searchQuery ? t('marketplace.noResults') : t('common.noData')}
        </div>
      )}
    </div>
  );
}
