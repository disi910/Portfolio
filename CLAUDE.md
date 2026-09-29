# CLAUDE.md

Guidance for Claude Code sessions in this repo. Read this first; the details are in the linked docs.

## What this is

Didrik Sivertsen's personal portfolio, **live at https://didriksi.com**. A Docker Compose monorepo: a Windows 98-style static landing page, an activity-feed API, and two apps included as git submodules (CourseCatalog, DataNorge). See [README.md](README.md) for the architecture table and repo layout.

## Current status (last updated 2026-09-29)

- **Production:** netcup VPS nano, **Debian 13**, deployed 2026-09-29 by following [DEPLOY.md](DEPLOY.md). All 9 containers run, HTTPS works, and a certificate-renewal dry run passed. The previous Hetzner server is cancelled.
- **Data:** Course Catalog seeded (`seed_server seed` + `add_new_courses`, `alembic stamp head`). DataNorge fully loaded (58 data centers). The feed shows GitHub, LeetCode and Letterboxd, and Spotify is configured.
- **Backups:** the nightly `~/backup.sh` cron is documented in [docs/OPERATIONS.md](docs/OPERATIONS.md#backups). Confirm it's installed on the server with `crontab -l`; if it's an older version without `--clean --if-exists`, re-run the setup block.
- **Merged work:**
  - Portfolio PR #5 and #6: Win98 redesign, feed service, project cards, Housing Classifier rewrite, DataNorge hosting.
  - CourseCatalog PR #14 and #15: Win98 restyle, taskbar.
  - DataNorge PR #4: sub-path production build.
- **Open items (not done, ask before doing):**
  - DataNorge's own UI still contains about 22 em dashes. Left alone, because DataNorge keeps its own design.
  - `icon128.png` in the claude-usage-bar repo is the old icon; the new one is `landing/assets/usage-bar-icon.png`.
  - There's no `robots.txt`; crawlers get a 404.

## Where things are

| Need | Look at |
|---|---|
| Server setup from scratch | [DEPLOY.md](DEPLOY.md) |
| Deploy an update, logs, backups/restore, certs, troubleshooting | [docs/OPERATIONS.md](docs/OPERATIONS.md) |
| Feed service (sources, endpoints, Spotify, local run) | [feed/README.md](feed/README.md) |
| Routing | `nginx/nginx.conf` |
| Services, volumes, env vars | `docker-compose.yml`, `.env.example` |
| Design system | `landing/assets/css/win98.css` (+ `home.css`, `project.css`) |

## Conventions

- **No em dashes anywhere on the website** (the user's rule). Use a colon, a comma or a full stop. Check with `grep -rn -e '—' -e '&mdash;' landing/`. This covers HTML, JS strings, CSS comments and demo data. For plot images, crop the title instead of shipping an em dash.
- **Win98 look** for the landing page, project pages and Course Catalog. Reuse the `win98.css` components (`.window`, `.title-bar`, `.btn`, `.taskbar`, `.list-view`, `.tag`) rather than adding new styles. **DataNorge keeps its own design**; don't restyle it.
- **The same taskbar/Start menu appears in three places:** `landing/index.html`, `landing/housingclassifier/index.html`, and `CourseCatalog/apps/web/ififag/src/components/Taskbar.tsx`. When adding a project or changing a link, update all three.
- **Project cards** (`landing/index.html`): the stretched title link covers the card, the GitHub icon sits top-right, an external link gets a ↗ arrow, and tools are shown as `.tool-tags`.
- **Content comes from the source.** Project descriptions must match each repo's README. The Housing Classifier page reflects the README's honest result: the model does not beat a seasonal baseline, and the old 86.5% figure is retracted.
- Feed code: no new dependencies without need. Keep `feed/tests` passing (`cd feed && python -m pytest`).
- The user wants direct, honest feedback, including disagreement where warranted.

## Pitfalls (each of these has bitten before)

- **Submodules:**
  - Merge CourseCatalog/DataNorge changes **with a merge commit**, *before* the Portfolio change that bumps the pointer.
  - A squash merge leaves Portfolio pointing at a commit that isn't on `main`.
  - Verify with `git merge-base --is-ancestor <sha> origin/main` in the submodule repo.
- **nginx needs the certificate to exist** before it can start (`/etc/letsencrypt/live/didriksi.com/`). Renewal works through the pre/post hooks in `/etc/letsencrypt/renewal-hooks/`, which stop and start the nginx container.
- **After any rebuild, run `docker compose restart nginx`,** otherwise you may get 502s.
- **Course Catalog seeding:** `python -m src.seed_server` with **no argument runs `reset` and wipes all courses.** Always pass `seed`.
- **DataNorge seeding:** never run `pipeline seed-research-sites`. Each seed job replaces the previous seed, so it would swap the 58 sites for 20 older ones.
- **DataNorge web build:** `VITE_BASE_PATH=/datanorge/` and `VITE_API_BASE_URL=/datanorge/api` are build args in `docker-compose.yml`. Its `tsconfig.json` needs `noEmit`; otherwise `tsc -b` writes `.js` files into `src/`, which Vite then picks up ahead of the `.tsx` files.
- **DB passwords** in `.env` can't be changed after the volumes exist.
- **Secrets are hex** (`openssl rand -hex 32`), because `DB_PASSWORD` is embedded in a URL.
- `postgis/postgis` is amd64-only.
- **Local runs on the user's Mac:** conda's `(base)` shadows virtualenv binaries, so always use `python -m uvicorn` / `python -m pytest`.
- **GitHub's Events API trims PushEvent payloads.** `app/sources/github.py` handles missing commit lists and looks up the head commit message.

## Verifying changes

- **Static site:** `cd landing && python3 -m http.server 8765`, open `/?demo`, and check at 1280 px and 375 px with no horizontal overflow (Playwright + Chromium are available in cloud sessions).
- **Feed:** `cd feed && python -m pytest`.
- **Compose and nginx:** `DB_PASSWORD=x SECRET_KEY=y DATANORGE_DB_PASSWORD=z API_KEY= docker compose config -q`. For `nginx -t`, rewrite the upstream hostnames and cert paths to local values first.
- **CourseCatalog:** `npm run lint && npm run build` in `apps/web/ififag`.
- **DataNorge web:** `npm run typecheck && VITE_BASE_PATH=/datanorge/ npm run build` in `apps/web`.
