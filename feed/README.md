# Activity feed service

FastAPI service behind `https://didriksi.com/api/`. It polls public activity into SQLite for the landing page's live feed, and serves Spotify now-playing for the music window.

## Sources

| Source | What shows up | Config (`.env`) | Poll |
|---|---|---|---|
| GitHub | pushes (with commit message), merged/opened PRs, new repos, releases, stars | `GITHUB_USERNAME`, optional `GITHUB_TOKEN` | 5 min |
| LeetCode | accepted submissions, with number, difficulty and language | `LEETCODE_USERNAME` | 10 min |
| Letterboxd | films logged in the diary, with rating | `LETTERBOXD_USERNAME` | 30 min |
| Status | manual one-liners you post | `FEED_API_KEY` | instant |
| Spotify | now playing + last 20 tracks (music window, not stored) | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REFRESH_TOKEN` | on request, 30 s cache |

- Every source is optional; it runs only if its variables are set. The startup log lists the enabled ones: `enabled sources: github, leetcode, letterboxd; spotify: True`.
- A failing source backs off exponentially (up to 1 hour) without affecting the others.
- Events are stored with IDs like `github:<id>`, so re-fetching is idempotent.
- Only public data is used, except Spotify, which shows what you're listening to in near real time.
- GitHub only shows public activity. Without `GITHUB_TOKEN` the API allows 60 requests an hour; with a token (fine-grained, public repositories, no permissions), 5,000.
- LeetCode has no official API. The service uses leetcode.com's own GraphQL endpoint, which can change or block server IPs.

Poll intervals are the `interval` attributes in `app/sources/*.py`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/feed?limit=30&before=<iso>&source=github,leetcode` | newest first, `{events, has_more}` |
| GET | `/music` | `{enabled, now_playing, recent}` |
| POST | `/status` | header `X-API-Key: $FEED_API_KEY`, body `{"text": "...", "url": null}` |
| DELETE | `/status/{id}` | same header |
| GET | `/health` | `{"ok": true}` |

nginx serves these under `/api/` (for example `https://didriksi.com/api/feed`), rate-limited to 30 requests/min per IP.

## Spotify setup (one time)

1. Create an app at https://developer.spotify.com/dashboard with the redirect URI `http://127.0.0.1:8888/callback` (not `localhost`), and tick **Web API**. If the dashboard has **User Management**, add your own Spotify email.
2. On your own computer (the login redirects to your browser), run:
   ```bash
   SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... python scripts/spotify_auth.py
   ```
3. Open the printed URL, approve, and copy the printed `SPOTIFY_REFRESH_TOKEN` into `.env`. It's one unbroken string of letters, digits, `-` and `_`; nothing may follow it.

## Run locally

Python 3.10+. Use `python -m ...`, so the virtualenv's interpreter runs even if another environment, such as conda's `(base)`, is active.

```bash
cd feed
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements-dev.txt
export GITHUB_USERNAME=disi910 LEETCODE_USERNAME=LordQuas LETTERBOXD_USERNAME=didster2   # any sources you want
python -m uvicorn app.main:create_app --factory --port 8000     # terminal 1
python scripts/dev_site.py                                       # terminal 2, then open http://127.0.0.1:8080
```

`scripts/dev_site.py` serves `../landing` and forwards `/api/` to port 8000, like nginx does in production.

## Tests

```bash
python -m pytest
```

The tests use recorded fixtures in `tests/fixtures/`, so they need no network.

## Layout

```
app/main.py        app factory, endpoints, per-source polling loops with backoff
app/store.py       SQLite store (upsert, paginated query)
app/spotify.py     token refresh + now playing / recently played, cached
app/sources/       github.py, leetcode.py, letterboxd.py (fetch + normalize)
scripts/           spotify_auth.py (one-time OAuth), dev_site.py (local preview)
tests/             normalizer, store and API tests
```
