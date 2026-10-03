#!/usr/bin/env python3
"""Rewrite the recent activity section of README.md from public GitHub events.

Reads events from the GitHub API (or from a local JSON file when
ACTIVITY_EVENTS_FILE is set, which is handy for testing) and replaces
everything between the ACTIVITY markers in the README.
"""

import json
import os
import re
import sys
import urllib.request

USER = os.environ.get("GITHUB_USER", "galando")
README = os.environ.get("README_PATH", "README.md")
LIMIT = int(os.environ.get("ACTIVITY_LIMIT", "8"))
SKIP_REPOS = {f"{USER}/{USER}"}  # the profile repo itself (bot commits)

START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"


def fetch_events():
    path = os.environ.get("ACTIVITY_EVENTS_FILE")
    if path:
        with open(path) as f:
            return json.load(f)
    req = urllib.request.Request(
        f"https://api.github.com/users/{USER}/events/public?per_page=100",
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER},
    )
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def link(repo):
    return f"[{repo}](https://github.com/{repo})"


def describe(event):
    """Return (line, dedupe_key) for an event, or None to skip it."""
    kind = event.get("type")
    repo = event.get("repo", {}).get("name", "")
    payload = event.get("payload", {}) or {}
    if repo in SKIP_REPOS:
        return None

    if kind == "ReleaseEvent" and payload.get("action") == "published":
        release = payload.get("release", {})
        name = release.get("name") or release.get("tag_name") or "a release"
        url = release.get("html_url") or f"https://github.com/{repo}/releases"
        return f"🏷️ Released [{name}]({url}) of {link(repo)}", ("release", url)

    if kind == "PullRequestEvent":
        pr = payload.get("pull_request", {})
        url = pr.get("html_url") or f"https://github.com/{repo}/pull/{payload.get('number', '')}"
        number = pr.get("number") or payload.get("number")
        title = pr.get("title")
        label = f"#{number}" + (f": {title}" if title else "")
        action = payload.get("action")
        if action == "closed" and pr.get("merged"):
            return f"🎉 Merged PR [{label}]({url}) in {link(repo)}", ("pr", url)
        if action == "opened":
            return f"💪 Opened PR [{label}]({url}) in {link(repo)}", ("pr", url)
        return None

    if kind == "IssuesEvent" and payload.get("action") in ("opened", "closed"):
        issue = payload.get("issue", {})
        url = issue.get("html_url", f"https://github.com/{repo}/issues")
        verb = "Opened" if payload["action"] == "opened" else "Closed"
        return f"❗ {verb} issue [#{issue.get('number')}]({url}) in {link(repo)}", ("issue", url, verb)

    if kind == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"✨ Created repository {link(repo)}", ("create", repo)

    if kind == "PushEvent":
        # Many pushes to one repo collapse into a single line.
        return f"🔨 Pushed to {link(repo)}", ("push", repo)

    if kind == "PublicEvent":
        return f"🔓 Made {link(repo)} public", ("public", repo)

    return None


def build_lines(events):
    lines, seen = [], set()
    for event in events:
        described = describe(event)
        if not described:
            continue
        line, key = described
        if key in seen:
            continue
        seen.add(key)
        date = (event.get("created_at") or "")[:10]
        lines.append(f"{len(lines) + 1}. {line} <sub>{date}</sub>")
        if len(lines) >= LIMIT:
            break
    return lines


def main():
    lines = build_lines(fetch_events())
    if not lines:
        print("No public activity found; leaving README unchanged.")
        return 0

    with open(README) as f:
        readme = f.read()
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(readme):
        print(f"Markers not found in {README}", file=sys.stderr)
        return 1

    block = START + "\n" + "\n".join(lines) + "\n" + END
    updated = pattern.sub(lambda _: block, readme, count=1)
    if updated != readme:
        with open(README, "w") as f:
            f.write(updated)
        print(f"Updated {README} with {len(lines)} items.")
    else:
        print("Activity unchanged.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
