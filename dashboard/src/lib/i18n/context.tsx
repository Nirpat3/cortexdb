'use client';

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from 'react';
import type { Translations, LanguageCode } from './types';
import { SUPPORTED_LANGUAGES } from './types';
import { en } from './translations/en';

// Lazy-loaded translation modules
const translationLoaders: Record<string, () => Promise<{ default: Translations }>> = {
  zh: () => import('./translations/zh').then(m => ({ default: m.zh })),
  hi: () => import('./translations/hi').then(m => ({ default: m.hi })),
  es: () => import('./translations/es').then(m => ({ default: m.es })),
  fr: () => import('./translations/fr').then(m => ({ default: m.fr })),
  ar: () => import('./translations/ar').then(m => ({ default: m.ar })),
  bn: () => import('./translations/bn').then(m => ({ default: m.bn })),
  pt: () => import('./translations/pt').then(m => ({ default: m.pt })),
  ru: () => import('./translations/ru').then(m => ({ default: m.ru })),
  ja: () => import('./translations/ja').then(m => ({ default: m.ja })),
};

interface I18nContextValue {
  language: LanguageCode;
  setLanguage: (code: LanguageCode) => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  dir: 'ltr' | 'rtl';
  languages: typeof SUPPORTED_LANGUAGES;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function getNestedValue(obj: Record<string, unknown>, path: string): string | undefined {
  const keys = path.split('.');
  let current: unknown = obj;
  for (const key of keys) {
    if (current == null || typeof current !== 'object') return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === 'string' ? current : undefined;
}

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{\{(\w+)\}\}/g, (_, key) => String(params[key] ?? `{{${key}}}`));
}

const STORAGE_KEY = 'cortexdb-language';

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<LanguageCode>('en');
  const [translations, setTranslations] = useState<Translations>(en);

  // Load saved language on mount
  useEffect(() => {
    const saved = localStorage.getItem(STORAGE_KEY) as LanguageCode | null;
    if (saved && SUPPORTED_LANGUAGES.some(l => l.code === saved)) {
      setLanguageState(saved);
      if (saved !== 'en') {
        loadTranslation(saved);
      }
    }
  }, []);

  const loadTranslation = async (code: LanguageCode) => {
    if (code === 'en') {
      setTranslations(en);
      return;
    }
    const loader = translationLoaders[code];
    if (loader) {
      try {
        const module = await loader();
        setTranslations(module.default);
      } catch {
        // Fallback to English
        setTranslations(en);
      }
    }
  };

  const setLanguage = useCallback((code: LanguageCode) => {
    setLanguageState(code);
    localStorage.setItem(STORAGE_KEY, code);
    loadTranslation(code);
  }, []);

  const t = useCallback((key: string, params?: Record<string, string | number>): string => {
    const value = getNestedValue(translations as unknown as Record<string, unknown>, key);
    if (value) return interpolate(value, params);
    // Fallback to English
    const fallback = getNestedValue(en as unknown as Record<string, unknown>, key);
    if (fallback) return interpolate(fallback, params);
    // Return key itself as last resort
    return key;
  }, [translations]);

  const langConfig = SUPPORTED_LANGUAGES.find(l => l.code === language);
  const dir = (langConfig?.dir ?? 'ltr') as 'ltr' | 'rtl';

  return (
    <I18nContext.Provider value={{ language, setLanguage, t, dir, languages: SUPPORTED_LANGUAGES }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useTranslation() {
  const ctx = useContext(I18nContext);
  if (!ctx) {
    // Outside provider — return English fallback
    return {
      language: 'en' as LanguageCode,
      setLanguage: () => {},
      t: (key: string) => {
        const val = getNestedValue(en as unknown as Record<string, unknown>, key);
        return val ?? key;
      },
      dir: 'ltr' as const,
      languages: SUPPORTED_LANGUAGES,
    };
  }
  return ctx;
}
