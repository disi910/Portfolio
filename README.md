# Portfolio

Personal portfolio site at **didriksi.com** — a Docker Compose monorepo with a retro landing page, CourseCatalog app, and HousingMarketClassifier.

## Deployment (VPS)

### Prerequisites
- Docker and Docker Compose installed on the VPS
- SSL certificates from Let's Encrypt at `/etc/letsencrypt/`
- A `.env` file in the project root with production secrets:
  ```
  DB_PASSWORD=<postgres password>
  SECRET_KEY=<api secret key>
  API_KEY=<api key>
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

HTTP is redirected to HTTPS. SSL certs are mounted from the host's `/etc/letsencrypt/`.

## TODO

- [ ] Fix ifi logo not displaying
- [ ] Implement small search bar in Emnekart
- [ ] Give the dependency nodes that are blue a blue outline on the left and top (like the turquoise nodes)
- [ ] Change so that it says the actual total forkunnskaper in Emnekart
- [ ] Add course link to information card and make prereqs clickable to go to their information card
- [ ] Add "Anbefalte forkunnskaper" as well from course sites
- [ ] Implement grade chart for courses by scraping karakterweb.no API
- [x] Add homepage navigation like HousingMarketClassifier has
