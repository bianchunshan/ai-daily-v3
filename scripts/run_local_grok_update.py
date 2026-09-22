#!/usr/bin/env python3
"""Run and publish AI Daily through the local Qwen service."""

import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import socket
import subprocess
import sys
import time
import urllib.request


REPO_URL = "https://github.com/bianchunshan/ai-daily-v3.git"
RUNNER_ROOT = Path.home() / ".local" / "share" / "ai-daily-grok-runner"
REPO_DIR = RUNNER_ROOT / "repo"
LOCK_FILE = Path("/tmp/ai-daily-grok-update.lock")
PROXY_LOG = Path.home() / "Library" / "Logs" / "ai-daily-grok-proxy.log"
HERMES = Path.home() / ".local" / "bin" / "hermes"
PROFILE = "sexreba"
PROXY_PORT = 18645
# 本机模型 API(ai.mlx.auth-proxy)。token 不写死在仓库里,运行时从家目录读。
# 使用本机常驻的 Qwen3.6-35B-A3B 推理服务,直连 mlx_lm.server,不经过外部模型。
LOCAL_API_BASE = os.environ.get("LOCAL_API_BASE", "http://127.0.0.1:8799")
MANAGED_MODEL = str(Path.home() / '.lmstudio/models/mlx-community/Qwen3.6-35B-A3B-8bit')
MODEL_SERVICE = 'ai.local-mlx.qwen36.server'
MODEL_PLIST = Path.home() / 'Library/LaunchAgents' / (MODEL_SERVICE + '.plist')
LOCAL_MODEL = os.environ.get(
    "LOCAL_MODEL",
    MANAGED_MODEL,
)
# 提交信息里只写短名,别把整条模型路径塞进 git log
LOCAL_MODEL_LABEL = os.environ.get("LOCAL_MODEL_LABEL", "qwen3.6-35b")
TOKENS_PATH = Path.home() / ".mlx-api" / "tokens.json"
LOCAL_TOKEN_LABEL = "github-actions-ai-daily"
DATA_FILES = [
    "news_data_latest.js",
    "news_data_list.js",
    "news_bodies.json",
    "news_chat_index.json",
    "seen_urls.json",
    "retry_queue.json",
    "backfill_queue.json",
    "data",
]


def log(message, **fields):
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "message": message,
        **fields,
    }
    print(json.dumps(row, ensure_ascii=False), flush=True)


def run(args, timeout=None, **kwargs):
    return subprocess.run(args, check=True, text=True, timeout=timeout, **kwargs)


