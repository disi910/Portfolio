import json
from datetime import datetime, timezone
from pathlib import Path

from app import spotify
from app.sources import github, leetcode

FIX = Path(__file__).parent / "fixtures"


def test_github_normalize_known_types():
    events = github.normalize(json.loads((FIX / "github_events.json").read_text()))
    by_id = {e.id: e for e in events}

    # Unmerged PR close, branch creation and unknown types are dropped.
    assert set(by_id) == {"github:50001", "github:50002", "github:50003", "github:50005", "github:50007", "github:50008"}

    trimmed = by_id["github:50001"]  # new-style payload with no commit list
    assert trimmed.title == "Pushed to disi910/Portfolio"
    assert trimmed.detail is None
    assert trimmed.meta["head"] == "abcdef1234567890"
    assert trimmed.url.endswith("/compare/1234567890ab...abcdef123456")

    full = by_id["github:50002"]
    assert full.title == "Pushed 2 commits to disi910/CourseCatalog"
    assert full.detail == "Add Win98 theme"  # first line of the latest commit

    assert by_id["github:50003"].title == "Merged PR #13 in disi910/CourseCatalog"
    assert by_id["github:50003"].detail == "Fix API vulnerabilities"
    assert by_id["github:50005"].kind == "create_repo"
    assert by_id["github:50007"].title == "Released v1.2.0 of disi910/claude-usage-bar"
    assert by_id["github:50008"].title == "Starred torvalds/linux"
    assert full.ts == datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc)


def test_github_new_branch_push_links_to_repo():
    raw = [{"id": "1", "type": "PushEvent", "created_at": "2026-01-01T00:00:00Z", "repo": {"name": "a/b"},
            "payload": {"head": "abc", "before": "0000000000000000000000000000000000000000", "size": 1}}]
    [ev] = github.normalize(raw)
    assert ev.url == "https://github.com/a/b"
    assert ev.title == "Pushed 1 commit to a/b"


def test_leetcode_normalize():
    subs = [
        {"id": "900", "title": "Two Sum", "titleSlug": "two-sum", "timestamp": "1790000000", "lang": "python3"},
        {"id": "901", "title": "Mystery", "titleSlug": "mystery", "timestamp": "1790000100", "lang": "zig"},
    ]
    questions = {"two-sum": {"questionFrontendId": "1", "difficulty": "Easy"}}
    a, b = leetcode.normalize(subs, questions)
    assert a.id == "leetcode:900"
    assert a.title == "Solved 1. Two Sum"
    assert a.url == "https://leetcode.com/problems/two-sum/"
    assert a.meta == {"difficulty": "Easy", "lang": "Python3"}
    assert b.title == "Solved Mystery"  # no question metadata cached
    assert b.meta["lang"] == "zig"


def test_spotify_normalize():
    data = spotify.normalize(
        json.loads((FIX / "spotify_current.json").read_text()),
        json.loads((FIX / "spotify_recent.json").read_text()),
    )
    np = data["now_playing"]
    assert np["title"] == "Everything In Its Right Place"
    assert np["artist"] == "Radiohead"
    assert np["art"] == "https://i.scdn.co/image/64"
    assert np["is_playing"] is True
    assert np["progress_ms"] == 94000

    assert [t["title"] for t in data["recent"]] == ["Nights", "Get Lucky"]
    assert data["recent"][1]["artist"] == "Daft Punk, Pharrell Williams"
    assert data["recent"][0]["art"] is None


def test_spotify_ignores_podcasts_and_idle():
    assert spotify.normalize({"currently_playing_type": "episode", "item": None}, None)["now_playing"] is None
    assert spotify.normalize(None, None) == {"enabled": True, "now_playing": None, "recent": []}
