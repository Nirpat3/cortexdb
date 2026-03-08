'use client';

import { useState, useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import {
  Shield, Bot, Users, ClipboardList, MessageSquare, Settings, LogOut,
  LayoutDashboard, Network, ChevronLeft, Zap, Mail, ScrollText, Layers, Tag, Brain,
  MessageCircle, DollarSign, GitBranch, BookOpen, Copy, Calendar, Activity, Star,
  Crosshair, Radio, BarChart3, Bell, Play, TrendingDown, FileText, Award,
  Share2, FlaskConical, Store, Sparkles, ShoppingBag, Link, KeyRound, ShieldCheck,
  Workflow, Globe, RadioTower, Container, Palette, Mic, Code, Target,
} from 'lucide-react';
import { useSuperAdminStore } from '@/stores/superadmin-store';
import { superadminApi } from '@/lib/api';
import { useTranslation } from '@/lib/i18n';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import OnboardingWizard from '@/components/superadmin/onboarding/OnboardingWizard';

// Nav items with translation keys (labels resolved at render time)
const NAV_ITEMS = [
  { id: 'dashboard', tKey: 'nav.dashboard', icon: LayoutDashboard, path: '/superadmin' },
  { id: 'org-chart', tKey: 'nav.orgChart', icon: Network, path: '/superadmin/org-chart' },
  { id: 'agents', tKey: 'nav.agents', icon: Bot, path: '/superadmin/agents' },
  { id: 'skills', tKey: 'nav.skills', icon: Star, path: '/superadmin/skills' },
  { id: 'tasks', tKey: 'nav.tasks', icon: ClipboardList, path: '/superadmin/tasks' },
  { id: 'instructions', tKey: 'nav.instructions', icon: MessageSquare, path: '/superadmin/instructions' },
  { id: 'bus', tKey: 'nav.agentBus', icon: Mail, path: '/superadmin/bus' },
  { id: 'executor', tKey: 'nav.executor', icon: Zap, path: '/superadmin/executor' },
  { id: 'audit', tKey: 'nav.auditLog', icon: ScrollText, path: '/superadmin/audit' },
  { id: 'registry', tKey: 'nav.registry', icon: Layers, path: '/superadmin/registry' },
  { id: 'chat', tKey: 'nav.agentChat', icon: MessageCircle, path: '/superadmin/chat' },
  { id: 'collab', tKey: 'nav.collaboration', icon: Users, path: '/superadmin/collab' },
  { id: 'intelligence', tKey: 'nav.intelligence', icon: Brain, path: '/superadmin/intelligence' },
  { id: 'costs', tKey: 'nav.llmCosts', icon: DollarSign, path: '/superadmin/costs' },
  { id: 'workflows', tKey: 'nav.workflows', icon: GitBranch, path: '/superadmin/workflows' },
  { id: 'rag', tKey: 'nav.ragPipeline', icon: BookOpen, path: '/superadmin/rag' },
  { id: 'templates', tKey: 'nav.templates', icon: Copy, path: '/superadmin/templates' },
  { id: 'scheduler', tKey: 'nav.scheduler', icon: Calendar, path: '/superadmin/scheduler' },
  { id: 'health', tKey: 'nav.health', icon: Activity, path: '/superadmin/health' },
  { id: 'autonomy', tKey: 'nav.autonomy', icon: Crosshair, path: '/superadmin/autonomy' },
  { id: 'reputation', tKey: 'nav.reputation', icon: Award, path: '/superadmin/reputation' },
  { id: 'live-feed', tKey: 'nav.liveFeed', icon: Radio, path: '/superadmin/live-feed' },
  { id: 'metrics', tKey: 'nav.metrics', icon: BarChart3, path: '/superadmin/metrics' },
  { id: 'alerts', tKey: 'nav.alerts', icon: Bell, path: '/superadmin/alerts' },
  { id: 'replay', tKey: 'nav.replay', icon: Play, path: '/superadmin/replay' },
  { id: 'cost-optimizer', tKey: 'nav.costOptimizer', icon: TrendingDown, path: '/superadmin/cost-optimizer' },
  { id: 'reports', tKey: 'nav.reports', icon: FileText, path: '/superadmin/reports' },
  { id: 'knowledge', tKey: 'nav.knowledge', icon: Share2, path: '/superadmin/knowledge' },
  { id: 'simulations', tKey: 'nav.simulations', icon: FlaskConical, path: '/superadmin/simulations' },
  { id: 'marketplace', tKey: 'nav.marketplace', icon: Store, path: '/superadmin/marketplace' },
  { id: 'copilot', tKey: 'nav.copilot', icon: Sparkles, path: '/superadmin/copilot' },
  { id: 'templates-market', tKey: 'nav.templatesMarket', icon: ShoppingBag, path: '/superadmin/templates-market' },
  { id: 'graphql', tKey: 'nav.graphql', icon: GitBranch, path: '/superadmin/graphql' },
  { id: 'integrations', tKey: 'nav.integrations', icon: Link, path: '/superadmin/integrations' },
  { id: 'voice', tKey: 'nav.voice', icon: Mic, path: '/superadmin/voice' },
  { id: 'vault', tKey: 'nav.vault', icon: KeyRound, path: '/superadmin/vault' },
  { id: 'zero-trust', tKey: 'nav.zeroTrust', icon: ShieldCheck, path: '/superadmin/zero-trust' },
  { id: 'sentinel', tKey: 'nav.sentinel', icon: Target, path: '/superadmin/sentinel' },
  { id: 'pipelines-data', tKey: 'nav.pipelineBuilder', icon: Workflow, path: '/superadmin/pipelines-data' },
  { id: 'dashboards', tKey: 'nav.customDashboards', icon: LayoutDashboard, path: '/superadmin/dashboards' },
  { id: 'edge', tKey: 'nav.edge', icon: RadioTower, path: '/superadmin/edge' },
  { id: 'kubernetes', tKey: 'nav.kubernetes', icon: Container, path: '/superadmin/kubernetes' },
  { id: 'theming', tKey: 'nav.theming', icon: Palette, path: '/superadmin/theming' },
  { id: 'regions', tKey: 'nav.multiRegion', icon: Globe, path: '/superadmin/regions' },
  { id: 'sdks', tKey: 'nav.sdks', icon: Code, path: '/superadmin/sdks' },
  { id: 'version', tKey: 'nav.versioning', icon: Tag, path: '/superadmin/version' },
  { id: 'llm', tKey: 'nav.llmConfig', icon: Settings, path: '/superadmin/llm' },
];

export default function SuperAdminLayout({ children }: { children: React.ReactNode }) {
  const { authenticated, login, logout, onboardingCompleted } = useSuperAdminStore();
  const [passphrase, setPassphrase] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const { t, dir } = useTranslation();

  // Check session on mount
  useEffect(() => {
    if (authenticated) {
      superadminApi.session().catch(() => {
        logout();
      });
    }
  }, [authenticated, logout]);

  const handleLogin = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await superadminApi.login(passphrase);
      login(result.token);
      setPassphrase('');
    } catch {
      setError(t('login.errorInvalid'));
    }
    setLoading(false);
  };

  const handleLogout = async () => {
    try { await superadminApi.logout(); } catch { /* silent */ }
    logout();
    router.push('/superadmin');
  };

  // Login Gate
  if (!authenticated) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center p-4" dir={dir}>
        <div className="glass-heavy rounded-2xl p-8 w-full max-w-md">
          <div className="flex items-center justify-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-xl bg-red-500/20 flex items-center justify-center">
              <Shield className="w-6 h-6 text-red-400" />
            </div>
            <div>
              <h1 className="text-xl font-bold">{t('login.title')}</h1>
              <p className="text-xs text-white/40">{t('login.subtitle')}</p>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <label className="text-xs text-white/40 block mb-1.5">{t('login.passphraseLabel')}</label>
              <input
                type="password"
                value={passphrase}
                onChange={(e) => setPassphrase(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                placeholder={t('login.passphrasePlaceholder')}
                className="w-full glass rounded-xl px-4 py-3 text-sm bg-white/5 border border-white/10 focus:border-red-500/50 focus:outline-none transition"
                autoFocus
              />
            </div>
            {error && <div className="text-xs text-red-400">{error}</div>}
            <button
              onClick={handleLogin}
              disabled={loading || !passphrase}
              className="w-full py-3 rounded-xl bg-red-500/20 text-red-300 hover:bg-red-500/30 transition font-medium text-sm disabled:opacity-50"
            >
              {loading ? t('login.authenticating') : t('login.submit')}
            </button>
          </div>

          <div className="mt-6 pt-4 border-t border-white/5 space-y-2">
            <div className="flex justify-center">
              <LanguageSwitcher compact />
            </div>
            <p className="text-[10px] text-white/20 text-center">{t('login.footerProtected')}</p>
            <p className="text-[10px] text-white/20 text-center">{t('login.footerLockout')}</p>
          </div>
        </div>
      </div>
    );
  }

  // Onboarding wizard for first-time users
  if (!onboardingCompleted) {
    return <OnboardingWizard />;
  }

  // Authenticated Layout
  return (
    <div className="min-h-screen bg-black flex" dir={dir}>
      {/* Sidebar */}
      <aside className="w-56 glass-heavy border-r border-white/5 flex flex-col shrink-0">
        <div className="p-4 border-b border-white/5">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-red-400" />
            <div>
              <div className="text-sm font-bold">{t('login.title')}</div>
              <div className="text-[10px] text-white/30">{t('login.subtitle')}</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.path;
            return (
              <button key={item.id} onClick={() => router.push(item.path)}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition ${
                  active ? 'bg-white/10 text-white' : 'text-white/50 hover:text-white/80 hover:bg-white/5'
                }`}>
                <item.icon className="w-4 h-4 shrink-0" />
                {t(item.tKey)}
              </button>
            );
          })}
        </nav>

        <div className="p-2 border-t border-white/5 space-y-0.5">
          <div className="px-3 py-2">
            <LanguageSwitcher compact />
          </div>
          <button onClick={() => router.push('/')}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-white/40 hover:text-white/70 hover:bg-white/5 transition">
            <ChevronLeft className="w-4 h-4" /> {t('nav.backToDashboard')}
          </button>
          <button onClick={handleLogout}
            className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-red-400/60 hover:text-red-400 hover:bg-red-500/10 transition">
            <LogOut className="w-4 h-4" /> {t('nav.logout')}
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto p-6 max-h-screen">
        {children}
      </main>
    </div>
  );
}
