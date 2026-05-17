"""
One-command demo orchestrator.

  $ make demo-up        # start backend + ngrok + caller-ui + demo-setup
  $ <Ctrl-C>            # tear everything down cleanly

What it does, in order:
  1. Start backend (uvicorn :8000) — wait for /healthz
  2. Start ngrok (both tunnels)    — wait for admin API 127.0.0.1:4040
  3. Start caller-ui (next dev :5173) — wait for port
  4. Run demo_setup.py (one-shot)  — wires env + pushes agent
  5. Print caller URL, then block until Ctrl-C

All processes run as their own process group so npm's grandchildren
(esbuild, swc, etc.) die when the orchestrator exits.

Logs from each process are prefixed and colorized so you can scroll back
to find errors.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CALLER_UI_DIR = REPO_ROOT / "caller-ui"
DASHBOARD_DIR = REPO_ROOT / "frontend"

# ANSI colors — one per process, bold prefix, reset after
RESET = "\033[0m"
BOLD = "\033[1m"
COLORS = {
    "backend":   "\033[34m",    # blue
    "ngrok":     "\033[33m",    # yellow
    "dashboard": "\033[31m",    # red
    "caller":    "\033[35m",    # magenta
    "setup":     "\033[32m",    # green
    "orch":      "\033[36m",    # cyan
}


@dataclass
class Managed:
    label: str
    proc: subprocess.Popen
    critical: bool  # if True, dying triggers full teardown


_managed: list[Managed] = []
_shutting_down = False


def log(label: str, msg: str) -> None:
    color = COLORS.get(label, "")
    sys.stdout.write(f"{color}{BOLD}[{label:>7}]{RESET} {msg}\n")
    sys.stdout.flush()


def orch(msg: str) -> None:
    log("orch", msg)


def fail(msg: str) -> None:
    orch(f"ERROR: {msg}")
    shutdown(exit_code=1)


def stream_output(label: str, proc: subprocess.Popen) -> None:
    """Daemon thread: read child stdout line-by-line, prefix-print to ours."""
    color = COLORS.get(label, "")
    if proc.stdout is None:
        return
    try:
        for raw in iter(proc.stdout.readline, b""):
            text = raw.decode("utf-8", errors="replace").rstrip("\n")
            if not text:
                continue
            sys.stdout.write(f"{color}{BOLD}[{label:>7}]{RESET} {text}\n")
            sys.stdout.flush()
    except (ValueError, OSError):
        # File descriptor closed during shutdown — ignore.
        pass


def spawn(label: str, cmd: list[str], *, cwd: Path | None = None, critical: bool = True) -> subprocess.Popen:
    """
    Launch a child as the leader of a new process group so killpg cleans up
    everything it spawns. Stream its stdout (+ merged stderr) on a daemon
    thread with a label prefix.
    """
    orch(f"starting {label}: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _managed.append(Managed(label=label, proc=proc, critical=critical))
    threading.Thread(target=stream_output, args=(label, proc), daemon=True).start()
    return proc


def wait_for_port(host: str, port: int, *, timeout_s: int = 30, label: str = "") -> bool:
    """Poll a TCP port until it accepts a connection or we time out."""
    deadline = time.time() + timeout_s
    target = label or f"{host}:{port}"
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.3)
    orch(f"timeout waiting for {target}")
    return False


def wait_for_http_200(url: str, *, timeout_s: int = 30, label: str = "") -> bool:
    deadline = time.time() + timeout_s
    target = label or url
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionResetError, TimeoutError):
            pass
        time.sleep(0.3)
    orch(f"timeout waiting for {target}")
    return False


def shutdown(*_args, exit_code: int = 0) -> None:
    """Send SIGTERM to every managed process group, then SIGKILL stragglers."""
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    orch("shutting down — sending SIGTERM to all children...")
    for m in _managed:
        if m.proc.poll() is None:
            try:
                os.killpg(os.getpgid(m.proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

    deadline = time.time() + 5
    for m in _managed:
        try:
            remaining = max(0.1, deadline - time.time())
            m.proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            orch(f"  {m.label} didn't exit in time — SIGKILL")
            try:
                os.killpg(os.getpgid(m.proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    orch("done.")
    sys.exit(exit_code)


def _fetch_ngrok_urls() -> tuple[str | None, str | None]:
    """Return (caller_url for :5173, backend_url for :8000) from ngrok's API."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=2) as r:
            tunnels = json.loads(r.read()).get("tunnels", [])
    except Exception:  # noqa: BLE001 — best-effort UI sugar
        return None, None
    caller = backend = None
    for t in tunnels:
        url = t.get("public_url", "")
        addr = t.get("config", {}).get("addr", "")
        if not url.startswith("https://"):
            continue
        if addr.endswith(":5173"):
            caller = url
        elif addr.endswith(":8000"):
            backend = url
    return caller, backend


