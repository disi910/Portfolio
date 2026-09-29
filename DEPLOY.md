# Deploying didriksi.com on a netcup VPS

A complete, from-scratch setup: netcup VPS (Ubuntu 24.04 or Debian 13; every command works on both) + Namecheap DNS + Docker Compose + Let's Encrypt.

This is the runbook that was used for the current production server (netcup VPS nano, **Debian 13 "trixie"**, user `deploy`, code in `/home/deploy/Portfolio`), first deployed on 2026-09-29. Use it again to rebuild the server from scratch or to move to a new host. For how the running system works and day-to-day tasks (updates, logs, backups, restore, troubleshooting), see [docs/OPERATIONS.md](docs/OPERATIONS.md).

Commands marked **Mac** run on your own computer. Everything else runs on the server.
Replace `SERVER_IP` with your VPS's IPv4 address everywhere.

---

## 0. Before you start

Have these ready:

- netcup Server Control Panel (SCP) login: https://www.servercontrolpanel.de
- Namecheap login
- An SSH key on your Mac. Check with `ls ~/.ssh/id_ed25519.pub`. If it doesn't exist, create one (**Mac**):
  ```bash
  ssh-keygen -t ed25519 -C "didriksi-vps"
  ```
- Optional: the values from your local `.env` for `GITHUB_TOKEN` and the `SPOTIFY_*` variables.

---

## 1. Install the OS on the VPS (netcup SCP)

1. Log in to the SCP and open your VPS nano.
2. Go to **Media → Images** and install **Ubuntu 24.04.5 UEFI amd64 (Minimal)** or **Debian 13**. Not Ubuntu 26.04 (untested here), and not the "cloudimg" or "openclaw" variants. If offered, choose one big partition, and paste your public key (`cat ~/.ssh/id_ed25519.pub` on your Mac) as the SSH key. Note the root password the installer shows or emails you. Check what you actually got with `cat /etc/os-release` after logging in: the production server ended up on Debian 13, and everything below works on it.
3. Copy the server's **IPv4 address** from the SCP (server overview or the network page).
4. Log in (**Mac**). The first line clears the old Hetzner host key, which would otherwise block the connection with a "REMOTE HOST IDENTIFICATION HAS CHANGED" error:
   ```bash
   ssh-keygen -R didriksi.com
   ssh-keygen -R SERVER_IP
   ssh root@SERVER_IP
   ```
5. Check the machine (on the server):
   ```bash
   uname -m      # must print x86_64 (the PostGIS image only exists for x86_64)
   free -h       # note total RAM
   df -h /       # note free disk space (you want at least 15 GB free)
   swapon --show # note whether swap already exists
   ```

---

## 2. Point didriksi.com at the VPS (Namecheap)

Do this now, so DNS has time to update while you set up the server.

1. Namecheap → **Domain List** → **Manage** next to `didriksi.com`.
2. **Domain** tab → **Nameservers**: must be **Namecheap BasicDNS**. If it says Custom DNS (for example Hetzner's nameservers), change it to Namecheap BasicDNS and save. This alone can take a while to update, so check it first.
3. **Advanced DNS** tab → **Host Records**:
   - **Delete:** the `CNAME Record` for `www` pointing to `parkingpage.namecheap.com`, any `URL Redirect Record` for `@`, and every existing `A` or `AAAA` record for `@` or `www` (the old Hetzner IP).
   - **Add:**

     | Type | Host | Value | TTL |
     |------|------|-------|-----|
     | A Record | `@` | `SERVER_IP` | Automatic |
     | A Record | `www` | `SERVER_IP` | Automatic |

   - **Do not add AAAA (IPv6) records.** Let's Encrypt prefers IPv6 when it exists, and the setup below only serves IPv4.
   - Leave any `MX` or `TXT` records alone (they are for email).
4. Verify (**Mac**). Both commands must print `SERVER_IP`, and the third must print nothing:
   ```bash
   dig +short didriksi.com @1.1.1.1
   dig +short www.didriksi.com @1.1.1.1
   dig +short AAAA didriksi.com @1.1.1.1
   ```
   This usually takes a few minutes, occasionally up to an hour. Don't request the certificate (step 7) until it's correct.

---

## 3. Base server setup (as root)

```bash
apt update && apt full-upgrade -y
apt install -y git curl ca-certificates dnsutils ufw unattended-upgrades nano openssl
timedatectl set-timezone Europe/Oslo
```

Create your own user (you'll be asked for a password; use a strong one, it's what `sudo` asks for):

```bash
adduser deploy
usermod -aG sudo deploy
```

Give `deploy` your SSH key (**Mac**):

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub deploy@SERVER_IP
```

Test it in a **new** terminal (**Mac**), and keep your root session open until this works:

```bash
ssh deploy@SERVER_IP
sudo -v   # enter deploy's password; no error = sudo works
```

From here on, work as `deploy`.

### Lock down SSH

The file name starts with `00-` on purpose: Ubuntu reads these files in order, and a cloud-init file (`50-cloud-init.conf`) can otherwise switch password login back on.

```bash
sudo tee /etc/ssh/sshd_config.d/00-hardening.conf > /dev/null <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sudo sshd -t && sudo systemctl restart ssh
```

Keep this session open and test from a **new** terminal (**Mac**): `ssh deploy@SERVER_IP` must still work, and `ssh root@SERVER_IP` must be refused.

### Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable       # answer y
sudo ufw status
```

Docker adds its own firewall rules for published ports and bypasses ufw. That's fine here, because only nginx publishes ports (80 and 443). The databases are never exposed.

### Automatic security updates

```bash
sudo dpkg-reconfigure -plow unattended-upgrades   # choose Yes
```

### Swap

Building the images needs more memory than a small VPS has. Skip this if `swapon --show` already listed 2 GB or more.

```bash
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h   # Swap should now show 4.0Gi
```

---

## 4. Install Docker

Docker's official repository (not the distro's `docker.io` package, which lacks the Compose plugin). These commands work on both Ubuntu and Debian: `/etc/os-release` supplies the distro (`$ID`, `ubuntu` or `debian`) and its release codename (for example `noble` or `trixie`).

