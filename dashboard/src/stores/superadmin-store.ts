import { create } from 'zustand';

const ONBOARDING_VERSION = 'v1';

interface SuperAdminState {
  authenticated: boolean;
  token: string;
  onboardingCompleted: boolean;
  login: (token: string) => void;
  logout: () => void;
  checkSession: () => boolean;
  completeOnboarding: () => void;
  resetOnboarding: () => void;
}

export const useSuperAdminStore = create<SuperAdminState>((set) => ({
  authenticated: typeof window !== 'undefined' ? !!sessionStorage.getItem('sa_token') : false,
  token: typeof window !== 'undefined' ? sessionStorage.getItem('sa_token') ?? '' : '',
  onboardingCompleted: typeof window !== 'undefined'
    ? localStorage.getItem('sa_onboarding_completed') === ONBOARDING_VERSION
    : true,

  login: (token: string) => {
    sessionStorage.setItem('sa_token', token);
    set({ authenticated: true, token });
  },

  logout: () => {
    sessionStorage.removeItem('sa_token');
    set({ authenticated: false, token: '' });
  },

  checkSession: () => {
    const token = sessionStorage.getItem('sa_token');
    if (!token) {
      set({ authenticated: false, token: '' });
      return false;
    }
    return true;
  },

  completeOnboarding: () => {
    localStorage.setItem('sa_onboarding_completed', ONBOARDING_VERSION);
    set({ onboardingCompleted: true });
  },

  resetOnboarding: () => {
    localStorage.removeItem('sa_onboarding_completed');
    set({ onboardingCompleted: false });
  },
}));
