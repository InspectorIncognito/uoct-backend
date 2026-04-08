# External Integrations

**Analysis Date:** 2026-04-08

## APIs & External Services

**Public transport / GTFS:**
- DTPM GTFS feed - Current GTFS source scraped and downloaded in `backend/gtfs_rt/utils.py`.
  - SDK/Client: `requests`, `beautifulsoup4`
  - Auth: `DTPM_GTFS_URL`
- GTFS-RT protobuf feed - Real-time vehicle data consumed in `backend/gtfs_rt/processors/manager.py`.
  - SDK/Client: `google.transit.gtfs_realtime_pb2`
  - Auth: `PROTO_URL`

**Mapping / GIS:**
- OpenStreetMap Nominatim - Relation lookup in `backend/processors/osm/query.py`.
  - SDK/Client: `requests`
  - Auth: custom `User-Agent` string in `OSMDownloader`
- OpenStreetMap Overpass API - Road geometry queries in `backend/processors/osm/query.py` and `backend/processors/osm/process.py`.
  - SDK/Client: `overpass`, `jinja2`
  - Auth: none detected

**Admin / legacy system integration:**
- TranSapp admin site - Alerts are created, updated, and deleted by scraping form endpoints in `backend/rest_api/util/alert.py`.
  - SDK/Client: `requests.Session`
  - Auth: `TRANSAPP_HOST`, `TRANSAPP_SITE_USERNAME`, `TRANSAPP_SITE_PASSWORD`, `ALERT_AUTHOR`

**Frontend build-time integration:**
- GitHub-hosted frontend repository - Cloned during image build in `docker/nginx/NginxDockerfile`.
  - SDK/Client: `git`
  - Auth: `GITHUB_TOKEN`
- Mapbox / frontend form configuration - Build arguments passed into the frontend image in `docker/docker-compose.yml` and `docker/docker-compose-dev.yml`.
  - Auth: `VITE_MAPBOX_TOKEN`, `VITE_FORM_URL`, `VUE_APP_BASE_URL`

## Data Storage

**Databases:**
- PostgreSQL - Primary relational database configured in `backend/backend/settings.py` and provisioned in `docker/docker-compose.yml`.
  - Connection: `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`
  - Client: Django ORM + `psycopg2-binary`

**File Storage:**
- Local filesystem and Docker volumes - Media/static paths use `backend/files` and `backend/static` in `backend/backend/settings.py` and `docker/docker-compose.yml`.

**Caching:**
- Redis - Cache backend and RQ queue store in `backend/backend/settings.py` and `docker/docker-compose.yml`.

## Authentication & Identity

**Auth Provider:**
- Custom Django authentication - `backend/backend/backend.py` extends `ModelBackend` and `backend/user/views.py` issues DRF tokens.
  - Implementation: session auth + token auth in `backend/backend/settings.py`
- CSRF/cookie handling is relaxed only in development for API endpoints in `backend/backend/settings.py`.

## Monitoring & Observability

**Error Tracking:**
- Not detected.

**Logs:**
- Standard output logging/printing in `docker/entrypoint.sh`, `backend/gtfs_rt/utils.py`, `backend/rest_api/util/alert.py`, and `backend/gtfs_rt/processors/manager.py`.

## CI/CD & Deployment

**Hosting:**
- Containerized deployment with Docker, Gunicorn, and Nginx (`docker/Dockerfile`, `docker/nginx/NginxDockerfile`).

**CI Pipeline:**
- GitHub Actions test workflow in `.github/workflows/test_task.yml`.

## Environment Configuration

**Required env vars:**
- `DEBUG`, `ALLOWED_HOSTS`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `CORS_ALLOWED_ORIGINS`, `GTFS_URL`, `DTPM_GTFS_URL`, `PROTO_URL`, `ALERT_AUTHOR`, `TRANSAPP_HOST`, `TRANSAPP_SITE_USERNAME`, `TRANSAPP_SITE_PASSWORD`, `GITHUB_TOKEN`, `VUE_APP_BASE_URL`, `VITE_MAPBOX_TOKEN`, `VITE_FORM_URL`, `HMM_NUM_WORKERS`.

**Secrets location:**
- Environment files are present in `backend/.env` and `.env.frontend`; the deployment also references `docker/docker_env` and `docker/docker_db_env`.

## Webhooks & Callbacks

**Incoming:**
- None detected.

**Outgoing:**
- HTTP GET/POST calls to DTPM, Nominatim, Overpass, TranSapp admin, and GTFS-RT sources in `backend/gtfs_rt/utils.py`, `backend/processors/osm/query.py`, `backend/rest_api/util/alert.py`, and `backend/gtfs_rt/processors/manager.py`.

---

*Integration audit: 2026-04-08*
