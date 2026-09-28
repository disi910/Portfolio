# Portfolio

Personal portfolio site at **didriksi.com** — a Docker Compose monorepo with a Windows 98-style landing page (about, live activity feed, Spotify player, projects), the CourseCatalog app, and the HousingMarketClassifier write-up.

## Deployment (VPS)

### Prerequisites
- Docker and Docker Compose installed on the VPS
- SSL certificates from Let's Encrypt at `/etc/letsencrypt/`
- A `.env` file in the project root with production secrets:
  ```
  DB_PASSWORD=<postgres password>
  SECRET_KEY=<api secret key>
  API_KEY=<api key>
  # optional activity feed settings - see .env.example
  ```

### Deploy
```bash
ssh user@didriksi.com
cd ~/Portfolio
git pull --recurse-submodules
git submodule update --init --recursive   # Ensure submodule is checked out
docker compose up --build -d
docker compose restart nginx              # Refresh upstream DNS after rebuild
```

### After schema changes
If the CourseCatalog API fails with `column ... does not exist`, a migration is needed.
Alembic may fail on existing objects — in that case, apply the change manually:
```bash
docker compose exec coursecatalog-db psql -U postgres -d coursecatalog -c "<ALTER TABLE ...>"
docker compose restart coursecatalog-api
```

### Troubleshooting
- **502 Bad Gateway**: Nginx has stale container IPs after a rebuild. Fix: `docker compose restart nginx`
- **API 500 errors**: Check `docker compose logs coursecatalog-api` — usually a missing DB column or failed migration
- **Submodule not updated**: `git pull --recurse-submodules` fetches but doesn't checkout. Run `git submodule update --init --recursive` separately
- **`docker compose restart` appears frozen**: This is normal — it completes but doesn't always print "done". Verify with `docker compose ps`

### Useful commands
```bash
docker compose logs -f              # Follow all logs
docker compose logs -f nginx        # Follow specific service
docker compose down                 # Stop all services
docker compose ps                   # Check running containers
docker compose exec coursecatalog-db psql -U postgres -d coursecatalog  # DB shell
```

### Architecture
All traffic enters via Nginx on ports 80/443:
- `/` → static landing page
- `/coursecatalog/` → CourseCatalog React SPA
- `/coursecatalog/api/` → CourseCatalog FastAPI backend
- `/housingclassifier/` → HousingMarketClassifier static page
- `/api/` → activity feed service (`feed/`, FastAPI + SQLite)

## Design system
All pages share `landing/assets/css/win98.css` (tokens + window, button, taskbar, list-view components) and the icons in `landing/assets/icons/`. Pages add their own layout CSS (`home.css`, `project.css`) and include the same taskbar markup plus `assets/js/taskbar.js`. CourseCatalog vendors a copy of the same tokens in its own repo so it builds standalone.

Preview locally without the backend: `cd landing && python3 -m http.server 8765`, then open `http://localhost:8765/?demo` (the `?demo` flag renders bundled sample data from `landing/assets/demo/`).

## Activity feed (`feed/`)
Polls public activity into SQLite and serves it to the landing page:

| Source | What shows up | Config | Poll |
|---|---|---|---|
| GitHub | pushes, merged/opened PRs, new repos, releases, stars | `GITHUB_USERNAME`, optional `GITHUB_TOKEN` | 5 min |
| LeetCode | accepted submissions with difficulty | `LEETCODE_USERNAME` | 10 min |
| Letterboxd | films logged, with rating | `LETTERBOXD_USERNAME` | 30 min |
| Status | manual one-liners you post | `FEED_API_KEY` | — |
| Spotify | now playing + recently played (separate window, not stored) | `SPOTIFY_CLIENT_ID/SECRET/REFRESH_TOKEN` | on request, 30 s cache |

Every source is optional; one failing source backs off (up to 1 h) without affecting the others.

Endpoints (behind `/api/`): `GET /feed?limit=&before=&source=`, `GET /music`, `POST /status`, `DELETE /status/{id}`, `GET /health`.

**Spotify setup (one time):** create an app at developer.spotify.com with redirect URI `http://127.0.0.1:8888/callback`, then on your own machine run
`SPOTIFY_CLIENT_ID=... SPOTIFY_CLIENT_SECRET=... python feed/scripts/spotify_auth.py` and put the printed refresh token in `.env`.

**Post a status:**
```bash
curl -X POST https://didriksi.com/api/status -H "X-API-Key: $FEED_API_KEY" \
     -H "Content-Type: application/json" -d '{"text": "Exam prep week", "url": null}'
```

**Privacy:** the feed only uses public data (public GitHub events, public LeetCode/Letterboxd profiles). Spotify is the exception — it exposes what you're listening to in near real time, so leave its variables empty if you don't want that.

**Tests:** `cd feed && pip install -r requirements-dev.txt && pytest`

HTTP is redirected to HTTPS. SSL certs are mounted from the host's `/etc/letsencrypt/`.

