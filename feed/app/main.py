"""Activity feed API for didriksi.com.

Served behind nginx at /api/:
    GET    /feed?limit=30&before=<iso>&source=github,leetcode
    GET    /music
    POST   /status          (X-API-Key)   manual status update
    DELETE /status/{id}     (X-API-Key)
    GET    /health
"""

import asyncio
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field, HttpUrl

from .config import Settings
from .models import Event, parse_iso
from .sources import enabled_sources
from .spotify import SpotifyClient
from .store import Store

log = logging.getLogger("feed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

MAX_BACKOFF = 3600
SOURCES = {"github", "leetcode", "letterboxd", "status"}


async def poll_forever(source, client: httpx.AsyncClient, store: Store) -> None:
    """Poll one source on its interval; back off exponentially on failures."""
    delay = source.interval
    while True:
        try:
            events = await source.fetch(client, store)
            new = store.upsert(events)
            if new:
                log.info("%s: %d new event(s)", source.name, new)
            delay = source.interval
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # one broken source must never take down the others
            delay = min(delay * 2, MAX_BACKOFF)
            log.warning("%s: fetch failed (%s); retrying in %ds", source.name, exc, delay)
        await asyncio.sleep(delay)


def create_app(settings: Settings | None = None, start_pollers: bool = True) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.db_path)
    spotify = SpotifyClient(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            app.state.client = client
            tasks = []
            if start_pollers:
                sources = enabled_sources(settings)
                log.info("enabled sources: %s; spotify: %s",
                         ", ".join(s.name for s in sources) or "none", spotify.enabled)
                tasks = [asyncio.create_task(poll_forever(s, client, store)) for s in sources]
            yield
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="didriksi.com feed", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store

    def require_key(x_api_key: str = Header(default="")) -> None:
        if not settings.api_key or not secrets.compare_digest(x_api_key, settings.api_key):
            raise HTTPException(status_code=401, detail="invalid API key")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/feed")
    def feed(
        response: Response,
        limit: int = Query(30, ge=1, le=100),
        before: str | None = None,
        source: str | None = None,
    ):
        try:
            before_dt = parse_iso(before) if before else None
        except ValueError:
            raise HTTPException(status_code=400, detail="before must be an ISO-8601 timestamp")
        wanted = [s for s in (source or "").split(",") if s in SOURCES] or None
        events, has_more = store.query(limit=limit, before=before_dt, sources=wanted)
        response.headers["Cache-Control"] = "public, max-age=30"
        return {"events": [e.to_json() for e in events], "has_more": has_more}

    @app.get("/music")
    async def music(response: Response):
        try:
            data = await spotify.music(app.state.client)
        except Exception as exc:
            log.warning("spotify: %s", exc)
            raise HTTPException(status_code=502, detail="spotify unavailable")
        response.headers["Cache-Control"] = "public, max-age=15"
        return data

    class StatusIn(BaseModel):
        text: str = Field(min_length=1, max_length=280)
        url: HttpUrl | None = None

    @app.post("/status", status_code=201, dependencies=[Depends(require_key)])
    def post_status(body: StatusIn):
        ev = Event(
            id=f"status:{uuid.uuid4().hex[:12]}",
            source="status",
            kind="post",
            title=body.text.strip(),
            ts=datetime.now(timezone.utc),
            url=str(body.url) if body.url else None,
        )
        store.upsert([ev])
        return ev.to_json()

    @app.delete("/status/{event_id}", status_code=204, dependencies=[Depends(require_key)])
    def delete_status(event_id: str):
        if not event_id.startswith("status:") or not store.delete(event_id):
            raise HTTPException(status_code=404, detail="not found")

    return app



