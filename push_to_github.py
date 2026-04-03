"""
Novaro HQ — GitHub Data Pusher
Pushes social-data.json and task-status.json to the GitHub repo
so the novarohq.com dashboard always has fresh live data.

Run this after any scraper updates the local JSON files.
Replaces the old Netlify redeploy step.

Token is loaded from .novaro_credentials or GITHUB_TOKEN env var.
"""

import json
import base64
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DASHBOARD_DIR = Path(__file__).parent
CREDS_FILE    = DASHBOARD_DIR / ".novaro_credentials"

def load_creds():
    creds = {}
    if CREDS_FILE.exists():
        for line in CREDS_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                creds[k.strip()] = v.strip()
    return creds

creds = load_creds()
GITHUB_TOKEN = creds.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER   = "vitogcocchi"
REPO_NAME    = "novarohq-dashboard"
BRANCH       = "main"

SOCIAL_FILE   = DASHBOARD_DIR / "social-data.json"
TASKS_FILE    = DASHBOARD_DIR / "task-status.json"
FUNNEL_FILE   = DASHBOARD_DIR / "funnel-data.json"
DEBRIEF_FILE  = DASHBOARD_DIR / "morning-debrief-data.json"
API_BASE     = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents"


# ─── HELPERS ──────────────────────────────────────────────────────────────────
def get_file_sha(filename):
    url = f"{API_BASE}/{filename}?ref={BRANCH}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "novaro-github-pusher/1.0",
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8")).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def push_file(filename, content_str, sha=None):
    url = f"{API_BASE}/{filename}"
    content_b64 = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
    payload = {
        "message": f"auto: update {filename} [{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}]",
        "content": content_b64,
        "branch": BRANCH,
    }
    if sha:
        payload["sha"] = sha

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="PUT",
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
            "User-Agent": "novaro-github-pusher/1.0",
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            commit_sha = result.get("commit", {}).get("sha", "?")[:7]
            print(f"     → {filename} pushed (commit {commit_sha})")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"[error] Failed to push {filename}: HTTP {e.code} — {body[:300]}")
        return False


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def push_all(include_html=False):
    if not GITHUB_TOKEN:
        print("[error] No GITHUB_TOKEN found in .novaro_credentials or environment")
        return False

    files = [
        (SOCIAL_FILE,   "social-data.json"),
        (TASKS_FILE,    "task-status.json"),
        (FUNNEL_FILE,   "funnel-data.json"),
        (DEBRIEF_FILE,  "morning-debrief-data.json"),
    ]
    if include_html:
        html_file = DASHBOARD_DIR / "index.html"
        files.append((html_file, "index.html"))
    success_count = 0
    for local_path, repo_filename in files:
        if not local_path.exists():
            print(f"[warn] {local_path.name} not found — skipping")
            continue
        sha = get_file_sha(repo_filename)
        ok = push_file(repo_filename, local_path.read_text(encoding="utf-8"), sha=sha)
        if ok:
            success_count += 1

    return success_count > 0


if __name__ == "__main__":
    include_html = "--include-html" in sys.argv
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] Pushing dashboard data to GitHub{'  (+ index.html)' if include_html else ''}...")
    success = push_all(include_html=include_html)
    print("[ok] Done" if success else "[warn] Push had errors")
    exit(0 if success else 1)
