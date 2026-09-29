"""Spotify now-playing + recently-played, fetched on demand and cached briefly.

Nothing here is written to the database: the music window is a live view, not history
we need to keep. Only track name, artist, album art and link are exposed.
"""

import asyncio
import base64
import time
from typing import Any

import httpx

from .config import Settings

TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"
CACHE_SECONDS = 30


def _artists(track: dict[str, Any]) -> str:
    return ", ".join(a.get("name", "") for a in track.get("artists") or [])


def _art(track: dict[str, Any]) -> str | None:
    images = (track.get("album") or {}).get("images") or []
    # Spotify lists largest first; pick the smallest that is still >= 64px.
    usable = [i for i in images if (i.get("width") or 0) >= 64] or images
    return usable[-1]["url"] if usable else None


def normalize(current: dict[str, Any] | None, recent: dict[str, Any] | None) -> dict[str, Any]:
    now_playing = None
    if current and current.get("currently_playing_type") == "track" and current.get("item"):
        t = current["item"]
        now_playing = {
            "title": t.get("name"),
            "artist": _artists(t),
            "album": (t.get("album") or {}).get("name"),
            "art": _art(t),
            "url": (t.get("external_urls") or {}).get("spotify"),
            "progress_ms": current.get("progress_ms") or 0,
            "duration_ms": t.get("duration_ms") or 0,
            "is_playing": bool(current.get("is_playing")),
        }

    tracks = []
    for item in (recent or {}).get("items") or []:
        t = item.get("track") or {}
        tracks.append({
            "title": t.get("name"),
            "artist": _artists(t),
            "art": _art(t),
            "url": (t.get("external_urls") or {}).get("spotify"),
            "played_at": item.get("played_at"),
        })
    return {"enabled": True, "now_playing": now_playing, "recent": tracks}


class SpotifyClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._token: str | None = None
        self._token_expires = 0.0
        self._cache: dict[str, Any] | None = None
        self._cache_at = 0.0
        self._lock = asyncio.Lock()

    @property
    def enabled(self) -> bool:
        return self.settings.spotify_enabled

    async def _access_token(self, client: httpx.AsyncClient) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        basic = base64.b64encode(
            f"{self.settings.spotify_client_id}:{self.settings.spotify_client_secret}".encode()
        ).decode()
        r = await client.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": self.settings.spotify_refresh_token},
            headers={"Authorization": f"Basic {basic}"},
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    async def music(self, client: httpx.AsyncClient) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "now_playing": None, "recent": []}
        async with self._lock:
            if self._cache and time.time() - self._cache_at < CACHE_SECONDS:
                return self._cache
            try:
                headers = {"Authorization": f"Bearer {await self._access_token(client)}"}
                cur, rec = await asyncio.gather(
                    client.get(f"{API}/me/player/currently-playing", headers=headers),
                    client.get(f"{API}/me/player/recently-played", params={"limit": 20}, headers=headers),
                )
                rec.raise_for_status()
                current = cur.json() if cur.status_code == 200 and cur.content else None
                self._cache = normalize(current, rec.json())
                self._cache_at = time.time()
            except (httpx.HTTPError, KeyError, ValueError):
                if self._cache is None:
                    raise
                # Serve stale data rather than failing the page; retry on the next request after the TTL.
                self._cache_at = time.time()
            return self._cache
