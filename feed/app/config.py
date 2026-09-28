"""Settings read from environment variables. Every source is optional:
a source runs only when the variables it needs are set."""

import os
from dataclasses import dataclass, field


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: _env("FEED_DB_PATH") or "feed.db")
    api_key: str = field(default_factory=lambda: _env("FEED_API_KEY"))

    github_username: str = field(default_factory=lambda: _env("GITHUB_USERNAME"))
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN"))

    leetcode_username: str = field(default_factory=lambda: _env("LEETCODE_USERNAME"))

    letterboxd_username: str = field(default_factory=lambda: _env("LETTERBOXD_USERNAME"))

    spotify_client_id: str = field(default_factory=lambda: _env("SPOTIFY_CLIENT_ID"))
    spotify_client_secret: str = field(default_factory=lambda: _env("SPOTIFY_CLIENT_SECRET"))
    spotify_refresh_token: str = field(default_factory=lambda: _env("SPOTIFY_REFRESH_TOKEN"))

    @property
    def spotify_enabled(self) -> bool:
        return bool(self.spotify_client_id and self.spotify_client_secret and self.spotify_refresh_token)
