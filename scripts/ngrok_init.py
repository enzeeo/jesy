"""
One-time ngrok.yml setup for this project.

  $ make ngrok-init                       # auto-detect static domain from tool configs
  $ make ngrok-init NGROK_DOMAIN=foo.ngrok-free.dev   # explicit

Idempotent: if the tunnels block is already present, exits with a notice and
makes no changes. Otherwise appends the block, preserving every existing line
(authtoken, version, etc.).

Why this script exists:
  ngrok free gives you ONE static domain per account. To stop re-pushing the
  ElevenLabs agent every time ngrok restarts, we pin the static domain to the
  backend tunnel (port 8000) and let the caller tunnel (port 5173) get a
  random URL each session.

Detection order for the static domain:
  1. --domain argv flag
  2. NGROK_DOMAIN env var
  3. Parsed out of any tool config URL (agents/elevenlabs/tool_configs/*.json)
  4. None — adds backend tunnel WITHOUT a domain pin (URL random per restart)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOL_CONFIGS_DIR = REPO_ROOT / "agents" / "elevenlabs" / "tool_configs"

# Matches URLs like https://indicatively-perissodactylous-mable.ngrok-free.dev/...
NGROK_HOST_PATTERN = re.compile(r'"url":\s*"https://([^/"]+\.ngrok-free\.(?:dev|app))/')


def info(msg: str) -> None:
    print(f"[ngrok-init] {msg}")


def fail(msg: str, code: int = 1) -> None:
    print(f"[ngrok-init] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def find_ngrok_config() -> Path:
    """
    Locate ngrok's config file. Try `ngrok config check` first (most accurate),
    fall back to the documented default paths per OS.
    """
    # Method 1: ask ngrok directly. Output format on success:
    #   Valid configuration file at /Users/.../Library/Application Support/ngrok/ngrok.yml
    try:
        result = subprocess.run(
            ["ngrok", "config", "check"],
            capture_output=True,
            text=True,
            check=False,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        # Path can contain spaces (e.g. "Application Support"), so anchor on
        # "at " and capture lazily up to the .yml extension at end of line.
        match = re.search(r"\bat\s+(.+?\.yml)(?:\s|$)", combined)
        if match:
            return Path(match.group(1).strip())
    except FileNotFoundError:
        fail("ngrok not on PATH. Install with: brew install ngrok")

    # Method 2: known default paths
    candidates = [
        Path.home() / "Library" / "Application Support" / "ngrok" / "ngrok.yml",  # macOS
        Path.home() / ".config" / "ngrok" / "ngrok.yml",                          # Linux modern
        Path.home() / ".ngrok2" / "ngrok.yml",                                    # Linux legacy
    ]
    for path in candidates:
        if path.exists():
            return path

    # Method 3: nothing found — pick the OS default to create
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ngrok" / "ngrok.yml"
    return Path.home() / ".config" / "ngrok" / "ngrok.yml"


def detect_static_domain() -> str | None:
    """Walk tool configs and find the first ngrok host substituted into a URL."""
    if not TOOL_CONFIGS_DIR.exists():
        return None
    for path in sorted(TOOL_CONFIGS_DIR.glob("*.json")):
        text = path.read_text()
        match = NGROK_HOST_PATTERN.search(text)
        if match:
            return match.group(1)
    return None


def has_tunnels_block(config_text: str) -> bool:
    """Return True if a top-level `tunnels:` key already exists."""
    return bool(re.search(r"^\s*tunnels:\s*$", config_text, flags=re.MULTILINE))


def build_tunnels_block(domain: str | None) -> str:
    backend_lines = [
        "  backend:",
        "    proto: http",
        "    addr: 8000",
    ]
    if domain:
        backend_lines.append(f"    domain: {domain}")
    block_lines = [
        "tunnels:",
        *backend_lines,
        "  caller:",
        "    proto: http",
        "    addr: 5173",
    ]
    return "\n".join(block_lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--domain",
        default=os.environ.get("NGROK_DOMAIN", ""),
        help="ngrok static domain to pin to the backend tunnel (e.g. foo.ngrok-free.dev). "
             "Defaults to $NGROK_DOMAIN, or auto-detected from existing tool configs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Append the tunnels block even if one already exists (you may end up with duplicates — edit by hand instead).",
    )
    args = parser.parse_args()

    domain = args.domain or detect_static_domain()
    if domain:
        info(f"using static domain for backend: {domain}")
    else:
        info("no static domain provided — backend URL will change every ngrok restart")
        info("  (claim one free at https://dashboard.ngrok.com/domains and re-run with --domain)")

    config_path = find_ngrok_config()
    info(f"ngrok config: {config_path}")

    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('version: "3"\n')
        info("created empty config")

    existing = config_path.read_text()

    if not args.force and has_tunnels_block(existing):
        info("`tunnels:` block already present in ngrok.yml — no change made.")
        info("  edit by hand or re-run with --force to append a second block.")
        return 0

    block = build_tunnels_block(domain)
    sep = "" if existing.endswith("\n") or existing == "" else "\n"
    config_path.write_text(existing + sep + "\n" + block)

    info("appended tunnels block:")
    for line in block.splitlines():
        info(f"  {line}")
    info("done. Re-run: make demo-up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