```bash
. /etc/os-release && echo "$ID $VERSION_CODENAME"   # e.g. "ubuntu noble" or "debian trixie"
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID $VERSION_CODENAME stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
docker --version   # must print a version before you continue
```

Cap container log size, so logs can't fill the disk:

```bash
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

Let `deploy` use Docker without `sudo`, then **log out and back in** so the group applies:

```bash
sudo usermod -aG docker deploy
exit
```

(**Mac**) `ssh deploy@SERVER_IP`, then:

```bash
docker run --rm hello-world   # prints "Hello from Docker!"
docker compose version
```

---

## 5. Get the code

```bash
cd ~
git clone --recurse-submodules https://github.com/disi910/Portfolio.git
cd ~/Portfolio
git submodule status
```

Both `CourseCatalog` and `DataNorge` must be listed **without** a leading `-`. If one has a `-`, run `git submodule update --init --recursive`.

If `git clone` asks for a username or password, the repository is private. Create a fine-grained personal access token on GitHub with read-only **Contents** access to `Portfolio`, `CourseCatalog` and `DataNorge`, and use it as the password.

---

## 6. Create `.env`

This generates random secrets. Hex is used on purpose: the database password ends up inside a URL, where characters like `/` or `+` would break it.

```bash
cd ~/Portfolio
cat > .env <<EOF
DB_PASSWORD=$(openssl rand -hex 32)
SECRET_KEY=$(openssl rand -hex 32)
API_KEY=$(openssl rand -hex 32)
DATANORGE_DB_PASSWORD=$(openssl rand -hex 32)
FEED_API_KEY=$(openssl rand -hex 32)

GITHUB_USERNAME=disi910
GITHUB_TOKEN=
LEETCODE_USERNAME=LordQuas
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REFRESH_TOKEN=
EOF
chmod 600 .env
nano .env   # paste GITHUB_TOKEN and the three SPOTIFY_ values if you have them; Ctrl+O, Enter, Ctrl+X
```

Two rules:

- **Never change `DB_PASSWORD` or `DATANORGE_DB_PASSWORD` after the first start.** Postgres stores the password when its data volume is created, so changing it in `.env` later locks the API out.
- Keep a copy of `API_KEY` and `FEED_API_KEY` in your password manager. You need `FEED_API_KEY` to post status updates.

---

## 7. HTTPS certificate (before the first start)

nginx won't start without a certificate, so get it first while port 80 is still free. DNS from step 2 must already point here.

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone \
  -d didriksi.com -d www.didriksi.com \
  --email YOUR_EMAIL --agree-tos --no-eff-email
sudo ls /etc/letsencrypt/live/didriksi.com/   # must list fullchain.pem and privkey.pem
```

Certificates renew automatically (certbot installs a timer). Renewal also needs port 80, which nginx holds once the site is running, so add hooks that stop nginx for the few seconds it takes:

