"""Accepted LeetCode submissions via leetcode.com's (unofficial) GraphQL endpoint.

LeetCode only exposes the ~20 most recent accepted submissions publicly, so this must
poll often enough not to miss any on a busy day.
"""

from datetime import datetime, timezone
from typing import Any

import httpx

from ..models import Event
from ..store import Store

GRAPHQL = "https://leetcode.com/graphql"
HEADERS = {
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com/",
    "User-Agent": "Mozilla/5.0 (compatible; didriksi.com activity feed)",
}

RECENT_QUERY = """
query recentAc($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) { id title titleSlug timestamp lang }
}"""

QUESTION_QUERY = """
query q($titleSlug: String!) {
  question(titleSlug: $titleSlug) { questionFrontendId difficulty }
}"""

LANGS = {"python3": "Python3", "python": "Python", "cpp": "C++", "java": "Java", "javascript": "JavaScript",
         "typescript": "TypeScript", "golang": "Go", "rust": "Rust", "c": "C", "csharp": "C#", "kotlin": "Kotlin"}


def normalize(submissions: list[dict[str, Any]], questions: dict[str, dict[str, Any]]) -> list[Event]:
    out = []
    for s in submissions:
        q = questions.get(s["titleSlug"], {})
        num = q.get("questionFrontendId")
        title = f"Solved {num}. {s['title']}" if num else f"Solved {s['title']}"
        out.append(Event(
            id=f"leetcode:{s['id']}",
            source="leetcode",
            kind="solved",
            title=title,
            ts=datetime.fromtimestamp(int(s["timestamp"]), tz=timezone.utc),
            url=f"https://leetcode.com/problems/{s['titleSlug']}/",
            meta={"difficulty": q.get("difficulty"), "lang": LANGS.get(s.get("lang", ""), s.get("lang"))},
        ))
    return out


class LeetCodeSource:
    name = "leetcode"
    interval = 600

    def __init__(self, username: str):
        self.username = username
        self._questions: dict[str, dict[str, Any]] = {}  # slug -> {questionFrontendId, difficulty}

    async def _gql(self, client: httpx.AsyncClient, query: str, variables: dict) -> dict:
        r = await client.post(GRAPHQL, json={"query": query, "variables": variables}, headers=HEADERS)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"LeetCode GraphQL error: {body['errors'][0].get('message')}")
        return body["data"]

    async def fetch(self, client: httpx.AsyncClient, store: Store) -> list[Event]:
        data = await self._gql(client, RECENT_QUERY, {"username": self.username, "limit": 20})
        subs = data.get("recentAcSubmissionList") or []
        for slug in {s["titleSlug"] for s in subs} - self._questions.keys():
            q = (await self._gql(client, QUESTION_QUERY, {"titleSlug": slug})).get("question")
            if q:
                self._questions[slug] = q
        return normalize(subs, self._questions)
