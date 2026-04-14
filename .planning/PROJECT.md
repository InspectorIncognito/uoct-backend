# PROJECT: uoct-backend — Map Matching & Speed Optimization

## Vision

Optimize the GPS-to-speed pipeline of `uoct-backend` so that map matching (HMM Viterbi) and speed calculation run reliably and efficiently on a constrained EC2 instance with 2 vCPU and 4 GB RAM, without degrading data correctness or requiring infrastructure changes.

## Problem

The current pipeline processes Santiago transit GTFS-RT pulses through an HMM map matching algorithm and bulk speed inserts. Under normal load the EC2 instance (2 vCPU Intel Xeon Platinum 8259CL, 4 GB RAM shared between Django, PostgreSQL, Redis, and RQ workers) shows signs of memory pressure and processing latency. Two known bugs cause silent data corruption (timestamp string comparison) and crash on startup (empty GTFSRTTimestamp table).

## Goals

- Reduce per-expedition processing time to under 500ms
- Keep RQ worker RAM under 800 MB peak
- Fix the two critical data-correctness bugs before optimizing
- Preserve existing data model and API contracts (no breaking changes)
- No new infrastructure — optimize within the current single-EC2 Docker stack

## Non-Goals

- Migrating to a different map matching library
- Horizontal scaling or new EC2 instances
- Changes to the REST API surface or client-facing behavior
- Rewriting in a compiled language

## Tech Context

- Python 3.12, Django 4.1, DRF, RQ + rq_scheduler
- PostgreSQL + psycopg2, Redis
- GeoPandas, Shapely, NetworkX, NumPy, pandas
- Dockerized: Gunicorn + Nginx + PostgreSQL + Redis on a single EC2
- GTFS-RT protobuf from Santiago's Red Metropolitana (Sonda S3 feed)

## Key Files

- `backend/velocity/grid.py` — HMM orchestration, ShapeManager lifecycle
- `backend/velocity/expedition.py` — expedition grouping, speed calc
- `backend/rest_api/util/hmm/` — Viterbi implementation
- `backend/rest_api/util/shape.py` — ShapeManager, GeoDataFrame caches
- `backend/gtfs_rt/processors/manager.py` — GTFS-RT ingestion, dedup
- `backend/gtfs_rt/processors/speed.py` — bulk speed insert
- `backend/processors/speed/avg_speed.py` — monthly historic aggregation
- `backend/backend/settings.py` — HMM_NUM_WORKERS, RQ config
