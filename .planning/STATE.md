# STATE

**Last updated:** 2026-04-08
**Current phase:** 1 — Critical Bug Fixes (not started)
**Milestone:** map-matching-optimization

---

## Current Position

Starting fresh. Codebase mapped via `/gsd-map-codebase`. No phases executed yet.

---

## Locked Decisions

- **No infrastructure changes** — optimization must work within the existing single-EC2 Docker stack (2 vCPU, 4 GB RAM)
- **No API contract changes** — REST endpoints and serializer outputs must remain identical
- **Bug fixes before profiling** — REQ-01 and REQ-02 distort measurements; must be fixed before establishing baseline
- **Worker count rule** — If ShapeManager measured footprint exceeds 400 MB, cap at 1 RQ worker; otherwise allow 2

---

## Open Questions

- **ShapeManager lifecycle in RQ workers** — Unknown whether it persists across jobs within the same worker process or is rebuilt per-job. This determines whether REQ-05 is a fix or just a verification.
- **HMM candidate search strategy** — Unknown if current implementation uses STRtree or linear scan. Determines the actual speedup potential of REQ-07.
- **Viterbi table structure** — Unknown if current implementation already uses NumPy arrays or pure Python lists. Determines effort for REQ-08.
- **Typical batch size** — Unknown: how many expeditions per run, how many GPS points per expedition on average. Required for REQ-04 baseline.
- **ShapeManager RAM footprint** — Unknown. Critical for deciding worker count (REQ-11) and whether lazy loading (v2) is worth pursuing.

---

## Blockers

None currently.

---

## Key Files Not Yet Read

These files are referenced in requirements but their internals are not yet known:

- `backend/rest_api/util/hmm/*.py` — Viterbi structure and candidate search
- `backend/velocity/grid.py` — ShapeManager instantiation and RQ job lifecycle
- `backend/rest_api/util/shape.py` — What columns are loaded, cache structure
- `backend/gtfs_rt/processors/speed.py` — Exact accumulation pattern before bulk_create
- `backend/backend/settings.py` — Current value of HMM_NUM_WORKERS

---

## Notes

- The `direction_id` vs `direction` mismatch (REQ-03) is low risk to fix but should be bundled with Phase 1 to avoid a separate small PR.
- `avg_speed.py` SQL migration (REQ-10) is independent of HMM changes and can be parallelized with Phase 4 if needed.
- The v2 backlog items (disk-serialized cache, ProcessPoolExecutor, windowed Viterbi) should only be evaluated after Phase 2 baseline numbers are in hand.
