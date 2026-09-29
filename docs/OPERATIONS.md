# Operating didriksi.com

How the production deployment works, and how to run it day to day. For building a server from scratch, see [DEPLOY.md](../DEPLOY.md).

## Production at a glance

| | |
|---|---|
| Host | netcup VPS nano, Debian 13 "trixie", x86_64 |
| Domain | `didriksi.com` + `www.didriksi.com` (Namecheap BasicDNS, two A records, no AAAA) |
| Login | `ssh deploy@didriksi.com` (SSH key only; root and password login disabled) |
| Code | `/home/deploy/Portfolio` (this repo, with `CourseCatalog` and `DataNorge` as git submodules) |
| Secrets | `/home/deploy/Portfolio/.env` (mode 600, never committed; see [.env.example](../.env.example)) |
| TLS | Let's Encrypt, `/etc/letsencrypt/live/didriksi.com/`, auto-renewed by certbot's systemd timer |
| Firewall | ufw: only 22, 80 and 443 open. Only the `nginx` container publishes ports. |
| Backups | `~/backup.sh` via cron at 03:15 into `~/backups` (7 days kept) |

## How a request flows

```
Browser ──HTTPS──▶ nginx (container, ports 80/443, certs mounted read-only from the host)
                     │
                     ├── /                   ▶ landing                 static Win98 site
                     ├── /housingclassifier/ ▶ landing                 static project page
                     ├── /api/               ▶ feed                    FastAPI + SQLite (activity feed, Spotify)
                     ├── /coursecatalog/     ▶ coursecatalog-frontend  React build served by nginx
                     ├── /coursecatalog/api/ ▶ coursecatalog-api       FastAPI ▶ coursecatalog-db (Postgres 16)
                     ├── /datanorge/         ▶ datanorge-web           React + MapLibre build served by nginx
                     └── /datanorge/api/     ▶ datanorge-api           FastAPI (GET only) ▶ datanorge-db (PostGIS)
```

- HTTP (port 80) always redirects to `https://didriksi.com`.
- nginx strips the path prefix before forwarding, so each app sees its own routes from `/`. The two React apps are built with their sub-path baked in (`/coursecatalog/`, and `/datanorge/` via the `VITE_BASE_PATH` build arg).
- `/api/` is rate-limited to 30 requests/min per IP (burst 20), and `/datanorge/api/` to 120/min (burst 40).
- Config lives in [`nginx/nginx.conf`](../nginx/nginx.conf) and [`docker-compose.yml`](../docker-compose.yml).

## Services, data and volumes

| Service | Built from | Stores data in |
|---|---|---|
| `nginx` | `nginx:alpine` + `nginx/nginx.conf` | nothing |
| `landing` | `landing/Dockerfile` | nothing (static files baked into the image) |
| `feed` | `feed/Dockerfile` | volume `portfolio_feeddata` (SQLite, re-fetchable) |
| `coursecatalog-frontend` | `CourseCatalog/apps/web/ififag` | nothing |
| `coursecatalog-api` | `CourseCatalog/apps/api` | nothing |
| `coursecatalog-db` | `postgres:16-alpine` | volume `portfolio_pgdata` (**back up**) |
| `datanorge-web` | `DataNorge/infra/Dockerfile.web.prod` | nothing |
| `datanorge-api` | `DataNorge/infra/Dockerfile.api` (also contains the `pipeline` CLI) | nothing |
| `datanorge-db` | `postgis/postgis:16-3.4` | volume `portfolio_datanorge-pgdata` (**back up**) |

Every service has `restart: unless-stopped`, and Docker starts on boot, so the whole site comes back by itself after a reboot.

Database passwords are fixed when a volume is first created. Changing `DB_PASSWORD` or `DATANORGE_DB_PASSWORD` in `.env` later does **not** change the database's password; it only locks the API out.

## Deploying an update

The normal flow is: merge a pull request on GitHub, then pull on the server.

