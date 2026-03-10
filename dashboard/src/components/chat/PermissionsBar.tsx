'use client';
import { useState } from 'react';
import { Eye, Pencil, Play, Globe, Save, Loader2 } from 'lucide-react';
import { PermToggle } from './PermToggle';
import { useChatStore } from '@/hooks/useChatStore';
import * as api from '@/lib/api';
import { toast } from '@/lib/toast';

export function PermissionsBar() {
  const { perms, setPerms, selectedAgent } = useChatStore();
  const [saving, setSaving] = useState(false);

  const savePerms = async () => {
    if (!selectedAgent) return;
    setSaving(true);
    try {
      await api.setAgentChatPermissions(selectedAgent.agent_id, perms);
      toast.success('Permission hints saved');
    } catch (err) {
      toast.apiError('Save permissions', err);
    }
    setSaving(false);
  };

  return (
    <div className="flex items-center gap-2 mb-3 flex-wrap">
      <span className="text-xs text-[var(--text-muted)] mr-1">Permission hints:</span>
      <PermToggle label="Read" icon={Eye} enabled={perms.read} onChange={(v) => setPerms((p) => ({ ...p, read: v }))} colorClass="bg-blue-500/15 text-blue-400" />
      <PermToggle label="Write" icon={Pencil} enabled={perms.write} onChange={(v) => setPerms((p) => ({ ...p, write: v }))} colorClass="bg-amber-500/15 text-amber-400" />
      <PermToggle label="Exec" icon={Play} enabled={perms.exec} onChange={(v) => setPerms((p) => ({ ...p, exec: v }))} colorClass="bg-red-500/15 text-red-400" />
      <PermToggle label="Network" icon={Globe} enabled={perms.network} onChange={(v) => setPerms((p) => ({ ...p, network: v }))} colorClass="bg-purple-500/15 text-purple-400" />
      {selectedAgent && (
        <button
          onClick={savePerms}
          disabled={saving}
          className="flex items-center gap-1 rounded-md border border-[var(--border-default)] bg-[var(--bg-elevated)] px-2 py-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] ml-1"
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Save className="h-3 w-3" />} Save
        </button>
      )}
    </div>
  );
}
