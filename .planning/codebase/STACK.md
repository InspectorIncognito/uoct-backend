# Technology Stack

**Analysis Date:** 2026-04-08

## Languages

**Primary:**
- Python 3.12 - Backend application code in `backend/**/*.py`, Django project files in `backend/backend/*.py`.

**Secondary:**
- Bash - Container entrypoints and orchestration in `docker/entrypoint.sh` and `docker/nginx/nginx_entrypoint.sh`.
- YAML - Compose and CI files in `docker/docker-compose.yml`, `docker/docker-compose-dev.yml`, and `.github/workflows/test_task.yml`.

## Runtime

**Environment:**
- Python 3.12 on Alpine Linux in `docker/Dockerfile`.
- Node 20 Alpine for the frontend build stage in `docker/nginx/NginxDockerfile`.

**Package Manager:**
- pip - Python dependencies from `requirements-prod.txt` and `requirements-dev.txt`.
- npm - Frontend build in `docker/nginx/NginxDockerfile`.
- Lockfile: present for the OpenCode workspace (`.opencode/bun.lock`); not used by the backend runtime.

## Frameworks

**Core:**
- Django 4.1.1 - Main backend framework, configured in `backend/backend/settings.py` and started via `backend/manage.py`.
- Django REST Framework 3.13.1 - API layer in `backend/rest_api/views.py`, `backend/user/views.py`, and `backend/backend/urls.py`.
- drf-spectacular 0.24.2 - OpenAPI schema and Swagger UI in `backend/backend/urls.py`.

**Testing:**
- Django test runner - Invoked through `docker/entrypoint.sh` and `Makefile`.
- coverage>=7.3.0 - Available in `requirements-dev.txt`.
- factory_boy 3.3.0 - Available in `requirements-dev.txt`.

**Build/Dev:**
- gunicorn>=21.2.0 - Production app server in `docker/entrypoint.sh`.
- django-rq 2.7.0 / rq 1.12.0 / rq_scheduler 0.13.0 - Background jobs and scheduled tasks in `backend/backend/settings.py` and `backend/backend/urls.py`.
- nginx - Production/static frontend serving via `docker/nginx/NginxDockerfile`.

## Key Dependencies

**Critical:**
- psycopg2-binary>=2.9.5 - PostgreSQL connectivity in `backend/backend/settings.py`.
- redis backend via Django cache and RQ - Cache/queue configuration in `backend/backend/settings.py`.
- requests - External HTTP calls in `backend/gtfs_rt/utils.py`, `backend/processors/osm/query.py`, and `backend/velocity/gtfs.py`.
- pandas / geopandas / shapely / networkx / scipy / geojson - Geospatial and data processing across `backend/rest_api/models.py`, `backend/processors/osm/process.py`, and `backend/velocity/*.py`.

**Infrastructure:**
- jinja2 - Template rendering for Overpass queries in `backend/processors/osm/query.py`.
- beautifulsoup4 - Scraping GTFS download links in `backend/gtfs_rt/utils.py`.
- gtfs-realtime-bindings==1.0.0 - Parsing GTFS-RT protobuf in `backend/gtfs_rt/processors/manager.py`.
- overpass - OSM client in `backend/processors/osm/query.py`.
- haversine, networkx, typer - Utility and processing support in backend modules.

## Configuration

**Environment:**
- Configuration is environment-driven through `python-decouple` (`decouple.config`) in `backend/backend/settings.py`, `backend/config/environment.py`, `backend/gtfs_rt/config.py`, and `backend/velocity/gtfs.py`.
- Required values include `DEBUG`, `ALLOWED_HOSTS`, `DB_NAME`, `DB_USER`, `DB_PASS`, `DB_HOST`, `DB_PORT`, `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `CORS_ALLOWED_ORIGINS`, `GTFS_URL`, `DTPM_GTFS_URL`, `PROTO_URL`, `ALERT_AUTHOR`, `TRANSAPP_HOST`, `TRANSAPP_SITE_USERNAME`, `TRANSAPP_SITE_PASSWORD`, `HMM_NUM_WORKERS`, and related queue settings.
- `.env` files are present in `backend/.env` and `.env.frontend`; contents are not inspected.

**Build:**
- Docker build definitions in `docker/Dockerfile` and `docker/nginx/NginxDockerfile`.
- Compose orchestration in `docker/docker-compose.yml` and `docker/docker-compose-dev.yml`.
- CI pipeline in `.github/workflows/test_task.yml`.

## Platform Requirements

**Development:**
- Python 3.12, Docker, Docker Compose, PostgreSQL, and Redis are required for the full stack defined in `Makefile` and `docker/docker-compose-dev.yml`.

**Production:**
- Containerized deployment with Gunicorn + Django backend, Nginx frontend/static proxy, PostgreSQL, and Redis.

---

*Stack analysis: 2026-04-08*
