"""
End-to-end sync of agents/elevenlabs/ to the ElevenLabs cloud.

  $ uv run python scripts/elevenlabs_sync.py --backend-url https://abc123.ngrok.app
  $ uv run python scripts/elevenlabs_sync.py --dry-run

Order of operations:
  1. Validate BACKEND_URL (must be https://)
  2. Substitute the URL into every tool_configs/*.json (idempotent — handles
     placeholder OR a previously-substituted ngrok URL)
  3. `elevenlabs tools push` — creates/updates tools, writes their ids back
     into tools.json
  4. Read tools.json, extract the four tool ids
  5. Patch agent_configs/emergency-intake.json with those tool_ids
  6. `elevenlabs agents push` — creates/updates the agent with tool bindings
  7. Print the agent id so you can paste it into caller-ui/.env.local

Re-runnable. Exits non-zero on first failure.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents" / "elevenlabs"
TOOL_CONFIGS_DIR = AGENTS_DIR / "tool_configs"
AGENT_CONFIG_PATH = AGENTS_DIR / "agent_configs" / "emergency-intake.json"
TOOLS_INDEX_PATH = AGENTS_DIR / "tools.json"
AGENTS_INDEX_PATH = AGENTS_DIR / "agents.json"

# Matches the URL prefix on tool endpoints. Group 1 is the entire prefix we replace.
URL_PATTERN = re.compile(r'"url":\s*"(https?://[^/"]+)(/intake/voice[^"]*)"')


def info(msg: str) -> None:
    print(f"[sync] {msg}")


def fail(msg: str, code: int = 1) -> None:
    print(f"[sync] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def run_cli(args: list[str], *, dry_run: bool = False, capture: bool = False) -> str:
    """Run an elevenlabs CLI subcommand inside agents/elevenlabs/."""
    cmd = ["elevenlabs", *args]
    if dry_run:
        cmd.append("--dry-run")
    info(f"$ {' '.join(cmd)}  (cwd={AGENTS_DIR.relative_to(Path.cwd())})")
    result = subprocess.run(
        cmd,
        cwd=AGENTS_DIR,
        capture_output=capture,
        text=True if capture else None,
    )
    if capture:
        # Always echo captured output so user still sees what happened.
        if result.stdout:
            sys.stdout.write(result.stdout)
        if result.stderr:
            sys.stderr.write(result.stderr)
    if result.returncode != 0:
        fail(f"command failed: {' '.join(cmd)}", code=result.returncode)
    return (result.stdout or "") if capture else ""


# Matches CLI v0.5.3's `tools pull --all --dry-run` line:
#   [DRY RUN] Would create tool: <name> (ID: <real_id>)
_TOOL_LIST_PATTERN = re.compile(r"Would create tool:\s+(\S+)\s+\(ID:\s+(tool_\S+)\)")


def fetch_real_tool_ids() -> dict[str, str]:
    """
    Workaround for CLI v0.5.3 bug: `tools push` assigns fabricated
    `tool_${Date.now()}` ids instead of the real ones returned by the API.
    Use `tools pull --all --dry-run` to list every tool on the server with its
    real id, then return {name → real_id}.
    """
    output = run_cli(["tools", "pull", "--all"], dry_run=True, capture=True)
    return dict(_TOOL_LIST_PATTERN.findall(output))


# Heuristic: CLI v0.5.3 fabricates ids as `tool_<13-digit-timestamp>`. Real
# server-issued ids have a different shape (mixed alphanumeric, ~30 chars).
_FAKE_ID_PATTERN = re.compile(r"^tool_\d{13}$")


def repair_fake_ids(real_by_name: dict[str, str]) -> int:
    """
    Walk tools.json. For any entry whose id matches the fake-id heuristic,
    look up the real id by tool name (from the on-disk tool config). Returns
    the number of ids repaired.
    """
    data = json.loads(TOOLS_INDEX_PATH.read_text())
    repaired = 0
    for entry in data.get("tools", []):
        current_id = entry.get("id")
        if not current_id or not _FAKE_ID_PATTERN.match(current_id):
            continue
        cfg_path = AGENTS_DIR / entry["config"]
        if not cfg_path.exists():
            continue
        cfg = json.loads(cfg_path.read_text())
        name = cfg.get("name")
        real_id = real_by_name.get(name)
        if real_id and real_id != current_id:
            info(f"  repaired fake id for {name}: {current_id} → {real_id}")
            entry["id"] = real_id
            repaired += 1
    if repaired:
        TOOLS_INDEX_PATH.write_text(json.dumps(data, indent=2) + "\n")
    return repaired


def substitute_backend_url(backend_url: str) -> int:
    """
    Replace the host part of every tool URL with backend_url. Handles both
    the YOUR_BACKEND placeholder AND a previously-baked URL (so re-runs work).
    Returns the count of files modified.
    """
    modified = 0
    for path in sorted(TOOL_CONFIGS_DIR.glob("*.json")):
        original = path.read_text()
        new_text, replacements = URL_PATTERN.subn(
            f'"url": "{backend_url}\\2"',
            original,
        )
        if replacements == 0:
            fail(f"{path.name} has no /intake/voice URL to substitute — file is malformed?")
        if new_text != original:
            path.write_text(new_text)
            modified += 1
            info(f"  patched {path.name}")
    return modified


def read_tool_ids() -> dict[str, str]:
    """Parse tools.json and return {tool_name → tool_id} for tools that have ids."""
    if not TOOLS_INDEX_PATH.exists():
        fail(f"{TOOLS_INDEX_PATH} not found — did you run `elevenlabs agents init`?")
    data = json.loads(TOOLS_INDEX_PATH.read_text())
    by_name: dict[str, str] = {}
    for entry in data.get("tools", []):
        cfg_path = AGENTS_DIR / entry["config"]
        if not cfg_path.exists():
            info(f"  warning: {entry['config']} referenced in tools.json but missing on disk")
            continue
        cfg = json.loads(cfg_path.read_text())
        name = cfg.get("name")
        tool_id = entry.get("id")
        if name and tool_id:
            by_name[name] = tool_id
    return by_name


def inject_tool_ids(tool_ids: list[str]) -> bool:
    """
    Write tool_ids into the agent config's
    conversation_config.agent.prompt.tool_ids array. Returns True if changed.
    """
    agent = json.loads(AGENT_CONFIG_PATH.read_text())
    prompt = agent["conversation_config"]["agent"]["prompt"]
    current = prompt.get("tool_ids", [])
    if set(current) == set(tool_ids):
        return False
    prompt["tool_ids"] = tool_ids
    AGENT_CONFIG_PATH.write_text(json.dumps(agent, indent=2) + "\n")
    return True


def read_agent_id() -> str | None:
    """Parse agents.json and return the first agent's id, or None."""
    if not AGENTS_INDEX_PATH.exists():
        return None
    data = json.loads(AGENTS_INDEX_PATH.read_text())
    agents = data.get("agents", [])
    if not agents:
        return None
    return agents[0].get("id")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backend-url",
        default=os.environ.get("BACKEND_URL", ""),
        help="Public HTTPS URL of the backend (e.g. https://abc123.ngrok.app). "
             "Defaults to $BACKEND_URL env var.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run elevenlabs CLI with --dry-run; do not actually push.",
    )
    parser.add_argument(
        "--skip-tools",
        action="store_true",
        help="Skip the tools push step (use if you only changed the agent).",
    )
    args = parser.parse_args()

    if not args.backend_url:
        fail("--backend-url (or BACKEND_URL env var) is required. Example:\n"
             "  uv run python scripts/elevenlabs_sync.py --backend-url https://abc123.ngrok.app")
    if not args.backend_url.startswith("https://"):
        fail(f"backend URL must be https:// (got: {args.backend_url}). "
             "ElevenLabs cloud requires HTTPS for webhooks.")
    args.backend_url = args.backend_url.rstrip("/")

    info(f"backend URL: {args.backend_url}")
    info(f"agents dir:  {AGENTS_DIR}")

    # 1. Substitute URL into tool configs
    changed = substitute_backend_url(args.backend_url)
    info(f"substituted URL in {changed} tool config(s)")

    # 2. Push tools (creates/updates, writes ids into tools.json)
    if not args.skip_tools:
        run_cli(["tools", "push"], dry_run=args.dry_run)

    # On dry-run, the rest of the pipeline can't proceed (no real ids assigned).
    if args.dry_run:
        info("dry-run complete — agent push skipped (would require real tool ids)")
        return 0

    # 2b. Workaround for CLI v0.5.3 bug: `tools push` may write fabricated
    # `tool_<13-digit-timestamp>` ids on CREATE. Detect and repair from the
    # server-side list before binding the agent.
    if not args.skip_tools:
        info("checking for fake tool ids from CLI v0.5.3 push bug...")
        real_by_name = fetch_real_tool_ids()
        repaired = repair_fake_ids(real_by_name)
        if repaired:
            info(f"repaired {repaired} fake id(s) in tools.json")
        else:
            info("all tool ids look real — no repair needed")

    # 3. Read assigned tool ids, inject into agent
    tool_ids = read_tool_ids()
    info(f"tool ids in tools.json: {len(tool_ids)} / 4 expected")
    for name, tid in sorted(tool_ids.items()):
        info(f"  {name}: {tid}")

    expected = {
        "create_incident_provisional",
        "update_assessment",
        "query_nearby_resources",
        "finalize",
    }
    missing = expected - set(tool_ids)
    if missing:
        fail(f"tools.json is missing ids for: {sorted(missing)}. "
             "Tool push must have failed for these — re-run after fixing.")

    if inject_tool_ids(sorted(tool_ids.values())):
        info(f"injected {len(tool_ids)} tool_ids into {AGENT_CONFIG_PATH.name}")
    else:
        info(f"{AGENT_CONFIG_PATH.name} already has the right tool_ids — no change")

    # 4. Push the agent
    run_cli(["agents", "push"])

    # 5. Report agent id
    agent_id = read_agent_id()
    print()
    print("=" * 64)
    if agent_id:
        info(f"agent id: {agent_id}")
        print()
        print("Paste this into caller-ui/.env.local:")
        print(f"  NEXT_PUBLIC_ELEVENLABS_AGENT_ID={agent_id}")
    else:
        info("agents.json has no id yet — check `elevenlabs agents list`")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    sys.exit(main())
