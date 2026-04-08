# Codebase Concerns

**Analysis Date:** 2026-04-08

## Tech Debt

**Hard-coded and environment-sensitive configuration:**
- Issue: `backend/backend/settings.py` mixes required runtime values from `decouple.config(...)` with a hard-coded `SECRET_KEY`, making secret rotation and environment parity harder.
- Files: `backend/backend/settings.py`, `backend/manage.py`, `backend/.env`
- Impact: deployment drift, accidental secret leakage, and fragile local/production parity.
- Fix approach: move all secrets and host configuration to environment variables and fail fast with explicit defaults/validation.

**Print-driven operational logging:**
- Issue: several runtime paths use `print(...)` instead of structured logging.
- Files: `backend/gtfs_rt/views.py`, `backend/gtfs_rt/processors/manager.py`, `backend/gtfs_rt/processors/speed.py`, `backend/processors/osm/process.py`
- Impact: noisy output, poor log routing, and weak observability in production.
- Fix approach: replace `print` with module loggers and add consistent log levels/context.

**Monolithic geospatial processing module:**
- Issue: `backend/processors/osm/process.py` is a very large orchestration module with many responsibilities (download, normalize, segment, persist).
- Files: `backend/processors/osm/process.py`
- Impact: high change risk and difficult targeted testing.
- Fix approach: split into downloader, geometry transform, persistence, and orchestration modules.

## Known Bugs

**Potential duplicate GTFS-RT ingestion:**
- Issue: `GTFSRTManager.save_gtfs_rt_to_db()` compares protobuf timestamps as strings and only updates `last_timestamp` in one branch.
- Files: `backend/gtfs_rt/processors/manager.py`, `backend/gtfs_rt/models.py`
- Impact: repeated inserts or skipped records when timestamp ordering is not lexicographic-safe.
- Fix approach: store/compare numeric timestamps and update the checkpoint consistently after successful writes.

**Unsafe assumptions about GTFS-RT database singleton state:**
- Issue: `GTFSRTManager.save_gtfs_rt_to_db()` calls `GTFSRTTimestamp.objects.first()` without checking for an empty table.
- Files: `backend/gtfs_rt/processors/manager.py`
- Impact: startup crashes when the timestamp row has not been seeded.
- Fix approach: create the row if missing or enforce a migration/seed guard.

**Shape processing can dereference invalid state:**
- Issue: `process_shape_data()` logs `len(axis['features'])` before validating that `axis` exists and contains `features`.
- Files: `backend/processors/osm/process.py`
- Impact: KeyError on malformed API responses or fixture corruption.
- Fix approach: validate response shape before logging or indexing.

**Route/direction field drift in tests and models:**
- Issue: `backend/gtfs_rt/tests/test_model.py` references `direction_id`, while `backend/gtfs_rt/models.py` defines `direction`.
- Files: `backend/gtfs_rt/tests/test_model.py`, `backend/gtfs_rt/models.py`
- Impact: test/model mismatch hides real regressions and suggests inconsistent field usage.
- Fix approach: normalize the field name across factories, tests, and model accessors.

## Security Considerations

**Hard-coded secret material:**
- Risk: `backend/backend/settings.py` contains a literal Django secret key.
- Files: `backend/backend/settings.py`
- Current mitigation: none visible in code.
- Recommendations: rotate the secret, load it from env, and ensure committed files never contain production secrets.

**External admin automation credentials are environment-bound but sensitive:**
- Risk: `backend/rest_api/util/alert.py` logs into an external admin site using environment-backed credentials and posts destructive actions.
- Files: `backend/rest_api/util/alert.py`
- Current mitigation: credentials are read from `decouple.config(...)`.
- Recommendations: tighten account permissions, add retry/CSRF/error checks, and avoid broad delete-all workflows without safeguards.

**Debug-only CORS/CSRF behavior can mask production issues:**
- Risk: `backend/backend/settings.py` enables CORS headers and relaxed CSRF behavior only when `DEBUG` is true.
- Files: `backend/backend/settings.py`
- Current mitigation: production path is separate.
- Recommendations: explicitly document production CORS/CSRF requirements and avoid relying on debug-only assumptions.

## Performance Bottlenecks

**Recursive geospatial merging and connectivity checks are expensive:**
- Problem: `backend/processors/osm/process.py` repeatedly loops over geometry pairs and recursively reconnects lines.
- Files: `backend/processors/osm/process.py`
- Cause: O(n²) pairwise checks, repeated reprojection, and recursive re-processing.
- Improvement path: pre-index geometries, reduce reprojections, and cap recursion/iteration depth.

