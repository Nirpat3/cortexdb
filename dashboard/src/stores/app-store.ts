import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { DEFAULT_DOCK_IDS } from '@/lib/constants';

interface AppStore {
  dockIds: string[];
  wallpaper: string;
  spotlightOpen: boolean;
  setDockIds: (ids: string[]) => void;
  setWallpaper: (wp: string) => void;
  toggleSpotlight: () => void;
  closeSpotlight: () => void;
}

export const useAppStore = create<AppStore>()(
  persist(
    (set) => ({
      dockIds: DEFAULT_DOCK_IDS,
      wallpaper: 'aurora',
      spotlightOpen: false,
      setDockIds: (ids) => set({ dockIds: ids }),
      setWallpaper: (wp) => set({ wallpaper: wp }),
      toggleSpotlight: () => set((s) => ({ spotlightOpen: !s.spotlightOpen })),
      closeSpotlight: () => set({ spotlightOpen: false }),
    }),
    { name: 'cortexdb-app-store' }
  )
);
