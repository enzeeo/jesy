"""
One-shot wiring for a demo session.

Run AFTER `ngrok start --all` is already up in another terminal. This script:

  1. Polls ngrok's local API at 127.0.0.1:4040 to discover the two tunnels
     (one for backend :8000, one for caller-ui :5173).
  2. Updates caller-ui/.env.local with the backend URL (preserving other
     vars; only NEXT_PUBLIC_BACKEND_URL is touched).
  3. Re-pushes the agent if the backend URL changed since last run.
  4. Prints the caller URL prominently so you can type it on your phone.

  $ uv run python scripts/demo_setup.py
  $ uv run python scripts/demo_setup.py --no-push       # skip agents-push
  $ uv run python scripts/demo_setup.py --backend-port 8000 --caller-port 5173

If ngrok isn't running, prints clear instructions and exits non-zero.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CALLER_ENV_PATH = REPO_ROOT / "caller-ui" / ".env.local"
CALLER_ENV_EXAMPLE_PATH = REPO_ROOT / "caller-ui" / ".env.example"
AGENTS_INDEX_PATH = REPO_ROOT / "agents" / "elevenlabs" / "agents.json"
NGROK_API = "http://127.0.0.1:4040/api/tunnels"
NGROK_API_TIMEOUT_S = 3
NGROK_POLL_RETRIES = 5

BACKEND_URL_VAR = "NEXT_PUBLIC_BACKEND_URL"
AGENT_ID_VAR = "NEXT_PUBLIC_ELEVENLABS_AGENT_ID"


def info(msg: str) -> None:
    print(f"[setup] {msg}")


def fail(msg: str, code: int = 1) -> None:
    print(f"[setup] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def fetch_ngrok_tunnels() -> list[dict]:
    """Hit ngrok's local API. Returns the `tunnels` array or raises on failure."""
    last_err: Exception | None = None
    for attempt in range(NGROK_POLL_RETRIES):
        try:
            req = urllib.request.Request(NGROK_API)
            with urllib.request.urlopen(req, timeout=NGROK_API_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode())
                return data.get("tunnels", [])
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as e:
            last_err = e
            if attempt + 1 < NGROK_POLL_RETRIES:
                time.sleep(0.5)
    fail(
        "could not reach ngrok at http://127.0.0.1:4040. Is ngrok running?\n"
        "  Start it in another terminal:  ngrok start --all\n"
        f"  Last error: {last_err}"
    )
    return []  # unreachable


def find_tunnel_for_port(tunnels: list[dict], port: int) -> str | None:
    """
    Return the https public_url of the tunnel pointed at localhost:<port>,
    or None if no match. Prefers https over http.
    """
    matches = [
        t for t in tunnels
        if t.get("config", {}).get("addr", "").endswith(f":{port}")
        or t.get("config", {}).get("addr") == f"http://localhost:{port}"
        or t.get("config", {}).get("addr") == f"https://localhost:{port}"
    ]
    if not matches:
        return None

    https = [t for t in matches if t.get("public_url", "").startswith("https://")]
    chosen = https[0] if https else matches[0]
    return chosen["public_url"]


def _read_env_var(var: str) -> str | None:
    """Parse caller-ui/.env.local and return current value of var, or None."""
    if not CALLER_ENV_PATH.exists():
        return None
    for line in CALLER_ENV_PATH.read_text().splitlines():
        match = re.match(rf"^\s*{var}\s*=\s*(.*)$", line)
        if match:
            return match.group(1).strip().strip('"').strip("'") or None
    return None


def _write_env_var(var: str, value: str) -> bool:
    """
    Set var=value in caller-ui/.env.local. Creates the file from .env.example
    if missing. Returns True if the value changed (or was newly added).
    """
    if not CALLER_ENV_PATH.exists():
        if CALLER_ENV_EXAMPLE_PATH.exists():
            info(f"creating {CALLER_ENV_PATH.relative_to(REPO_ROOT)} from .env.example")
            CALLER_ENV_PATH.write_text(CALLER_ENV_EXAMPLE_PATH.read_text())
        else:
            CALLER_ENV_PATH.write_text("")

    existing = CALLER_ENV_PATH.read_text()
    pattern = re.compile(rf"^\s*{var}\s*=.*$", flags=re.MULTILINE)
    replacement = f"{var}={value}"

    if pattern.search(existing):
        previous = _read_env_var(var)
        if previous == value:
            return False
        new_text = pattern.sub(replacement, existing)
    else:
        sep = "" if existing.endswith("\n") or existing == "" else "\n"
        new_text = f"{existing}{sep}{replacement}\n"

    CALLER_ENV_PATH.write_text(new_text)
    return True


def read_current_backend_url() -> str | None:
    return _read_env_var(BACKEND_URL_VAR)


