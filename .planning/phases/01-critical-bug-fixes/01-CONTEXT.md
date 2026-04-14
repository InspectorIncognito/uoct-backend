# Phase 1: Critical Bug Fixes - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix the critical GPS-to-speed pipeline bugs required before any profiling or optimization work begins. This phase stays within the existing EC2/Docker stack and does not add new capabilities.

</domain>

<decisions>
## Implementation Decisions

### Direction field normalization
- **D-01:** Keep the `direction` model field, and treat `direction` / `direction_id` as the same concept across code and tests.
- **D-02:** Keep the stored field numeric, but normalize GTFS direction values consistently so the model, factories, and tests agree on the same internal representation.
- **D-03:** Preserve backward compatibility in code paths that still reference `direction_id` while making `direction` the canonical field name.

### Phase priorities
- **D-04:** The HMM / speed-calculation optimization work is deferred to later phases; it is not part of Phase 1 bug fixing.
- **D-05:** The EC2 runtime target (2 vCPU, 4 GB RAM, about 4 minutes total speed calculation) is a constraint for later optimization phases, not a change to Phase 1 scope.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and constraints
- `.planning/ROADMAP.md` — Phase 1 scope and milestone ordering
- `.planning/REQUIREMENTS.md` — REQ-01, REQ-02, REQ-03, REQ-12 for this phase
- `.planning/PROJECT.md` — no API or infrastructure changes; current EC2/RAM constraints
- `.planning/STATE.md` — locked decisions and known open questions

### GTFS-RT ingestion bug fixes
- `backend/gtfs_rt/processors/manager.py` — empty timestamp row handling and duplicate ingestion logic
- `backend/rest_api/models.py` — `GTFSRTTimestamp` singleton model
- `backend/gtfs_rt/models.py` — GPS pulse direction field definition

### Tests and regressions
- `backend/gtfs_rt/tests/test_model.py` — current direction-field regression coverage
- `.planning/codebase/CONCERNS.md` — documented ingestion and field-name mismatches

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GTFSRTTimestamp` singleton model: existing checkpoint row for GTFS-RT ingestion state.
- `GPSPulse` model: current persistence target for ingested pulses.

### Established Patterns
- The codebase uses direct Django ORM writes and small manager classes for ingestion.
- Tests are scenario-driven and co-located under app-specific `tests/` packages.

### Integration Points
- `backend/gtfs_rt/processors/manager.py` is the main ingestion gate for the Phase 1 fixes.
- `backend/gtfs_rt/tests/test_model.py` should be updated to match the finalized direction-field behavior.

</code_context>

<specifics>
## Specific Ideas

- The user wants `direction` and `direction_id` treated as equivalent.
- The user indicated the underlying stored direction should stay numeric.

</specifics>

<deferred>
## Deferred Ideas

- HMM and speed-calculation optimization for the constrained EC2 worker is a later-phase concern.
- The target of keeping total speed calculation around 4 minutes belongs in optimization work, not Phase 1.

</deferred>

---

*Phase: 01-critical-bug-fixes*
*Context gathered: 2026-04-08*
