"""Films logged on Letterboxd, from the public profile RSS feed."""

from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from ..models import Event
from ..store import Store


def _rating(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def normalize(rss_text: str) -> list[Event]:
    feed = feedparser.parse(rss_text)
    out = []
    for item in feed.entries:
        film = item.get("letterboxd_filmtitle")
        if not film:  # lists and other non-diary items
            continue
        year = item.get("letterboxd_filmyear")
        parsed = item.get("published_parsed") or item.get("updated_parsed")
        if not parsed:
            continue
        rewatch = (item.get("letterboxd_rewatch") or "").lower() == "yes"
        out.append(Event(
            id=f"letterboxd:{item.get('id') or item.get('link')}",
            source="letterboxd",
            kind="watched",
            title=f"{'Rewatched' if rewatch else 'Watched'} {film}" + (f" ({year})" if year else ""),
            ts=datetime.fromtimestamp(timegm(parsed), tz=timezone.utc),
            url=item.get("link"),
            meta={"rating": _rating(item.get("letterboxd_memberrating")), "rewatch": rewatch},
        ))
    return out


class LetterboxdSource:
    name = "letterboxd"
    interval = 1800

    def __init__(self, username: str):
        self.url = f"https://letterboxd.com/{username}/rss/"

    async def fetch(self, client: httpx.AsyncClient, store: Store) -> list[Event]:
        r = await client.get(self.url, headers={"User-Agent": "didriksi.com activity feed"})
        r.raise_for_status()
        return normalize(r.text)
