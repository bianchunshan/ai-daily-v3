#!/usr/bin/env python3
"""Run the AI Daily enrichment locally through the sexreba Hermes Grok proxy."""

import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


REPO_URL = "https://github.com/bianchunshan/ai-daily-v3.git"
RUNNER_ROOT = Path.home() / ".local" / "share" / "ai-daily-grok-runner"
REPO_DIR = RUNNER_ROOT / "repo"
LOCK_FILE = Path("/tmp/ai-daily-grok-update.lock")
PROXY_LOG = Path.home() / "Library" / "Logs" / "ai-daily-grok-proxy.log"
HERMES = Path.home() / ".local" / "bin" / "hermes"
PROFILE = "sexreba"
PROXY_PORT = 18645
DATA_FILES = [
    "news_data_latest.js",
    "news_data_list.js",
    "news_bodies.json",
    "news_chat_index.json",
    "seen_urls.json",
]


def log(message, **fields):
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "message": message,
        **fields,
    }
    print(json.dumps(row, ensure_ascii=False), flush=True)


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def ensure_repo():
    RUNNER_ROOT.mkdir(parents=True, exist_ok=True)
    if not (REPO_DIR / ".git").is_dir():
        run(["/usr/bin/git", "clone", REPO_URL, str(REPO_DIR)])
    status = subprocess.check_output(
        ["/usr/bin/git", "status", "--porcelain"], cwd=REPO_DIR, text=True
    ).strip()
    if status:
        raise RuntimeError(f"runner repository has unfinished changes: {status[:300]}")
    run(["/usr/bin/git", "fetch", "origin", "main", "--quiet"], cwd=REPO_DIR)
    run(["/usr/bin/git", "merge", "--ff-only", "origin/main"], cwd=REPO_DIR)
    # Retry a commit left ahead of origin by a previous transient push failure.
    run(["/usr/bin/git", "push", "origin", "main", "--quiet"], cwd=REPO_DIR)


def wait_for_port(port, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise RuntimeError("Hermes Grok proxy did not start")


def frontend_count():
    text = (REPO_DIR / "news_data_list.js").read_text(encoding="utf-8")
    raw = text.partition("var newsData = ")[2].partition(";\nvar newsDigest = ")[0]
    return len(json.loads(raw))


def push_changes():
    diff = subprocess.run(
        ["/usr/bin/git", "diff", "--quiet", "--", *DATA_FILES], cwd=REPO_DIR
    )
    if diff.returncode == 0:
        log("no_data_changes")
        return
    count = frontend_count()
    if count < 10:
        raise RuntimeError(f"frontend validation failed: only {count} items")
    run(["/usr/bin/git", "add", *DATA_FILES], cwd=REPO_DIR)
    run(
        ["/usr/bin/git", "-c", "user.name=ai-daily-grok[bot]",
         "-c", "user.email=ai-daily-grok@users.noreply.github.com",
         "commit", "-m", "chore: 本机 Grok 自动更新新闻"],
        cwd=REPO_DIR,
    )
    run(["/usr/bin/git", "push", "origin", "main"], cwd=REPO_DIR)
    head = subprocess.check_output(
        ["/usr/bin/git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, text=True
    ).strip()
    log("data_pushed", head=head, frontend_count=count)


def main():
    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("already_running")
            return 0

        ensure_repo()
        PROXY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with PROXY_LOG.open("a", encoding="utf-8") as proxy_log:
            proxy = subprocess.Popen(
                [str(HERMES), "-p", PROFILE, "proxy", "start", "--provider", "xai",
                 "--host", "127.0.0.1", "--port", str(PROXY_PORT)],
                stdout=proxy_log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_for_port(PROXY_PORT)
                env = os.environ.copy()
                env.update({
                    "ENRICH_PROVIDER": "grok",
                    "GROK_URL": f"http://127.0.0.1:{PROXY_PORT}/v1/chat/completions",
                    "GROK_MODEL": "grok-4.5",
                })
                log("enrichment_started", provider="grok", model="grok-4.5")
                run([sys.executable, "enrich_news.py"], cwd=REPO_DIR, env=env)
                push_changes()
            finally:
                proxy.terminate()
                try:
                    proxy.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proxy.kill()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log("failed", error=str(exc))
        raise SystemExit(1)