def update_caller_env(backend_url: str) -> bool:
    return _write_env_var(BACKEND_URL_VAR, backend_url)


def read_agent_id_from_index() -> str | None:
    """Read the agent id assigned by `elevenlabs agents push` from agents.json."""
    if not AGENTS_INDEX_PATH.exists():
        return None
    try:
        data = json.loads(AGENTS_INDEX_PATH.read_text())
    except json.JSONDecodeError:
        return None
    agents = data.get("agents", [])
    if not agents:
        return None
    return agents[0].get("id")


def sync_agent_id() -> bool:
    """
    Mirror the agent id from agents.json → caller-ui/.env.local. Returns True
    if .env.local changed. Silent no-op if agents.json has no id yet (e.g.
    before first agents-push).
    """
    agent_id = read_agent_id_from_index()
    if not agent_id:
        info("agents.json has no agent id yet — skipping NEXT_PUBLIC_ELEVENLABS_AGENT_ID sync")
        return False
    current = _read_env_var(AGENT_ID_VAR)
    if current == agent_id:
        return False
    changed = _write_env_var(AGENT_ID_VAR, agent_id)
    if changed:
        info(f"updated {AGENT_ID_VAR}: {current or '(unset)'} → {agent_id}")
    return changed


def run_agents_push(backend_url: str) -> None:
    """Invoke the existing sync script."""
    cmd = ["uv", "run", "python", "scripts/elevenlabs_sync.py",
           "--backend-url", backend_url]
    info(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        fail("agents-push failed — see output above", code=result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--caller-port", type=int, default=5173)
    parser.add_argument(
        "--no-push",
        action="store_true",
        help="Skip the agents-push step (don't re-sync to ElevenLabs).",
    )
    parser.add_argument(
        "--force-push",
        action="store_true",
        help="Run agents-push even if the backend URL hasn't changed.",
    )
    args = parser.parse_args()

    info("looking up ngrok tunnels from 127.0.0.1:4040...")
    tunnels = fetch_ngrok_tunnels()
    if not tunnels:
        fail(
            "ngrok is running but reports zero tunnels. Check your ngrok.yml has\n"
            "  tunnels:\n"
            f"    backend:  {{ proto: http, addr: {args.backend_port} }}\n"
            f"    caller:   {{ proto: http, addr: {args.caller_port} }}\n"
            "Then re-run: ngrok start --all"
        )

    backend_url = find_tunnel_for_port(tunnels, args.backend_port)
    caller_url = find_tunnel_for_port(tunnels, args.caller_port)

    if not backend_url:
        fail(
            f"no ngrok tunnel found for port {args.backend_port} (backend).\n"
            f"  Tunnels seen: {[t.get('config', {}).get('addr') for t in tunnels]}\n"
            f"  Add a 'backend' tunnel to ngrok.yml on port {args.backend_port}."
        )
    if not caller_url:
        fail(
            f"no ngrok tunnel found for port {args.caller_port} (caller-ui).\n"
            f"  Tunnels seen: {[t.get('config', {}).get('addr') for t in tunnels]}\n"
            f"  Add a 'caller' tunnel to ngrok.yml on port {args.caller_port}."
        )

    info(f"backend tunnel:    {backend_url}")
    info(f"caller-ui tunnel:  {caller_url}")

    previous = read_current_backend_url()
    backend_changed = update_caller_env(backend_url)
    if backend_changed:
        info(f"updated {BACKEND_URL_VAR}: {previous or '(unset)'} → {backend_url}")
    else:
        info(f"{BACKEND_URL_VAR} already correct")

    if args.no_push:
        info("--no-push set: skipping agents-push")
    elif backend_changed or args.force_push:
        run_agents_push(backend_url)
    else:
        info("backend URL unchanged — skipping agents-push (use --force-push to re-sync)")

    # Mirror agent id from agents.json into .env.local. Done AFTER agents-push
    # so a fresh push that assigns a new id propagates immediately.
    agent_changed = sync_agent_id()

    if backend_changed or agent_changed:
        info("→ restart caller-ui (`npm run dev`) for env changes to take effect")

    agent_id = read_agent_id_from_index()

    print()
    print("=" * 64)
    info("READY. Open this URL on your phone:")
    print()
    print(f"    {caller_url}")
    print()
    if agent_id:
        info(f"Caller UI env: NEXT_PUBLIC_ELEVENLABS_AGENT_ID={agent_id}")
        info("  (already in caller-ui/.env.local — no manual paste needed)")
        print()
    info("Phone checklist:")
    info("  1. Tap 'Visit Site' on the ngrok interstitial (first time)")
    info("  2. Tap 'Call for help'")
    info("  3. Allow microphone (iOS will prompt)")
    info("  4. Allow location (iOS will prompt)")
    info("  5. Speak — the agent should answer within ~1 second")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