```bash
ssh deploy@didriksi.com
cd ~/Portfolio
git pull
git submodule update --init --recursive
docker compose up -d --build
docker compose restart nginx     # always after a rebuild, otherwise nginx may 502
docker image prune -f
```

`docker compose up -d --build` only rebuilds and restarts services whose code changed. Volumes (the databases) are untouched.

### Changes to CourseCatalog or DataNorge

These are separate repos included as submodules. Portfolio pins each one to an exact commit.

1. Merge the change in the app's own repo **with a merge commit** (not squash or rebase), so the exact commit lands on that repo's `main`.
2. In Portfolio, bump the submodule pointer to that commit:
   ```bash
   cd CourseCatalog && git fetch && git checkout <commit> && cd ..
   git add CourseCatalog && git commit
   ```
3. Merge that Portfolio change, then deploy as above.

If the Portfolio pointer refers to a commit that isn't on the app repo's `main` (for example after a squash merge and branch deletion), `git submodule update` fails on the server.

## Logs and status

```bash
docker compose ps                          # all 9 services should be Up
docker compose logs -f nginx               # follow one service
docker compose logs --tail 50 coursecatalog-api
docker compose logs feed | grep -i -e warning -e spotify
docker stats --no-stream                   # memory per container
free -h; df -h /
```

Quick health checks from anywhere:

```bash
curl -s https://didriksi.com/datanorge/api/health        # {"status":"ok","db":true}
curl -s https://didriksi.com/api/feed | head -c 200
curl -s https://didriksi.com/api/music | head -c 200     # "enabled":true when Spotify is configured
curl -s https://didriksi.com/coursecatalog/api/courses/ | head -c 200
```

## Database shells

```bash
docker compose exec coursecatalog-db psql -U postgres -d coursecatalog
docker compose exec datanorge-db psql -U datasenter -d datasenter
```

## Backups

Nightly dumps of both databases, kept for 7 days. Set up (or update) with the block below. It's safe to run again: it overwrites the script and replaces any existing cron line for it.

```bash
mkdir -p ~/backups
cat > ~/backup.sh <<'EOF'
#!/bin/sh
set -e
cd /home/deploy/Portfolio
d=$(date +%F)
docker compose exec -T coursecatalog-db pg_dump -U postgres --clean --if-exists coursecatalog | gzip > /home/deploy/backups/coursecatalog-$d.sql.gz
docker compose exec -T datanorge-db pg_dump -U datasenter --clean --if-exists datasenter | gzip > /home/deploy/backups/datanorge-$d.sql.gz
find /home/deploy/backups -name '*.sql.gz' -mtime +7 -delete
EOF
chmod +x ~/backup.sh
~/backup.sh && ls -lh ~/backups
(crontab -l 2>/dev/null | grep -v backup.sh; echo '15 3 * * * /home/deploy/backup.sh >> /home/deploy/backups/backup.log 2>&1') | crontab -
crontab -l
```

`--clean --if-exists` makes each dump drop and recreate its tables when restored, so a restore works on top of existing data.

The backups live on the same server. Copy them off now and then (**Mac**):

```bash
scp -r deploy@didriksi.com:backups ./didriksi-backups
```

### Restore

Stop the API that uses the database, restore, then start it again. Replace the date with the backup you want.

```bash
cd ~/Portfolio

# Course Catalog
docker compose stop coursecatalog-api
gunzip -c ~/backups/coursecatalog-2026-09-30.sql.gz | docker compose exec -T coursecatalog-db psql -U postgres -d coursecatalog
docker compose start coursecatalog-api

# DataNorge
docker compose stop datanorge-api
gunzip -c ~/backups/datanorge-2026-09-30.sql.gz | docker compose exec -T datanorge-db psql -U datasenter -d datasenter
docker compose start datanorge-api
```

The feed's SQLite database isn't backed up: it refills itself from GitHub, LeetCode and Letterboxd within minutes. Only manual status posts would be lost.

## HTTPS certificates