**Repeated queryset evaluation inside view logic:**
- Problem: `backend/gtfs_rt/views.py` calls `queryset.count()` and iterates the queryset after multiple filters and annotations.
- Files: `backend/gtfs_rt/views.py`
- Cause: expensive count/iteration on potentially large pulse sets.
- Improvement path: paginate earlier, avoid repeated evaluations, and use DB-side aggregations where possible.

**Speed generation loads and groups large in-memory datasets:**
- Problem: `backend/gtfs_rt/processors/speed.py` materializes all speed records before bulk insert.
- Files: `backend/gtfs_rt/processors/speed.py`
- Cause: whole-batch accumulation in Python.
- Improvement path: stream/batch per shape or segment and push more aggregation into SQL.

## Fragile Areas

**GTFS pulse filtering and time-window logic:**
- Files: `backend/gtfs_rt/views.py`, `backend/gtfs_rt/services.py`, `backend/gtfs_rt/processors/manager.py`
- Why fragile: multiple paths compute “last 15 minutes” differently, rely on local timezone conversions, and assume timestamp formats remain stable.
- Safe modification: centralize temporal-window helpers and normalize timestamp handling to one timezone model.
- Test coverage: partial; current tests do not cover malformed timestamps, empty checkpoint rows, or boundary-time behavior.

**Stationary detection in expedition speed calculation:**
- Files: `backend/velocity/expedition.py`, `backend/velocity/tests/test_expedition.py`
- Why fragile: logic depends on `None` gaps, route-id exceptions, and threshold-crossing state transitions.
- Safe modification: preserve the threshold-crossed state machine and extend tests for gaps, jitter, and exact-threshold edges.
- Test coverage: good for known scenarios, but not for mixed route IDs, malformed distance arrays, or timestamp disorder beyond `add_gps_point()`.

**Alert creation/update flow against TranSapp:**
- Files: `backend/rest_api/util/alert.py`
- Why fragile: state is split across local DB, remote admin session, and remote HTML forms/CSRF tokens.
- Safe modification: keep request/response parsing isolated and protect destructive operations with idempotency checks.
- Test coverage: not detected for remote failure modes, response schema changes, or authentication expiry.

**GeoJSON/debug artifact generation in the repository tree:**
- Files: `backend/processors/osm/process.py`, `backend/debug/*.geojson`
- Why fragile: processing writes debug outputs to a committed path, which can accumulate stale artifacts and confuse reproducibility.
- Safe modification: route debug exports to an ignored temp directory or make them opt-in.
- Test coverage: none detected for filesystem side effects.

## Test Coverage Gaps

**GTFS-RT ingestion edge cases:**
- What's not tested: empty `GTFSRTTimestamp` rows, duplicate protobuf timestamps, invalid protobuf payloads, and failed HTTP downloads.
- Files: `backend/gtfs_rt/processors/manager.py`, `backend/gtfs_rt/tests/*`
- Risk: silent duplication or crashes in scheduled jobs.
- Priority: High

**View/query parameter parsing:**
- What's not tested: invalid `start_date` / `end_date` formats in `backend/gtfs_rt/views.py`.
- Files: `backend/gtfs_rt/views.py`
- Risk: 500 errors from `datetime.strptime(...)` on malformed requests.
- Priority: High

**OSM processing fallback paths:**
- What's not tested: malformed Overpass responses, empty feature collections, CRS-less geometries, and failures in `connect_lines()` recursion.
- Files: `backend/processors/osm/process.py`, `backend/processors/tests/test_process.py`
- Risk: intermittent failures on real-world map data.
- Priority: High

**Alert sync failure handling:**
- What's not tested: invalid CSRF tokens, login failures, partial delete/update failures, and non-200 admin responses.
- Files: `backend/rest_api/util/alert.py`
- Risk: remote alert state diverges from local state.
- Priority: Medium

**Settings validation:**
- What's not tested: missing env vars for `DB_*`, `REDIS_*`, `TRANSAPP_*`, and `ALERT_AUTHOR`.
- Files: `backend/backend/settings.py`, `backend/rest_api/util/alert.py`
- Risk: startup failures and confusing deployment errors.
- Priority: High

---

*Concerns audit: 2026-04-08*
