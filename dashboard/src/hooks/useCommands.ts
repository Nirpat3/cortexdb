/**
 * Slash command handler.
 *
 * Processes /help, /cli, /sh, /agents, /agent, /perms, etc.
 * Returns true if the input was a command (consumed), false otherwise.
 */
import { useCallback } from 'react';
import { useChatStore } from './useChatStore';
import { useChatSessions } from './useChatSessions';
import type { AgentOption } from '@/lib/api';

export function useCommands(sendStreaming: (text: string) => void) {
  const store = useChatStore();
  const { startNewChat, exportChat, condense } = useChatSessions();

  const handleCommand = useCallback(
    (raw: string): boolean => {
      const { agents, selectedAgent, perms, cliMode } = useChatStore.getState();
      const parts = raw.trim().split(/\s+/);
      const cmd = parts[0].toLowerCase();

      if (cmd === '/help') {
        store.addSystemMessage(
          'Commands:\n' +
            '  /agents          List all agents\n' +
            '  /agent <id>      Switch to agent\n' +
            '  /task <desc>     Create a task from chat\n' +
            '  /db <query>      Query the database\n' +
            '  /perms           Show permissions\n' +
            '  /grant|/deny <p> Set permissions\n' +
            '  /save            Save permissions\n' +
            '  /new             New conversation\n' +
            '  /export          Export chat\n' +
            '  /condense        Summarize old messages\n' +
            '  /clear           Clear messages\n' +
            '  /cli             Toggle CLI mode\n' +
            '  /sh <cmd>        Run shell command\n' +
            '  !<cmd>           Run shell command\n' +
            '  @Agent           Mention/delegate',
        );
        return true;
      }

      if (cmd === '/cli') {
        const next = !cliMode;
        store.setCliMode(next);
        // NOTE: do NOT auto-escalate permissions — server enforces
        store.addSystemMessage(next ? 'CLI mode ON.' : 'CLI mode OFF.');
        return true;
      }

      if (cmd === '/sh' || raw.startsWith('!')) {
        const shellCmd = cmd === '/sh' ? parts.slice(1).join(' ') : raw.slice(1).trim();
        if (!shellCmd) {
          store.addSystemMessage('Usage: /sh <command>');
          return true;
        }
        // Send as a code block — no client-side perm escalation
        sendStreaming(`Run this command and show the output:\n\`\`\`\n${shellCmd}\n\`\`\``);
        return true;
      }

      if (cmd === '/new') { startNewChat(); return true; }
      if (cmd === '/export') { exportChat(); return true; }
      if (cmd === '/condense') { condense(); return true; }

      if (cmd === '/agents') {
        const grouped: Record<string, AgentOption[]> = {};
        for (const a of agents) {
          (grouped[a.tier || 'other'] = grouped[a.tier || 'other'] || []).push(a);
        }
        let msg = 'Available agents:\n';
        for (const [tier, list] of Object.entries(grouped).sort()) {
          msg += `\n  [${tier.toUpperCase()}]\n`;
          for (const a of list) {
            msg += `    ${a.agent_id} -- ${a.name}${a.agent_id === selectedAgent?.agent_id ? ' (active)' : ''}\n`;
          }
        }
        store.addSystemMessage(msg.trimEnd());
        return true;
      }

      if (cmd === '/agent') {
        const id = parts[1];
        if (!id) {
          store.addSystemMessage(selectedAgent ? `Current: ${selectedAgent.agent_id}` : 'No agent selected.');
          return true;
        }
        const found = agents.find(
          (a) => a.agent_id.toLowerCase() === id.toLowerCase() || a.agent_id.toLowerCase().endsWith(id.toLowerCase()),
        );
        if (found) {
          store.setSelectedAgent(found);
          store.addSystemMessage(`Switched to ${found.name}`);
        } else {
          store.addSystemMessage(`Not found: ${id}`);
        }
        return true;
      }

      if (cmd === '/perms') {
        store.addSystemMessage(
          `Permissions (hints — server enforces):\n${Object.entries(perms)
            .map(([k, v]) => `  ${k.padEnd(10)} ${v ? 'ALLOW' : 'DENY'}`)
            .join('\n')}`,
        );
        return true;
      }

      if (cmd === '/grant' || cmd === '/deny') {
        const p = parts[1]?.toLowerCase();
        const v = cmd === '/grant';
        if (p === 'all') store.setPerms({ read: v, write: v, exec: v, network: v });
        else if (p && p in perms) store.setPerms((prev) => ({ ...prev, [p]: v }));
        store.addSystemMessage(`${v ? 'Granted' : 'Denied'} ${p || 'unknown'} permission hint.`);
        return true;
      }

      if (cmd === '/clear') { store.clearMessages(); return true; }

      if (cmd === '/task') {
        const rest = parts.slice(1).join(' ').trim();
        if (!rest || rest === 'help') {
          store.addSystemMessage(
            'Usage: /task <description>\nExamples:\n  /task add email organization and assign to nova\n  /task create daily report with priority high',
          );
          return true;
        }
        sendStreaming(
          `Create a task based on this request. Use the create_task tool to insert it into the database. Parse the details carefully.\n\nRequest: ${rest}`,
        );
        return true;
      }

      if (cmd === '/db') {
        const rest = parts.slice(1).join(' ').trim();
        if (!rest || rest === 'help') {
          store.addSystemMessage('Usage: /db <natural language query>\nExamples:\n  /db show all active tasks');
          return true;
        }
        sendStreaming(
          `Use the query_database tool to answer this database question. Write a safe SELECT query.\n\nQuestion: ${rest}`,
        );
        return true;
      }

      if (cmd.startsWith('/')) {
        store.addSystemMessage(`Unknown: ${cmd}. Try /help`);
        return true;
      }

      return false;
    },
    [sendStreaming, startNewChat, exportChat, condense],
  );

  return handleCommand;
}