- **Issued** once with `certbot certonly --standalone` before nginx first started (see [DEPLOY.md step 7](../DEPLOY.md#7-https-certificate-before-the-first-start)).
- **Renewed** automatically by certbot's systemd timer, about 30 days before expiry. Renewal needs port 80, so two hook scripts stop and start the nginx container around it (a few seconds of downtime):
  - `/etc/letsencrypt/renewal-hooks/pre/stop-nginx.sh`
  - `/etc/letsencrypt/renewal-hooks/post/start-nginx.sh`
- **Check** with `sudo certbot certificates` (expiry date) and `sudo certbot renew --dry-run`. The "Hook ran with error output" lines in the dry run are only Docker progress messages.
- The hooks use the absolute path `/home/deploy/Portfolio/docker-compose.yml`. Update them if the repo ever moves.

## Data maintenance

**Course Catalog courses:** run the seed scripts (both skip courses that already exist):

```bash
docker compose exec coursecatalog-api python -m src.seed_server seed
docker compose exec coursecatalog-api python -m src.add_new_courses
```

Always pass `seed`. With no argument, `seed_server` runs `reset`, which **deletes every course first**.

**Course Catalog schema changes:** apply migrations with `docker compose exec coursecatalog-api alembic upgrade head`. If Alembic trips over objects that already exist, apply the change by hand in the DB shell and then `alembic stamp head`.

**DataNorge data:** every pipeline job is idempotent. To refresh SSB electricity figures or BRREG ownership details:

```bash
docker compose exec datanorge-api pipeline load-ssb-electricity
docker compose exec datanorge-api pipeline enrich-brreg --force
```

Never run `seed-research-sites`. Each seed job replaces the previous seed, so it would swap the 58 data centers for an older list of 20. To restore the 58, run `pipeline seed-top-sites`.

**Status posts on the live feed:**

```bash
FEED_API_KEY=$(grep FEED_API_KEY ~/Portfolio/.env | cut -d= -f2)
curl -X POST https://didriksi.com/api/status -H "X-API-Key: $FEED_API_KEY" \
     -H "Content-Type: application/json" -d '{"text": "Exam prep week"}'
```

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| 502 Bad Gateway after a rebuild | nginx cached old container addresses: `docker compose restart nginx` |
| nginx exits with "cannot load certificate" | No certificate on the host: `sudo ls /etc/letsencrypt/live/`, then DEPLOY.md step 7 |
| Renewal dry run fails with "Timeout during connect" | DNS doesn't point to this server, port 80 is blocked (`sudo ufw status`), or something besides nginx holds port 80 |
| A service keeps restarting | `docker compose logs --tail 50 <service>`. For an API, the usual cause is a DB password mismatch (see above) or a missing migration. |
| Course Catalog API returns 500 "column … does not exist" | Schema is behind the code: see "Course Catalog schema changes" above |
| Course Catalog list is empty | DB not seeded: run the seed commands above |
| DataNorge shows no sites | `curl -s https://didriksi.com/datanorge/api/health` must show `"db":true`, then re-run the DataNorge load from DEPLOY.md step 9 |
| Feed empty or stale | `docker compose logs feed \| grep -i warning`. A failing source backs off up to an hour; LeetCode may block server IPs. |
| Music window says "offline" | Spotify token revoked or wrong: re-run `feed/scripts/spotify_auth.py` on your Mac, update `SPOTIFY_REFRESH_TOKEN` in `.env`, then `docker compose up -d feed` |
| Build dies, or the server freezes during a build | Out of memory: `free -h`, check swap, build one service at a time (`docker compose build <service>`) |
| Disk filling up | `df -h /`, then `docker builder prune -f` and `docker image prune -f` |
| `git submodule update` fails with "not our ref" | The pinned commit isn't on the app repo's `main`: see "Changes to CourseCatalog or DataNorge" |
| `docker compose restart` seems to hang or prints a spinner | Normal: it finishes without printing "done". Check with `docker compose ps`. |
