# Codebase Structure

**Analysis Date:** 2026-04-08

## Directory Layout

```text
uoct-backend/
├── backend/          # Django project root and app packages
├── docker/           # Container builds and compose manifests
├── docs/             # Project documentation
├── Makefile          # Common dev/test/deploy commands
├── README.md         # Setup and operational notes
└── requirements-*.txt # Python dependency manifests
```

## Directory Purposes

**`backend/`:**
- Purpose: Main application source tree.
- Contains: Django project config, app packages, processing modules, fixtures, static/media roots, tests.
- Key files: `backend/backend/settings.py`, `backend/backend/urls.py`, `backend/manage.py`.

**`backend/backend/`:**
- Purpose: Django project configuration package.
- Contains: settings, root URL config, ASGI/WSGI entry points, custom auth backend.
- Key files: `backend/backend/settings.py`, `backend/backend/urls.py`, `backend/backend/backend.py`, `backend/backend/asgi.py`, `backend/backend/wsgi.py`.

**`backend/rest_api/`:**
- Purpose: Main REST surface for map, speed, alerts, shapes, services, and operational commands.
- Contains: models, serializers, viewsets, routers, utilities, management commands, tests.
- Key files: `backend/rest_api/models.py`, `backend/rest_api/views.py`, `backend/rest_api/serializers.py`, `backend/rest_api/urls.py`, `backend/rest_api/util/shape.py`, `backend/rest_api/util/services.py`.

**`backend/gtfs_rt/`:**
- Purpose: Real-time GTFS pulse ingestion and processing.
- Contains: GPS pulse model, API viewset, utilities, processors, schedulers, tests, management commands.
- Key files: `backend/gtfs_rt/models.py`, `backend/gtfs_rt/views.py`, `backend/gtfs_rt/utils.py`, `backend/gtfs_rt/routers.py`.

**`backend/gps/`:**
- Purpose: Legacy/auxiliary GPS endpoint package.
- Contains: GPS model, serializer, viewset, and URL wiring.
- Key files: `backend/gps/views.py`, `backend/gps/urls.py`, `backend/gps/models.py`.

**`backend/user/`:**
- Purpose: Authentication and user management.
- Contains: custom user model, admin, serializers, login/verify endpoints, tests.
- Key files: `backend/user/models.py`, `backend/user/views.py`, `backend/user/serializers.py`.

**`backend/processors/`:**
- Purpose: Data preparation and geospatial processing helpers.
- Contains: OSM ingestion, geometry helpers, speed aggregation, shape utilities, tests.
- Key files: `backend/processors/osm/process.py`, `backend/processors/speed/avg_speed.py`, `backend/processors/geometry/*.py`.

**`backend/velocity/`:**
- Purpose: Map matching, segmenting, expedition grouping, GTFS ingestion, speed computation.
- Contains: grid manager, vehicle manager, expedition model, segment criteria, GTFS reader, low-level GPS helpers.
- Key files: `backend/velocity/grid.py`, `backend/velocity/vehicle.py`, `backend/velocity/expedition.py`, `backend/velocity/segment.py`, `backend/velocity/gtfs.py`.

**`backend/config/`:**
- Purpose: Shared runtime path and environment helpers.
- Contains: path constants and environment variables.
- Key files: `backend/config/paths.py`, `backend/config/environment.py`.

**`backend/fixtures/`:**
- Purpose: Seed and fallback data.
- Contains: GeoJSON and CSV fixtures.
- Key files: `backend/fixtures/shapes_fixture.geojson`, `backend/fixtures/processed_cameras.csv`.

**`backend/debug/`:**
- Purpose: Generated GeoJSON debug artifacts.
- Contains: segmented shape outputs used for inspection.
- Key files: `backend/debug/*.geojson`.

**`docker/`:**
- Purpose: Build/runtime definitions for local and containerized execution.
- Contains: Dockerfiles, compose manifests, entrypoint, env files, nginx build assets.
- Key files: `docker/Dockerfile`, `docker/docker-compose.yml`, `docker/docker-compose-dev.yml`, `docker/entrypoint.sh`.

**`docs/`:**
- Purpose: Human-facing documentation assets.
- Contains: markdown docs and placeholders.
- Key files: `docs/APIDOCS.md`.

## Key File Locations

**Entry Points:**
- `backend/manage.py`: Django CLI entry point.
- `backend/backend/urls.py`: project URL dispatcher.
- `backend/backend/asgi.py`: ASGI application entry.
- `backend/rest_api/management/commands/initialize_map_data.py`: map bootstrap command.
- `backend/gtfs_rt/management/commands/calculate_speed.py`: speed batch command.

**Configuration:**
- `backend/backend/settings.py`: installed apps, database, cache, DRF, auth, static/media.
- `docker/docker-compose.yml`: production/test service topology.
- `docker/docker-compose-dev.yml`: development overrides.
- `docker/Dockerfile`: multi-stage Python image build.
- `Makefile`: convenience commands for build/test/up/down/migrate.

**Core Logic:**
- `backend/rest_api/models.py`: domain persistence and GeoJSON helpers.
- `backend/rest_api/views.py`: primary API endpoints and CSV/GeoJSON streaming.
- `backend/velocity/grid.py`: GPS filtering, HMM orchestration, grid handling.
- `backend/velocity/expedition.py`: expedition grouping and speed calculation.
- `backend/processors/osm/process.py`: OSM shape processing and segmentation.

**Testing:**
- `backend/rest_api/tests/`: REST API tests.
- `backend/gtfs_rt/tests/`: GTFS-RT tests.
- `backend/velocity/tests/`: velocity/map-matching tests.
- `backend/processors/tests/`: processing tests.
- `backend/user/tests/`: authentication tests.

## Naming Conventions

**Files:**
- Python modules use snake_case, e.g. `backend/rest_api/util/shape.py`, `backend/velocity/expedition.py`.
- Django management commands use descriptive action names, e.g. `backend/gtfs_rt/management/commands/get_last_month_avg_speed.py`.

**Directories:**
- App directories are lowercase singular nouns or domain names, e.g. `backend/user/`, `backend/gps/`, `backend/gtfs_rt/`.
- Utility subpackages group by concern, e.g. `backend/rest_api/util/hmm/`, `backend/processors/geometry/`.

## Where to Add New Code

**New Feature:**
- Primary code: add domain views/serializers/models under `backend/rest_api/` or the owning app package.
- Tests: add matching tests under the app’s `tests/` directory, e.g. `backend/rest_api/tests/`.

**New Component/Module:**
- Implementation: place reusable processing logic in `backend/velocity/` for map matching/speeds or `backend/processors/` for ingestion/transforms.

**Utilities:**
- Shared helpers: `backend/rest_api/util/` for API-adjacent helpers; `backend/config/` for environment/path constants.

## Special Directories

**`backend/static/` and `backend/files/`:**
- Purpose: Django static and media roots.
- Generated: Yes.
- Committed: Only placeholders (`.gitkeep`) are committed.

**`backend/debug/`:**
- Purpose: inspection outputs for segmented shapes and derived GeoJSON.
- Generated: Yes.
- Committed: Data files are present in the repository snapshot.

**`backend/logs/`:**
- Purpose: runtime logs.
- Generated: Yes.
- Committed: No; guarded by `backend/logs/.gitignore`.

---

*Structure analysis: 2026-04-08*
