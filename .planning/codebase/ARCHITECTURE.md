# Architecture

**Analysis Date:** 2026-04-08

## Pattern Overview

**Overall:** Django monolith with domain-oriented apps, REST API layers, and batch/worker processing.

**Key Characteristics:**
- Request handling is centered in `backend/backend/urls.py` and app-level routers like `backend/rest_api/urls.py` and `backend/gtfs_rt/routers.py`.
- Core business logic is split between Django apps (`backend/rest_api/`, `backend/gtfs_rt/`, `backend/gps/`, `backend/user/`) and computation modules (`backend/velocity/`, `backend/processors/`).
- Background and maintenance work is executed through management commands and shared utility modules, especially `backend/rest_api/util/` and `backend/gtfs_rt/utils.py`.

## Layers

**Project configuration layer:**
- Purpose: Django startup, settings, URL routing, ASGI entry.
- Location: `backend/backend/`
- Contains: `settings.py`, `urls.py`, `asgi.py`, `wsgi.py`, custom auth backend in `backend.py`.
- Depends on: Django, DRF, `decouple`, app packages.
- Used by: all app code and deployment containers.

**API layer:**
- Purpose: Expose domain data as REST endpoints and custom actions.
- Location: `backend/rest_api/`, `backend/gtfs_rt/`, `backend/gps/`, `backend/user/`
- Contains: viewsets, serializers, routers, permissions, API utilities.
- Depends on: Django ORM models, `rest_framework`, `geojson`, `pandas`, `geopandas`, worker helpers.
- Used by: external clients, browser UI, admin workflows.

**Domain model layer:**
- Purpose: Persist shapes, segments, speeds, alerts, GTFS data, GPS pulses, users.
- Location: `backend/rest_api/models.py`, `backend/gtfs_rt/models.py`, `backend/gps/models.py`, `backend/user/models.py`
- Contains: Django models and model methods.
- Depends on: Django ORM, geometry helpers, GTFS time helpers.
- Used by: serializers, views, processors, management commands.

**Processing layer:**
- Purpose: Transform GTFS, OSM, GPS, and shape data into segments, routes, and speeds.
- Location: `backend/processors/`, `backend/velocity/`, `backend/rest_api/util/`, `backend/gtfs_rt/processors/`
- Contains: segmentation logic, HMM map matching, route assignment, speed calculation, GTFS imports.
- Depends on: GeoPandas, Shapely, NetworkX, pandas, NumPy, requests, Django ORM.
- Used by: `backend/rest_api/util/process.py`, management commands, runtime API endpoints.

**Infrastructure layer:**
- Purpose: Containerization, runtime config, environment-dependent paths.
- Location: `docker/`, `backend/config/`
- Contains: Dockerfiles, compose manifests, path/environment helpers.
- Depends on: environment variables, filesystem layout.
- Used by: local development, tests, production deployment.

## Data Flow

**Map initialization flow:**
1. `README.md` directs setup to `python manage.py initialize_map_data` in `backend/rest_api/management/commands/initialize_map_data.py`.
2. Shape and axis data are downloaded or loaded from fixture sources in `backend/processors/osm/process.py` and `backend/processors/util/shapes.py`.
3. Segments, services, stops, thresholds, and GTFS mappings are persisted through `backend/rest_api/models.py` and helper modules in `backend/rest_api/util/`.

**GTFS update flow:**
1. `backend/gtfs_rt/utils.py` resolves the active GTFS URL and downloads the ZIP.
2. `backend/velocity/gtfs.py` reads `shapes.txt`, `trips.txt`, `routes.txt`, and `stops.txt` from the archive.
3. Processed GTFS shapes are saved into `backend/rest_api/models.py` and later used by segment assignment helpers in `backend/rest_api/util/services.py` and `backend/rest_api/util/stops.py`.

**GPS-to-speed flow:**
1. Incoming GPS pulses are stored in `backend/gtfs_rt/models.py` and exposed by `backend/gtfs_rt/views.py`.
2. `backend/velocity/grid.py` and `backend/velocity/vehicle.py` group pulses by vehicle and expedition.
3. `backend/velocity/expedition.py` and `backend/velocity/segment.py` compute distances, temporal windows, and speed records.
4. `backend/processors/speed/avg_speed.py` aggregates monthly historic speeds into `HistoricSpeed` rows.