def sync_remote():
    run(["/usr/bin/git", "fetch", "origin", "main", "--quiet"], cwd=REPO_DIR, timeout=30)
    try:
        run(["/usr/bin/git", "merge", "--no-edit", "origin/main"], cwd=REPO_DIR, timeout=15)
    except subprocess.CalledProcessError:
        merge = subprocess.run(["/usr/bin/git", "rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd=REPO_DIR, capture_output=True)
        if merge.returncode == 0:
            run(["/usr/bin/git", "merge", "--abort"], cwd=REPO_DIR, timeout=15)
        raise


def push_remote():
    for attempt in range(3):
        try:
            run(["/usr/bin/git", "push", "origin", "main", "--quiet"], cwd=REPO_DIR, timeout=25)
            return True
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
            log("git_push_retry", attempt=attempt + 1, error=str(exc)[:300])
            if attempt < 2:
                try:
                    sync_remote()
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as sync_error:
                    log("git_sync_failed", error=str(sync_error)[:300])
                time.sleep(2 ** (attempt + 1))
    log("data_pending_publish", action="retry_next_scheduled_run")
    return False


def ensure_repo():
    RUNNER_ROOT.mkdir(parents=True, exist_ok=True)
    if not (REPO_DIR / ".git").is_dir():
        run(["/usr/bin/git", "clone", REPO_URL, str(REPO_DIR)])
    status = subprocess.check_output(
        ["/usr/bin/git", "status", "--porcelain"], cwd=REPO_DIR, text=True
    )
    if status:
        paths = {line[3:] for line in status.splitlines() if len(line) > 3}
        unknown = {p for p in paths if p not in DATA_FILES and not p.startswith('data/')}
        if unknown:
            raise RuntimeError(f"runner repository has unknown changes: {sorted(unknown)}")
        log("recovering_pending_data_files", files=sorted(paths))
        push_changes()
    # GitHub 网络异常不应阻塞本机抓取；本地提交保留，下一轮再同步。
    try:
        sync_remote()
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        log("git_sync_failed", error=str(exc)[:300])
    # Retry a commit left ahead of origin by a previous transient push failure.
    push_remote()


def read_local_key():
    """本机 API 的 token。缺失时返回空串,让 enrich_news.py 用 401 显式失败。"""
    try:
        entries = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
        for entry in entries:
            if entry.get("label") == LOCAL_TOKEN_LABEL:
                return entry.get("token", "")
    except Exception as exc:
        log("local_key_unreadable", error=str(exc))
    return ""


def local_api_ready():
    """Check the configured local endpoint without invoking generation."""
    try:
        # 直连 mlx_lm.server 时没有 /health,用 /v1/models 当探活端点
        with urllib.request.urlopen(f"{LOCAL_API_BASE}/v1/models", timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def ensure_local_api(timeout=90):
    if local_api_ready():
        return True
    # Only recover our known local service; do not change custom endpoints or overrides.
    if (LOCAL_API_BASE.rstrip('/') != 'http://127.0.0.1:8799'
            or LOCAL_MODEL != MANAGED_MODEL
            or os.environ.get('AID_MODEL_AUTOSTART', '1') != '1'):
        return False
    try:
        with MODEL_PLIST.open('rb') as handle:
            config = plistlib.load(handle)
        if config.get('Label') != MODEL_SERVICE or config.get('Disabled'):
            return False
        domain = f'gui/{os.getuid()}'
        disabled = run(['/bin/launchctl', 'print-disabled', domain], capture_output=True, timeout=5)
        if re.search(r'"' + re.escape(MODEL_SERVICE) + r'"\s*=>\s*(?:disabled|true)', disabled.stdout):
            log('model_recovery_skipped', reason='service_explicitly_disabled')
            return False
        state = subprocess.run(['/bin/launchctl', 'print', domain + '/' + MODEL_SERVICE],
                               capture_output=True, text=True, timeout=5)
        if state.returncode != 0:
            run(['/bin/launchctl', 'bootstrap', domain, str(MODEL_PLIST)], capture_output=True, timeout=10)
            action = 'bootstrap'
        elif re.search(r'\bstate\s*=\s*running\b', state.stdout):
            action = 'wait_for_startup'
        else:
            # Without -k, kickstart never kills an existing model process.
            run(['/bin/launchctl', 'kickstart', domain + '/' + MODEL_SERVICE], capture_output=True, timeout=10)
            action = 'kickstart'
        log('model_recovery_started', service=MODEL_SERVICE, action=action)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if local_api_ready():
                log('model_recovered', service=MODEL_SERVICE)
                return True
            time.sleep(2)
    except (OSError, ValueError, plistlib.InvalidFileException,
            subprocess.SubprocessError) as exc:
        log('model_recovery_failed', error=type(exc).__name__)
        return False
    log('model_recovery_failed', error='startup_timeout')
    return False


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
    changes = subprocess.check_output(
        ["/usr/bin/git", "status", "--porcelain", "--", *DATA_FILES], cwd=REPO_DIR, text=True)
    if not changes.strip():
        log("no_data_changes")
        return True
    count = frontend_count()
    if count < 10:
        raise RuntimeError(f"frontend validation failed: only {count} items")
    run(["/usr/bin/git", "add", *DATA_FILES], cwd=REPO_DIR)
    run(
        ["/usr/bin/git", "-c", "user.name=ai-daily-grok[bot]",
         "-c", "user.email=ai-daily-grok@users.noreply.github.com",
         "commit", "-m", f"chore: 本机 {LOCAL_MODEL_LABEL} 自动更新新闻"],
        cwd=REPO_DIR,
    )
    if not push_remote():
        return False
    head = subprocess.check_output(
        ["/usr/bin/git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, text=True
    ).strip()
    log("data_pushed", head=head, frontend_count=count)
    return True


def main():
    with LOCK_FILE.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("already_running")
            return 0

        ensure_repo()
        sys.path.insert(0, str(REPO_DIR))
        from news_export import write_status
        # 使用本机常驻模型(LaunchAgent ai.local-mlx.qwen36.server),
        # 不再按轮拉起 Hermes 的 xai proxy——本机服务一直在,少一个进程生命周期要管。
        if not ensure_local_api():
            log("local_api_unavailable", url=LOCAL_API_BASE)
            os.chdir(REPO_DIR)
            write_status(error='model_unavailable')
            push_changes()
            return 1
        env = os.environ.copy()
        env.update({
            "ENRICH_PROVIDER": "local",
            "LOCAL_URL": f"{LOCAL_API_BASE}/v1/chat/completions",
            "LOCAL_KEY": read_local_key(),
            "LOCAL_MODEL": LOCAL_MODEL,
            "PYTHONUNBUFFERED": "1",
        })
        log("enrichment_started", provider="local", model=LOCAL_MODEL_LABEL)
        try:
            run([sys.executable, "enrich_news.py"], cwd=REPO_DIR, env=env, timeout=540)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            os.chdir(REPO_DIR)
            write_status(error='update_failed')
            push_changes()
            return 1
        return 0 if push_changes() else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log("failed", error=str(exc))
        raise SystemExit(1)
