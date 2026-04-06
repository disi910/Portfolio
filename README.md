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
docker compose up --build -d
```

### Useful commands
```bash
docker compose logs -f              # Follow all logs
docker compose logs -f nginx        # Follow specific service
docker compose down                 # Stop all services
docker compose ps                   # Check running containers
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