**State Management:**
- Persistent state lives in Django models; transient state lives in in-memory managers like `GridManager`, `ShapeManager`, and `VehicleManager`.
- Batch jobs rely on database cleanup helpers such as `flush_shape_objects()` in `backend/rest_api/util/shape.py` and `flush_gps_pulses()` in `backend/gtfs_rt/utils.py`.
- Query-driven response shaping is common in viewsets, with filters based on request query params in `backend/rest_api/views.py` and `backend/gtfs_rt/views.py`.

## Key Abstractions

**Shape / Segment:**
- Purpose: Represent road axes and their 500m subdivisions.
- Examples: `backend/rest_api/models.py`, `backend/processors/osm/process.py`, `backend/rest_api/util/shape.py`
- Pattern: `Shape` owns ordered `Segment` rows; `ShapeManager` groups shapes by axis name and precomputes caches.

**Speed / HistoricSpeed / Alert:**
- Purpose: Store computed travel speeds, monthly benchmarks, and alert events.
- Examples: `backend/rest_api/models.py`, `backend/rest_api/views.py`, `backend/processors/speed/avg_speed.py`
- Pattern: speeds are calculated from GPS pulses, then enriched with historic reference values and alert thresholds.

**GTFSShape / Services / Stop:**
- Purpose: Connect GTFS route metadata to mapped road segments.
- Examples: `backend/velocity/gtfs.py`, `backend/rest_api/util/services.py`, `backend/rest_api/util/stops.py`
- Pattern: GTFS shapes are merged, matched, and persisted before route/service lists are attached to segments.

**GridManager / ExpeditionData / VehicleManager:**
- Purpose: Organize GPS pulses into vehicles, expeditions, and map-matching workloads.
- Examples: `backend/velocity/grid.py`, `backend/velocity/expedition.py`, `backend/velocity/vehicle.py`
- Pattern: the grid and expedition objects hold transient processing state and produce serializable outputs for API/debug use.

**ShapeManager:**
- Purpose: Provide axis-level access to shapes, segment GeoDataFrames, and HMM caches.
- Examples: `backend/rest_api/util/shape.py`, `backend/velocity/grid.py`, `backend/velocity/gtfs.py`
- Pattern: caches are built once per run and reused by matching and response generation code.

## Entry Points

**Django runtime:**
- Location: `backend/manage.py`, `backend/backend/asgi.py`, `backend/backend/urls.py`
- Triggers: container startup, local dev, production web server.
- Responsibilities: initialize settings, expose URL routing, attach app endpoints.

**API routing:**
- Location: `backend/backend/urls.py`, `backend/rest_api/urls.py`, `backend/gtfs_rt/routers.py`, `backend/gps/urls.py`
- Triggers: HTTP requests.
- Responsibilities: map endpoints to viewsets and custom actions.

**Admin/utility commands:**
- Location: `backend/rest_api/management/commands/`, `backend/gtfs_rt/management/commands/`, `backend/velocity/management/commands/`
- Triggers: `python manage.py <command>` and scheduled jobs.
- Responsibilities: initialize map data, update GTFS data, calculate speeds, assign routes/stops, and clean tables.

**Docker entrypoint:**
- Location: `docker/entrypoint.sh`, `docker/Dockerfile`, `docker/docker-compose.yml`, `docker/docker-compose-dev.yml`
- Triggers: container startup under dev/prod/test profiles.
- Responsibilities: install dependencies, mount project code, run web/worker/db/cache services.

## Error Handling

**Strategy:** Prefer defensive checks with explicit exceptions in processing modules and framework-managed HTTP errors in views.

**Patterns:**
- Input validation is performed early in serializers such as `backend/rest_api/serializers.py` and `backend/user/serializers.py`.
- Data-processing code uses `try/except` around I/O and matching routines in `backend/gtfs_rt/utils.py`, `backend/rest_api/util/services.py`, and `backend/velocity/grid.py`.
- Viewsets often return `JsonResponse` directly for custom payloads in `backend/rest_api/views.py` and `backend/user/views.py`.

## Cross-Cutting Concerns

**Logging:** Minimal; mostly `print()` statements in batch/process code and standard logging setup only where needed, such as `backend/velocity/segment.py`.
**Validation:** Serializer validation in `backend/rest_api/serializers.py` and `backend/user/serializers.py`; model/query guards in `backend/rest_api/views.py`.
**Authentication:** Token-based authentication via `backend/user/views.py`, Django auth backend in `backend/backend/backend.py`, and DRF auth settings in `backend/backend/settings.py`.

---

*Architecture analysis: 2026-04-08*
