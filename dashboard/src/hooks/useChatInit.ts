/**
 * Initialization hook — loads agents, models, provider health, and sidebar data.
 * Runs once on mount.
 */
import { useEffect } from 'react';
import { useChatStore } from './useChatStore';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';

export function useChatInit() {
  const {
    setAgents, setAgentsLoaded, setSelectedAgent,
    setModels, setProviderHealth,
  } = useChatStore();

  const loadSidebar = useSidebarLoader();

  useEffect(() => {
    // Load agents
    api.getAgents()
      .then((agents) => {
        setAgents(agents);
        setAgentsLoaded(true);
        if (agents.length > 0) {
          const nova = agents.find((a) => a.agent_id === 'NOVA');
          setSelectedAgent(nova || agents[0]);
        }
      })
      .catch((err) => {
        setAgentsLoaded(true);
        toast.apiError('Load agents', err);
      });

    // Load models
    api.getModels()
      .then(setModels)
      .catch((err) => toast.apiError('Load models', err));

    // Load provider health
    api.getProviderHealth()
      .then(setProviderHealth)
      .catch((err) => toast.apiError('Load provider health', err));

    // Load sidebar
    loadSidebar();
  }, []);
}

/** Reusable sidebar loader — used in init and after mutations */
export function useSidebarLoader() {
  const { setSessions, setGroups } = useChatStore();

  return () => {
    api.getChatSessions()
      .then((data) => setSessions(data.sessions || []))
      .catch((err) => toast.apiError('Load sessions', err));
    api.getChatGroups()
      .then((data) => setGroups(data.groups || []))
      .catch((err) => toast.apiError('Load groups', err));
  };
}
