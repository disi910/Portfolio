from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Event:
    """One entry in the activity timeline.

    `id` is "<source>:<native id>" so re-fetching the same item is an idempotent upsert.
    """

    id: str
    source: str          # github | leetcode | status
    kind: str            # push, pr_merged, solved, post, ...
    title: str
    ts: datetime         # timezone-aware, UTC
    url: str | None = None
    detail: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "kind": self.kind,
            "title": self.title,
            "url": self.url,
            "detail": self.detail,
            "ts": iso(self.ts),
            "meta": self.meta,
        }


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
