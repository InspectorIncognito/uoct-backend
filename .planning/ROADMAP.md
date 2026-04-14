# ROADMAP

## Milestone: map-matching-optimization

Optimize the GPS-to-speed pipeline for EC2 2vCPU / 4GB RAM. Fix critical data bugs first, then profile, then optimize.

---

## Phases

### Phase 1 — Critical Bug Fixes [ ]
Fix the two data-correctness bugs that corrupt or crash the pipeline before any profiling or optimization work begins.

Requirements: REQ-01, REQ-02, REQ-03, REQ-12

**Plans:** 2 plans

Plans:
- [ ] 01-01-PLAN.md — Prevent empty checkpoint crashes and duplicate timestamp writes
- [ ] 01-02-PLAN.md — Normalize GPS pulse direction naming with backward-compatible alias

### Phase 2 — Baseline Profiling [ ]
Instrument the pipeline and measure current performance so every subsequent optimization can be validated against real numbers.

Requirements: REQ-04

### Phase 3 — ShapeManager & Memory [ ]
Ensure the HMM cache is not rebuilt unnecessarily and reduce the GeoDataFrame footprint so the worker fits within the RAM budget.

Requirements: REQ-05, REQ-06, REQ-11

### Phase 4 — HMM Algorithm Optimization [ ]
Speed up the Viterbi core with a spatial index for candidate lookup and NumPy vectorization of the probability tables.

Requirements: REQ-07, REQ-08

### Phase 5 — Speed Pipeline Memory [ ]
Replace full in-memory accumulation in the speed insert path with streaming batch inserts, and push monthly aggregation into SQL.

Requirements: REQ-09, REQ-10

---

## Status Legend
[ ] Not started  [~] In progress  [x] Complete
