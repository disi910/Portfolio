# Portfolio

Personal portfolio site, live at **https://didriksi.com**.

A Docker Compose monorepo with:

- a Windows 98-style landing page: about, a live activity feed (GitHub, LeetCode, status posts), a Winamp-style Spotify window, and project cards;
- **Course Catalog** at `/coursecatalog/` (git submodule, [disi910/CourseCatalog](https://github.com/disi910/CourseCatalog));
- **DataNorge** at `/datanorge/`, a register of Norway's data centers (git submodule, [disi910/DataNorge](https://github.com/disi910/DataNorge));
- the **Housing Market Classifier** write-up at `/housingclassifier/` (code in [disi910/HousingMarketClassifier](https://github.com/disi910/HousingMarketClassifier));
- a link to the **Usage Bar for Claude** Chrome extension ([disi910/claude-usage-bar](https://github.com/disi910/claude-usage-bar)).

## Documentation

| Document | For |
|---|---|
| [DEPLOY.md](DEPLOY.md) | Setting up a server from scratch (netcup VPS, Namecheap DNS, Docker, HTTPS, first data load) |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | How production works, deploying updates, logs, backups and restore, certificates, troubleshooting |
| [feed/README.md](feed/README.md) | The activity feed service: sources, endpoints, Spotify setup, local run, tests |
| [CLAUDE.md](CLAUDE.md) | Project status, conventions and pitfalls (for Claude Code sessions, and useful for humans too) |

## Architecture

All traffic enters through nginx on ports 80/443. HTTP redirects to HTTPS.

| Path | Service | What it is |
|---|---|---|
| `/` | `landing` | Static Win98 landing page |
| `/housingclassifier/` | `landing` | Static project page |
| `/api/` | `feed` | Activity feed + Spotify (FastAPI + SQLite), see [feed/](feed/) |
| `/coursecatalog/` | `coursecatalog-frontend` | React SPA |
| `/coursecatalog/api/` | `coursecatalog-api` → `coursecatalog-db` | FastAPI → PostgreSQL 16 |
| `/datanorge/` | `datanorge-web` | React + MapLibre (keeps its own design) |
| `/datanorge/api/` | `datanorge-api` → `datanorge-db` | FastAPI (GET only) → PostGIS |

Production runs on a netcup VPS (Debian 13), with Let's Encrypt certificates mounted from the host. Details in [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Repository layout

```
landing/                 static site (served by the `landing` container)
  index.html             landing page
  housingclassifier/     project page + plots
  assets/css/            win98.css (shared design system), home.css, project.css
  assets/js/             home.js (feed + music), taskbar.js (Start menu + clock)
  assets/icons/          pixel-art + brand SVG icons
  assets/demo/           sample data for ?demo mode
feed/                    activity feed service (FastAPI)
nginx/nginx.conf         reverse proxy, TLS, rate limits
docker-compose.yml       all 9 services
CourseCatalog/           submodule
DataNorge/               submodule
DEPLOY.md, docs/         deployment and operations docs
```

## Design system

All pages share `landing/assets/css/win98.css` (colour tokens, windows, buttons, taskbar, list views) and the icons in `landing/assets/icons/`. Pages add their own layout CSS (`home.css`, `project.css`) and include the same taskbar markup plus `assets/js/taskbar.js`. Course Catalog keeps a copy of the same tokens in its own repo, so it builds on its own. DataNorge deliberately keeps its own design.

## Local development

Preview the static site without any backend:

```bash
cd landing && python3 -m http.server 8765
# open http://localhost:8765/?demo   (?demo renders bundled sample feed and music data)
```

Preview with the real feed service: see [feed/README.md → Run locally](feed/README.md#run-locally).

Run everything as in production (needs Docker, a `.env` based on [.env.example](.env.example), and a certificate; see [DEPLOY.md](DEPLOY.md)):

```bash
git clone --recurse-submodules https://github.com/disi910/Portfolio.git
docker compose up -d --build
```

## Tests

```bash
cd feed && python -m pytest
```
