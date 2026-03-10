import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: 'var(--bg-surface)',
        elevated: 'var(--bg-elevated)',
      },
    },
  },
  plugins: [],
};
export default config;
