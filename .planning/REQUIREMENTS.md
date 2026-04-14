# REQUIREMENTS

## Scope

This milestone covers performance optimization and critical bug fixes for the GPS-to-speed pipeline. No new features, no API changes.

---

## v1 (This Milestone)

### Bug Fixes

**REQ-01** Fix GTFSRTTimestamp empty table crash
- `GTFSRTManager.save_gtfs_rt_to_db()` must not crash when `GTFSRTTimestamp` table is empty
- Use `get_or_create` instead of `objects.first()` with no null guard
- Files: `backend/gtfs_rt/processors/manager.py`
- Priority: Critical (crashes on clean startup)

**REQ-02** Fix timestamp string comparison causing duplicate/skipped records
- Protobuf timestamps must be stored and compared as integers (Unix epoch), not strings
- The `last_timestamp` checkpoint must be updated consistently after every successful write
- Files: `backend/gtfs_rt/processors/manager.py`, `backend/gtfs_rt/models.py`
- Priority: Critical (silent data corruption)

**REQ-03** Fix `direction_id` vs `direction` field name mismatch
- Normalize field name across model definition, factories, and tests
- Files: `backend/gtfs_rt/tests/test_model.py`, `backend/gtfs_rt/models.py`
- Priority: Medium (hides regressions)

### Performance

**REQ-04** Establish baseline metrics before any optimization
- Instrument `GridManager`, `ExpeditionData`, and `ShapeManager` entry points with `perf_counter`
- Record: N° pulses, N° expeditions, N° shapes, HMM time, bulk insert time, peak RAM
- Output: a baseline measurement document or log entry
- Priority: High (required before any other perf work)

**REQ-05** ShapeManager cache must persist across jobs within the same worker process
- Verify and enforce that `ShapeManager` is not re-instantiated per-expedition or per-job
- If re-instantiation is happening, fix the lifecycle so the cache is built once per worker startup
- Files: `backend/velocity/grid.py`, `backend/rest_api/util/shape.py`
- Priority: High

**REQ-06** Reduce GeoDataFrame memory footprint in ShapeManager
- Audit columns loaded per segment: only geometry + id are needed for HMM candidate lookup
- Use `float32` instead of `float64` where sub-meter precision is not required
- Files: `backend/rest_api/util/shape.py`
- Priority: Medium

**REQ-07** Add STRtree spatial index to HMM candidate lookup
- Replace linear O(n) segment search with Shapely STRtree O(log n) for per-GPS-point candidate retrieval
- Files: `backend/rest_api/util/hmm/`
- Priority: High (expected largest single speedup)

**REQ-08** Vectorize Viterbi emission and transition probability computation
- Replace Python loops with NumPy array operations for the (T × N) Viterbi table
- Files: `backend/rest_api/util/hmm/`
- Priority: High

**REQ-09** Streaming bulk insert for Speed records
- Replace full in-memory accumulation in `speed.py` with `bulk_create(..., batch_size=1000)`
- Files: `backend/gtfs_rt/processors/speed.py`
- Priority: High (reduces peak RAM during insert)

**REQ-10** Move monthly speed aggregation to SQL
- Replace Python-side materialization in `avg_speed.py` with Django ORM `annotate(Avg(...))` + `GROUP BY`
- Files: `backend/processors/speed/avg_speed.py`
- Priority: Medium

**REQ-11** Set RQ worker count to match available vCPU and RAM budget
- Audit `HMM_NUM_WORKERS` setting; document the RAM cost per worker with ShapeManager loaded
- Set to 1 or 2 workers based on measured ShapeManager footprint (rule: if >400 MB → 1 worker)
- Files: `backend/backend/settings.py`, `backend/config/environment.py`
- Priority: Medium

### Testing

**REQ-12** Add tests for REQ-01 and REQ-02 fixes
- Test: empty GTFSRTTimestamp table does not crash manager
- Test: integer timestamp comparison prevents duplicate inserts
- Files: `backend/gtfs_rt/tests/`
- Priority: High

---

## v2 (Future / Out of Scope Now)

- Pre-serialized HMM cache to disk (invalidation complexity not worth it yet)
- ProcessPoolExecutor for parallel HMM across expeditions (evaluate after REQ-11 baseline)
- Windowed Viterbi for very long expeditions (>500 points) — evaluate after REQ-07/08
- Lazy per-shape-id loading of ShapeManager (evaluate after REQ-06 baseline)
- Refactor `backend/processors/osm/process.py` into smaller modules
- Structured logging to replace all `print()` statements
- Secret rotation and `SECRET_KEY` env loading
