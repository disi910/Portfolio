# Feed service: polls GitHub / LeetCode / Letterboxd into SQLite and proxies Spotify.
# Internal only - main nginx proxies /api/ traffic here.
FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

# SQLite database lives on a named volume (see docker-compose.yml)
ENV FEED_DB_PATH=/data/feed.db
RUN mkdir -p /data && useradd --system --uid 10001 feed && chown feed /data
USER feed

EXPOSE 8000
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
