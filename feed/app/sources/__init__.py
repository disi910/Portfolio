"""Timeline sources. Each exposes `name`, `interval` (seconds) and
`async fetch(client, store) -> list[Event]`."""

from ..config import Settings
from .github import GitHubSource
from .leetcode import LeetCodeSource
from .letterboxd import LetterboxdSource


def enabled_sources(settings: Settings) -> list:
    sources: list = []
    if settings.github_username:
        sources.append(GitHubSource(settings.github_username, settings.github_token))
    if settings.leetcode_username:
        sources.append(LeetCodeSource(settings.leetcode_username))
    if settings.letterboxd_username:
        sources.append(LetterboxdSource(settings.letterboxd_username))
    return sources
