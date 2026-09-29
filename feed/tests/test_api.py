from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Event
from app.store import Store

T0 = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def ev(i: int, source: str = "github") -> Event:
    return Event(id=f"{source}:{i}", source=source, kind="x", title=f"event {i}", ts=T0 - timedelta(hours=i))


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "feed.db"), api_key="secret"), start_pollers=False)
    with TestClient(app) as c:
        yield c


def test_store_upsert_is_idempotent(tmp_path):
    store = Store(str(tmp_path / "s.db"))
    assert store.upsert([ev(1), ev(2)]) == 2
    changed = ev(1)
    changed.title = "renamed"
    assert store.upsert([changed, ev(3)]) == 1
    events, has_more = store.query(limit=10)
    assert [e.id for e in events] == ["github:1", "github:2", "github:3"]
    assert events[0].title == "renamed"
    assert has_more is False


def test_feed_pagination_and_filter(client):
    store = client.app.state.store
    store.upsert([ev(i) for i in range(5)] + [ev(10, "leetcode")])

    page = client.get("/feed", params={"limit": 3}).json()
    assert [e["id"] for e in page["events"]] == ["github:0", "github:1", "github:2"]
    assert page["has_more"] is True
    assert page["events"][0]["ts"] == "2026-09-28T12:00:00Z"

    rest = client.get("/feed", params={"limit": 3, "before": page["events"][-1]["ts"]}).json()
    assert [e["id"] for e in rest["events"]] == ["github:3", "github:4", "leetcode:10"]
    assert rest["has_more"] is False

    only_lc = client.get("/feed", params={"source": "leetcode,bogus"}).json()
    assert [e["id"] for e in only_lc["events"]] == ["leetcode:10"]


def test_feed_rejects_bad_before(client):
    assert client.get("/feed", params={"before": "yesterday"}).status_code == 400


def test_music_disabled_without_credentials(client):
    assert client.get("/music").json() == {"enabled": False, "now_playing": None, "recent": []}


def test_status_requires_key_and_roundtrips(client):
    assert client.post("/status", json={"text": "hi"}).status_code == 401
    assert client.post("/status", json={"text": "hi"}, headers={"X-API-Key": "wrong"}).status_code == 401

    r = client.post("/status", json={"text": "  Exam prep week  "}, headers={"X-API-Key": "secret"})
    assert r.status_code == 201
    created = r.json()
    assert created["title"] == "Exam prep week"
    assert created["source"] == "status"

    feed = client.get("/feed").json()["events"]
    assert feed[0]["id"] == created["id"]

    assert client.delete(f"/status/{created['id']}", headers={"X-API-Key": "secret"}).status_code == 204
    assert client.delete("/status/github:1", headers={"X-API-Key": "secret"}).status_code == 404


def test_status_disabled_when_no_key_configured(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "f.db"), api_key=""), start_pollers=False)
    with TestClient(app) as c:
        assert c.post("/status", json={"text": "x"}, headers={"X-API-Key": ""}).status_code == 401
