#!/usr/bin/env python3
"""
CortexDB CLI Chat — Talk to SuperAdmin agents from your terminal.

Usage:
    python cli_chat.py                    # interactive agent picker
    python cli_chat.py SA-EXEC-001       # chat with a specific agent
    python cli_chat.py --list            # list all agents
    python cli_chat.py --help            # show help

Environment:
    CORTEXDB_URL       Base URL (default: http://localhost:5400)
    CORTEXDB_TOKEN     SuperAdmin session token (or login interactively)
    CORTEXDB_PASSPHRASE  Auto-login passphrase (skips prompt)
"""

import argparse
import getpass
import json
import os
import sys
import urllib.request
import urllib.error

BASE_URL = os.environ.get("CORTEXDB_URL", "http://localhost:5400")
TOKEN = os.environ.get("CORTEXDB_TOKEN", "")

# ── Colors ──

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"


def colored(text: str, color: str) -> str:
    return f"{color}{text}{C.RESET}"


# ── API helpers ──

def api(method: str, path: str, body: dict = None, token: str = "") -> dict:
    """Make an API call to CortexDB."""
    url = f"{BASE_URL}/api{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-SuperAdmin-Token"] = token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else str(e)
        raise SystemExit(f"{colored('API Error', C.RED)} ({e.code}): {error_body}")
    except urllib.error.URLError as e:
        raise SystemExit(f"{colored('Connection failed', C.RED)}: {e.reason}\nIs CortexDB running at {BASE_URL}?")


def login_interactive() -> str:
    """Login and return a session token."""
    passphrase = os.environ.get("CORTEXDB_PASSPHRASE", "")
    if not passphrase:
        passphrase = getpass.getpass(colored("SuperAdmin passphrase: ", C.YELLOW))
    result = api("POST", "/v1/superadmin/login", {"passphrase": passphrase})
    return result.get("token", "")


def get_agents(token: str) -> list:
    """Get all agents."""
    result = api("GET", "/v1/superadmin/team", token=token)
    agents = result.get("agents", [])
    if not agents and isinstance(result, list):
        agents = result
    return agents


def chat(agent_id: str, message: str, token: str, session_id: str = "") -> dict:
    """Send a chat message."""
    body = {"message": message}
    if session_id:
        body["session_id"] = session_id
    return api("POST", f"/v1/superadmin/chat/{agent_id}", body, token=token)


# ── UI ──

def print_banner():
    print(colored("""
╔══════════════════════════════════════════╗
║     CortexDB CLI Chat                   ║
║     Talk to your agents from terminal    ║
╚══════════════════════════════════════════╝""", C.CYAN))


def list_agents(agents: list):
    """Print agent roster."""
    print(f"\n{colored('Available Agents', C.BOLD)} ({len(agents)})\n")
    depts: dict = {}
    for a in agents:
        dept = a.get("department", "unknown")
        depts.setdefault(dept, []).append(a)

    for dept in sorted(depts):
        print(colored(f"  {dept.upper()}", C.YELLOW))
        for a in depts[dept]:
            state = a.get("state", "idle")
            state_color = C.GREEN if state == "idle" else C.YELLOW
            print(f"    {colored(a['agent_id'], C.CYAN):40s} {a.get('name', '')[:30]:32s} {colored(state, state_color)}")
        print()


def pick_agent(agents: list) -> str:
    """Interactive agent picker."""
    list_agents(agents)
    while True:
        agent_id = input(colored("Enter agent ID (or 'q' to quit): ", C.YELLOW)).strip()
        if agent_id.lower() in ("q", "quit", "exit"):
            sys.exit(0)
        if any(a["agent_id"] == agent_id for a in agents):
            return agent_id
        # Fuzzy match
        matches = [a for a in agents if agent_id.lower() in a["agent_id"].lower()
                    or agent_id.lower() in a.get("name", "").lower()]
        if len(matches) == 1:
            return matches[0]["agent_id"]
        if matches:
            print(colored(f"  Multiple matches:", C.DIM))
            for m in matches:
                print(f"    {colored(m['agent_id'], C.CYAN)}  {m.get('name', '')}")
        else:
            print(colored("  Agent not found. Try again.", C.RED))


