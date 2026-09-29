"""GitHub public activity via the Events API.

GitHub has been trimming PushEvent payloads (commit lists may be absent), so the
normalizer works from `head`/`before`/`ref` alone and the poller optionally looks up
the head commit's message for pushes it hasn't stored yet.
"""

import logging
from typing import Any

import httpx

from ..models import Event, parse_iso
from ..store import Store

log = logging.getLogger(__name__)

API = "https://api.github.com"
MAX_COMMIT_LOOKUPS = 5  # per poll, keeps unauthenticated use well under 60 req/h


def _repo_url(name: str) -> str:
    return f"https://github.com/{name}"


def _first_line(msg: str | None) -> str | None:
    return msg.strip().splitlines()[0][:200] if msg and msg.strip() else None


def normalize(raw_events: list[dict[str, Any]]) -> list[Event]:
    out: list[Event] = []
    for ev in raw_events:
        etype = ev.get("type")
        repo = (ev.get("repo") or {}).get("name", "")
        p = ev.get("payload") or {}
        ts = parse_iso(ev["created_at"])
        eid = f"github:{ev['id']}"

        if etype == "PushEvent":
            commits = p.get("commits") or []
            n = p.get("distinct_size") or p.get("size") or len(commits)
            branch = (p.get("ref") or "").removeprefix("refs/heads/")
            title = f"Pushed {n} commit{'s' if n != 1 else ''} to {repo}" if n else f"Pushed to {repo}"
            head, before = p.get("head"), p.get("before")
            url = f"{_repo_url(repo)}/compare/{before[:12]}...{head[:12]}" if head and before and set(before) != {"0"} else _repo_url(repo)
            detail = _first_line(commits[-1].get("message")) if commits else None
            out.append(Event(eid, "github", "push", title, ts, url, detail,
                             {"repo": repo, "count": n, "branch": branch, "head": head}))

        elif etype == "PullRequestEvent":
            action = p.get("action")
            pr = p.get("pull_request") or {}
            num = p.get("number") or pr.get("number")
            url = pr.get("html_url") or f"{_repo_url(repo)}/pull/{num}"
            if action == "opened":
                kind, verb = "pr_opened", "Opened"
            elif action == "closed" and pr.get("merged"):
                kind, verb = "pr_merged", "Merged"
            else:
                continue
            out.append(Event(eid, "github", kind, f"{verb} PR #{num} in {repo}", ts, url,
                             _first_line(pr.get("title")), {"repo": repo}))

        elif etype == "CreateEvent" and p.get("ref_type") == "repository":
            out.append(Event(eid, "github", "create_repo", f"Created repository {repo}", ts,
                             _repo_url(repo), _first_line(p.get("description")), {"repo": repo}))

        elif etype == "ReleaseEvent" and p.get("action") == "published":
            rel = p.get("release") or {}
            tag = rel.get("tag_name") or "a new version"
            out.append(Event(eid, "github", "release", f"Released {tag} of {repo}", ts,
                             rel.get("html_url") or f"{_repo_url(repo)}/releases", _first_line(rel.get("name")),
                             {"repo": repo, "tag": tag}))

        elif etype == "WatchEvent":
            out.append(Event(eid, "github", "star", f"Starred {repo}", ts, _repo_url(repo), None, {"repo": repo}))

        elif etype == "ForkEvent":
            out.append(Event(eid, "github", "fork", f"Forked {repo}", ts, _repo_url(repo), None, {"repo": repo}))

        elif etype == "PublicEvent":
            out.append(Event(eid, "github", "public", f"Open-sourced {repo}", ts, _repo_url(repo), None, {"repo": repo}))

    return out


class GitHubSource:
    name = "github"
    interval = 300

    def __init__(self, username: str, token: str = ""):
        self.username = username
        self.headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self._etag: str | None = None

    async def fetch(self, client: httpx.AsyncClient, store: Store) -> list[Event]:
        headers = dict(self.headers)
        if self._etag:
            headers["If-None-Match"] = self._etag
        r = await client.get(f"{API}/users/{self.username}/events/public", params={"per_page": 100}, headers=headers)
        if r.status_code == 304:
            return []
        r.raise_for_status()
        self._etag = r.headers.get("ETag")
        events = normalize(r.json())

        # Fill in commit messages for new pushes whose payload had no commit list.
        lookups = 0
        for ev in events:
            if ev.kind != "push" or ev.detail or not ev.meta.get("head") or store.has(ev.id):
                continue
            if lookups >= MAX_COMMIT_LOOKUPS:
                break
            lookups += 1
            try:
                c = await client.get(f"{API}/repos/{ev.meta['repo']}/commits/{ev.meta['head']}", headers=self.headers)
                if c.status_code == 200:
                    ev.detail = _first_line((c.json().get("commit") or {}).get("message"))
            except httpx.HTTPError as exc:
                log.debug("commit lookup failed: %s", exc)
        return events
