'use client';

import { useTranslation } from '@/lib/i18n';
import { Globe } from 'lucide-react';

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { language, setLanguage, languages } = useTranslation();

  return (
    <div className="relative flex items-center gap-1.5">
      <Globe className="w-3.5 h-3.5 text-white/30 shrink-0" />
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value as typeof language)}
        className="bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white/60 appearance-none focus:outline-none cursor-pointer hover:bg-white/10 transition pr-6"
        style={{ backgroundImage: 'none' }}
      >
        {languages.map((lang) => (
          <option key={lang.code} value={lang.code}>
            {compact ? lang.nativeName : `${lang.nativeName} (${lang.name})`}
          </option>
        ))}
      </select>
    </div>
  );
}