```bash
sudo mkdir -p /etc/letsencrypt/renewal-hooks/pre /etc/letsencrypt/renewal-hooks/post
sudo tee /etc/letsencrypt/renewal-hooks/pre/stop-nginx.sh > /dev/null <<'EOF'
#!/bin/sh
docker compose -f /home/deploy/Portfolio/docker-compose.yml stop nginx
EOF
sudo tee /etc/letsencrypt/renewal-hooks/post/start-nginx.sh > /dev/null <<'EOF'
#!/bin/sh
docker compose -f /home/deploy/Portfolio/docker-compose.yml start nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/pre/stop-nginx.sh /etc/letsencrypt/renewal-hooks/post/start-nginx.sh
```

You'll test renewal in step 10, once the site is running.

---

## 8. First start

```bash
cd ~/Portfolio
docker compose up -d --build
```

The first build takes a while on a small VPS (10-20 minutes is normal). When it finishes:

```bash
docker compose ps
```

All 9 services should be `Up` or `running`: `nginx`, `landing`, `feed`, `coursecatalog-frontend`, `coursecatalog-api`, `coursecatalog-db`, `datanorge-web`, `datanorge-api`, `datanorge-db` (which should also say `healthy`). Then:

```bash
docker compose restart nginx   # makes nginx pick up the final container addresses
```

The restart may print a spinner line like `Container portfolio-nginx-1 Restarting 0.6s` as the prompt returns. That's only progress output. Check the real state with `docker compose ps nginx` (it should say `Up …`, not `Restarting`) and `docker compose logs nginx --tail 15` (no `[emerg]` lines). The log line `can not modify /etc/nginx/conf.d/default.conf (read-only file system?)` is expected: the config is mounted read-only on purpose.

If a service keeps restarting, run `docker compose logs <service>` to see why.

---

## 9. Load the databases (one time)

Both databases start empty.

### Course Catalog

The tables are created automatically when the API starts. Load the courses. **Always pass `seed`**: running the script without an argument defaults to `reset`, which wipes the table first.

```bash
docker compose exec coursecatalog-api python -m src.seed_server seed
docker compose exec coursecatalog-api python -m src.add_new_courses
docker compose exec coursecatalog-api alembic stamp head
```

The last line records the schema version, so future migrations know where to start.

### DataNorge

Run these in exactly this order (each is safe to re-run):

```bash
docker compose exec datanorge-api alembic -c db/alembic.ini upgrade head
docker compose exec datanorge-api pipeline load-kommuner
docker compose exec datanorge-api pipeline load-ssb-electricity
docker compose exec datanorge-api pipeline load-nkom-operators
docker compose exec datanorge-api pipeline seed-top-sites
docker compose exec datanorge-api pipeline enrich-brreg
docker compose exec datanorge-api pipeline load-key-articles
```

**Do not run `seed-research-sites`.** Each seed job replaces the previous seed, so it would swap the 58 data centers for an older list of 20.

---

## 10. Verify

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://didriksi.com    # 301 https://didriksi.com/
curl -s -o /dev/null -w "%{http_code}\n" https://www.didriksi.com                # 200
curl -s -o /dev/null -w "%{http_code}\n" https://didriksi.com/                    # 200
curl -s -o /dev/null -w "%{http_code}\n" https://didriksi.com/housingclassifier/  # 200
curl -s -o /dev/null -w "%{http_code}\n" https://didriksi.com/coursecatalog/      # 200
curl -s https://didriksi.com/coursecatalog/api/courses/ | head -c 150; echo      # JSON with courses
curl -s -o /dev/null -w "%{http_code}\n" https://didriksi.com/datanorge/          # 200
curl -s https://didriksi.com/datanorge/api/health; echo                          # {"status":"ok","db":true}
curl -s https://didriksi.com/api/feed | head -c 150; echo                        # {"events":[...
curl -s https://didriksi.com/api/music; echo                                     # {"enabled":...
docker compose logs feed | head -5   # "enabled sources: github, leetcode; spotify: ..."
```

Test certificate renewal. This stops nginx for a few seconds and starts it again:

```bash
sudo certbot renew --dry-run   # must end with "Congratulations, all simulated renewals succeeded"
docker compose ps nginx        # must be running again
systemctl list-timers | grep certbot
```

certbot prints `Hook 'pre-hook' ran with error output:` followed by Docker's `Stopping`/`Started` lines. That's not an error: Docker writes progress messages to stderr, and certbot labels anything there as "error output".

Finally, open https://didriksi.com in a browser and click through every project.

---

## 11. Set up backups

Both databases live only on this server. Set up the nightly backup job described in [docs/OPERATIONS.md → Backups](docs/OPERATIONS.md#backups) now, and test it once.

After that, everything else (deploying updates, logs, restore, troubleshooting) is in [docs/OPERATIONS.md](docs/OPERATIONS.md).