def preflight(*, skip_dashboard: bool, skip_caller: bool, skip_ngrok: bool) -> None:
    missing = []
    for tool in ["uv", "npm", "ngrok"]:
        if shutil.which(tool) is None:
            missing.append(tool)
    if missing:
        fail(f"missing required tools on PATH: {', '.join(missing)}")

    if not skip_caller:
        if not CALLER_UI_DIR.exists():
            fail(f"caller-ui dir not found at {CALLER_UI_DIR}")
        if not (CALLER_UI_DIR / "node_modules").exists():
            orch("caller-ui/node_modules missing — run `cd caller-ui && npm install` first")
            fail("caller-ui deps not installed")

    if not skip_dashboard:
        if not DASHBOARD_DIR.exists():
            fail(f"frontend dir not found at {DASHBOARD_DIR}")
        if not (DASHBOARD_DIR / "node_modules").exists():
            orch("frontend/node_modules missing — run `cd frontend && npm install` first")
            fail("frontend deps not installed")

    if not skip_ngrok:
        # Two ngrok agents both running --all both try to claim the static
        # domain, causing chaotic routing where some requests hit backend
        # and others hit caller-ui. Force a clean slate before starting.
        stale = _list_ngrok_pids()
        if stale:
            orch(f"found {len(stale)} stale ngrok process(es): {stale} — killing for clean start")
            for pid in stale:
                try:
                    os.kill(pid, signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
            time.sleep(1.5)
            remaining = _list_ngrok_pids()
            if remaining:
                orch(f"  some ngrok survivors: {remaining} — SIGKILL")
                for pid in remaining:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                time.sleep(0.5)


def _list_ngrok_pids() -> list[int]:
    """pgrep for ngrok processes that are NOT children of this script."""
    try:
        out = subprocess.run(
            ["pgrep", "-x", "ngrok"],
            capture_output=True, text=True, check=False,
        )
        pids = [int(line) for line in out.stdout.strip().splitlines() if line.strip().isdigit()]
        # Filter out anything we spawned (we're not running yet, so all are stale)
        my_pid = os.getpid()
        return [p for p in pids if p != my_pid]
    except (FileNotFoundError, ValueError):
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-setup", action="store_true",
                        help="Don't run demo-setup at the end (skip env update + agents-push)")
    parser.add_argument("--skip-ngrok", action="store_true",
                        help="Don't start ngrok (use if you have ngrok running already in another terminal)")
    parser.add_argument("--skip-dashboard", action="store_true",
                        help="Don't start the dispatcher dashboard (frontend/ at :3000)")
    parser.add_argument("--skip-caller", action="store_true",
                        help="Don't start the caller UI (caller-ui/ at :5173)")
    parser.add_argument("--caller-prod", action="store_true",
                        help="Build + run caller-ui in production mode (bypasses Turbopack dev runtime — required for iOS Safari over ngrok). Adds ~15s to startup.")
    parser.add_argument("--no-reload", action="store_true",
                        help="Run backend without --reload (avoids double-process noise)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, lambda *a: shutdown())
    signal.signal(signal.SIGTERM, lambda *a: shutdown())

    preflight(
        skip_dashboard=args.skip_dashboard,
        skip_caller=args.skip_caller,
        skip_ngrok=args.skip_ngrok,
    )

    # ── 1. Backend ────────────────────────────────────────────────────────────
    backend_cmd = ["uv", "run", "uvicorn", "disaster.app.main:app", "--port", "8000"]
    if not args.no_reload:
        backend_cmd.append("--reload")
    spawn("backend", backend_cmd, cwd=REPO_ROOT)
    if not wait_for_http_200("http://127.0.0.1:8000/healthz", timeout_s=20, label="backend /healthz"):
        fail("backend never became ready")
    orch("backend ✓ (http://localhost:8000)")

    # ── 2. ngrok ──────────────────────────────────────────────────────────────
    if args.skip_ngrok:
        orch("--skip-ngrok set — assuming ngrok is running elsewhere")
    else:
        spawn("ngrok", ["ngrok", "start", "--all", "--log=stdout", "--log-format=term"], cwd=REPO_ROOT)
        if not wait_for_http_200("http://127.0.0.1:4040/api/tunnels", timeout_s=15, label="ngrok admin API"):
            fail("ngrok admin API never came up — check ngrok.yml has both tunnels (backend:8000, caller:5173)")
        orch("ngrok ✓ (http://127.0.0.1:4040)")

    # ── 3. Dispatcher dashboard (frontend/) ───────────────────────────────────
    if args.skip_dashboard:
        orch("--skip-dashboard set — not starting frontend/")
    else:
        spawn("dashboard", ["npm", "run", "dev"], cwd=DASHBOARD_DIR)
        if not wait_for_port("127.0.0.1", 3000, timeout_s=60, label="dashboard :3000"):
            fail("dispatcher dashboard (frontend/) never came up")
        orch("dashboard ✓ (http://localhost:3000)")

    # ── 4. Caller UI ──────────────────────────────────────────────────────────
    if args.skip_caller:
        orch("--skip-caller set — not starting caller-ui/")
    elif args.caller_prod:
        # Production build path: required for iOS Safari over ngrok. Next 16's
        # Turbopack dev runtime hangs hydration on mobile Safari behind a tunnel.
        #
        # IMPORTANT: run demo-setup BEFORE the build so NEXT_PUBLIC_* env vars
        # (backend URL + agent id) are written into .env.local in time to be
        # baked into the bundle. If we built first and synced later, the prod
        # bundle would be missing the right env values.
        if not args.skip_setup and not args.skip_ngrok:
            orch("running demo-setup to sync env before prod build...")
            pre_setup = subprocess.run(
                ["uv", "run", "python", "scripts/demo_setup.py"],
                cwd=str(REPO_ROOT),
                capture_output=False,
            )
            if pre_setup.returncode != 0:
                orch("demo-setup exited non-zero — continuing anyway, env may be stale")

        orch("--caller-prod set — building caller-ui for production (~15s)...")
        build = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(CALLER_UI_DIR),
            capture_output=False,
        )
        if build.returncode != 0:
            fail("caller-ui production build failed — see output above")
        orch("caller-ui build ✓ — starting production server")
        spawn("caller", ["npm", "start"], cwd=CALLER_UI_DIR)
        if not wait_for_port("127.0.0.1", 5173, timeout_s=60, label="caller-ui :5173"):
            fail("caller-ui prod server never came up")
        orch("caller-ui ✓ (http://localhost:5173 — PROD MODE, no HMR)")
    else:
        spawn("caller", ["npm", "run", "dev"], cwd=CALLER_UI_DIR)
        if not wait_for_port("127.0.0.1", 5173, timeout_s=60, label="caller-ui :5173"):
            fail("caller-ui dev server never came up")
        orch("caller-ui ✓ (http://localhost:5173 — DEV MODE; if iOS Safari hangs, retry with --caller-prod)")

    # ── 5. Demo setup (one-shot wire-up) ──────────────────────────────────────
    # In --caller-prod mode we already ran setup before the build, so skip
    # the second run.
    if not args.skip_setup and not args.skip_ngrok and not args.caller_prod:
        setup_proc = spawn(
            "setup",
            ["uv", "run", "python", "scripts/demo_setup.py"],
            cwd=REPO_ROOT,
            critical=False,
        )
        setup_proc.wait()
        if setup_proc.returncode != 0:
            orch("demo-setup exited non-zero — see above")
            # Don't fail the whole stack; everything else might still be useful
        else:
            orch("demo-setup ✓")

    # ── 6. Block until Ctrl-C, watching for child deaths ──────────────────────
    caller_url, backend_url = _fetch_ngrok_urls() if not args.skip_ngrok else (None, None)

    print()
    orch("=" * 70)
    orch("ALL UP.")
    if not args.skip_dashboard:
        orch("  Dispatcher dashboard (laptop):")
        orch("    http://localhost:3000")
    if not args.skip_caller:
        orch("")
        orch("  Caller UI on YOUR PHONE — open this exact URL:")
        if caller_url:
            orch(f"    {caller_url}")
        else:
            orch("    (ngrok not started — use http://localhost:5173 locally)")
    if backend_url:
        orch("")
        orch(f"  Backend tunnel (do NOT open on phone — ElevenLabs uses it): {backend_url}")
    orch("")
    orch("Press Ctrl-C to tear everything down.")
    orch("=" * 70)
    print()

    try:
        while not _shutting_down:
            for m in _managed:
                if m.critical and m.proc.poll() is not None:
                    orch(f"{m.label} died (exit code {m.proc.returncode}) — tearing down")
                    shutdown(exit_code=1)
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