def chat_loop(agent_id: str, token: str, agent_name: str = ""):
    """Interactive chat loop."""
    display = agent_name or agent_id
    session_id = f"cli-{agent_id}-{os.getpid()}"

    print(f"\n{colored('Chatting with', C.DIM)} {colored(display, C.CYAN)}")
    print(colored("Type your message. Commands: /clear, /tools, /switch, /quit\n", C.DIM))

    while True:
        try:
            user_input = input(colored("You → ", C.GREEN)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]
            if cmd in ("/quit", "/q", "/exit"):
                break
            elif cmd == "/clear":
                api("DELETE", f"/v1/superadmin/chat/{agent_id}/clear", token=token)
                print(colored("  Conversation cleared.\n", C.DIM))
                continue
            elif cmd == "/tools":
                result = api("GET", "/v1/superadmin/tools", token=token)
                tools = result.get("tools", result if isinstance(result, list) else [])
                print(colored("  Available tools:", C.YELLOW))
                for t in tools:
                    params = ", ".join(p["name"] for p in t.get("parameters", []))
                    print(f"    {colored(t['name'], C.CYAN)}({params}) — {t.get('description', '')}")
                print()
                continue
            elif cmd == "/switch":
                return "switch"
            elif cmd == "/help":
                print(colored("  /clear   — Clear conversation history", C.DIM))
                print(colored("  /tools   — List available agent tools", C.DIM))
                print(colored("  /switch  — Switch to a different agent", C.DIM))
                print(colored("  /quit    — Exit chat", C.DIM))
                print()
                continue

        # Send message
        try:
            result = chat(agent_id, user_input, token, session_id)
        except SystemExit as e:
            print(colored(f"  Error: {e}", C.RED))
            continue

        response = result.get("response", "No response")
        provider = result.get("provider", "?")
        model = result.get("model", "?")
        elapsed = result.get("elapsed_ms", 0)

        print(f"\n{colored(display, C.CYAN)} → {response}")
        print(colored(f"  [{provider}/{model} · {elapsed:.0f}ms]\n", C.DIM))


def main():
    parser = argparse.ArgumentParser(description="CortexDB CLI Chat")
    parser.add_argument("agent_id", nargs="?", help="Agent ID to chat with")
    parser.add_argument("--list", "-l", action="store_true", help="List all agents")
    parser.add_argument("--url", help="CortexDB base URL")
    args = parser.parse_args()

    global BASE_URL, TOKEN
    if args.url:
        BASE_URL = args.url

    print_banner()

    # Authenticate
    if not TOKEN:
        TOKEN = login_interactive()
    print(colored("  Authenticated ✓\n", C.GREEN))

    # List mode
    if args.list:
        agents = get_agents(TOKEN)
        list_agents(agents)
        return

    agents = get_agents(TOKEN)
    if not agents:
        print(colored("No agents found.", C.RED))
        return

    # Direct agent selection or interactive picker
    agent_id = args.agent_id
    if agent_id:
        matches = [a for a in agents if a["agent_id"] == agent_id]
        if not matches:
            matches = [a for a in agents if agent_id.lower() in a["agent_id"].lower()]
        if not matches:
            print(colored(f"Agent '{agent_id}' not found.", C.RED))
            list_agents(agents)
            return
        agent_id = matches[0]["agent_id"]
        agent_name = matches[0].get("name", "")
    else:
        agent_id = pick_agent(agents)
        agent_name = next((a.get("name", "") for a in agents if a["agent_id"] == agent_id), "")

    while True:
        result = chat_loop(agent_id, TOKEN, agent_name)
        if result == "switch":
            agent_id = pick_agent(agents)
            agent_name = next((a.get("name", "") for a in agents if a["agent_id"] == agent_id), "")
        else:
            break

    print(colored("\nGoodbye!", C.CYAN))


if __name__ == "__main__":
    main()
