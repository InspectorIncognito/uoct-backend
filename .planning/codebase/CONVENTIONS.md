# Coding Conventions

**Analysis Date:** 2026-04-08

## Naming Patterns

**Files:**
- Django app modules use short, lowercase names under `backend/` such as `backend/user/views.py`, `backend/rest_api/models.py`, `backend/velocity/expedition.py`, and `backend/gps/serializers.py`.
- Test files use `test_*.py` and `tests_*.py` naming, for example `backend/rest_api/tests/test_models.py`, `backend/rest_api/tests/test_util.py`, and `backend/user/tests/tests_views_user.py`.

**Functions:**
- Use `snake_case` for functions and methods, including private helpers like `backend/rest_api/views.py::_build_where_clause()` and `backend/rest_api/views.py::_copy_stream()`.
- View actions remain verb-style and descriptive, such as `LoginViewSet.post()`, `SpeedViewSet.to_csv_local_gz()`, and `AlertViewSet.active()`.

**Variables:**
- Use `snake_case` for local variables and parameters, e.g. `start_time`, `temporal_segment`, `distance_threshold`, and `login_token` in `backend/user/views.py` and `backend/rest_api/views.py`.
- Constants use `UPPER_SNAKE_CASE`, for example `WARNING_THRESHOLD`, `CRITICAL_THRESHOLD`, and `MANAGED_HOOKS` in `.opencode/hooks/gsd-context-monitor.js` and `.opencode/hooks/gsd-check-update.js`.

**Types:**
- Django models use singular PascalCase classes in `backend/rest_api/models.py` and `backend/user/models.py`.
- Test classes use PascalCase with a `Test` suffix or domain prefix, such as `GeometryTestCase`, `ShapeTest`, `UserRequestViewSetTest`, and `TestCalculateSpeedValueErrors`.

## Code Style

**Formatting:**
- The codebase follows standard Python formatting with 4-space indentation and line wrapping for long expressions.
- String quoting is mixed between single and double quotes across the repository; preserve local file style when editing existing files.

**Linting:**
- No dedicated formatter or linter config is detected at repository root (`.eslintrc*`, `eslint.config.*`, `.prettierrc*`, `biome.json`, `ruff.toml`, `pyproject.toml` not detected).
- Keep changes conservative and consistent with surrounding Django/Python style in files under `backend/`.

## Import Organization

**Order:**
1. Standard library imports.
2. Third-party imports.
3. Local project imports.

This pattern appears in `backend/rest_api/views.py`, `backend/user/views.py`, and `backend/rest_api/tests/test_models.py`.

**Path Aliases:**
- Not detected. Imports are absolute module imports such as `from rest_api.models import Shape` and `from velocity.grid import GridManager`.
- Preserve the current import style instead of introducing aliasing.

## Error Handling

**Patterns:**
- API views return `JsonResponse` for explicit success/failure payloads and use HTTP status codes directly, e.g. `backend/user/views.py::LoginViewSet.post()` and `backend/rest_api/views.py::ProcessAxisView.post()`.
- Serializer validation uses `serializers.ValidationError` for field-level errors in `backend/rest_api/serializers.py` and `backend/user/serializers.py`.
- Broad exception handling is used in a few view methods (`backend/rest_api/views.py::ProcessAxisView.post()`), but the preferred pattern is still explicit validation before the command or DB action.
- Some utility code silently ignores errors in best-effort paths, especially `.opencode/hooks/*.js` and streaming helpers in `backend/rest_api/views.py::_copy_stream()`.

## Logging

**Framework:**
- Not detected in application code; tests and utilities primarily rely on `print()` or silent failure patterns.

**Patterns:**
- Avoid adding ad hoc logging unless it matches nearby code; if debugging output is needed, prefer targeted, temporary diagnostics over permanent prints.

## Comments

**When to Comment:**
- Comments document non-obvious business rules, performance assumptions, or API behavior, as seen in `backend/rest_api/views.py`, `backend/rest_api/models.py`, and `.opencode/hooks/*.js`.
- Inline comments are used heavily in tests to explain scenarios and edge cases, especially in `backend/velocity/tests/test_expedition.py`.

**JSDoc/TSDoc:**
- Not applicable to the Python app.

## Function Design

**Size:**
- Prefer small helpers for reusable logic; larger view modules like `backend/rest_api/views.py` centralize related actions but split implementation into private helpers.
- Keep methods focused on one responsibility: query construction, streaming, serialization, or response formatting.

**Parameters:**
- Pass request state explicitly (`request`, `*args`, `**kwargs`) in Django views and keep helper signatures narrow, e.g. `BaseTestCase._make_request()` in `backend/rest_api/tests/tests_views_base.py`.

**Return Values:**
- Return Django response objects from views, serializer data from serializers, and plain Python data structures from internal helpers.
- Helpers often return tuples or dicts when building query fragments or aggregate results, such as `backend/rest_api/views.py::_build_where_clause()` and `backend/rest_api/views.py::_delete_axis_shapes()`.

## Module Design

**Exports:**
- Modules expose Django models, serializers, views, and utility functions directly; there are few wrapper layers.
- Keep module-level names explicit and importable from their defining file paths such as `backend/rest_api/models.py`, `backend/rest_api/serializers.py`, and `backend/rest_api/views.py`.

**Barrel Files:**
- Not detected.

## Repository-Specific Conventions

**Django apps:**
- App-level code lives under `backend/<app>/` and separates `models.py`, `views.py`, `serializers.py`, `urls.py`, `admin.py`, `migrations/`, and `tests/`.
- Router-style endpoint registration is used in `backend/rest_api/urls.py` and `backend/backend/urls.py`.

**Validation-heavy code:**
- Favor serializer validation over manual field parsing when input originates from HTTP requests, as shown in `backend/user/serializers.py` and `backend/rest_api/serializers.py`.

**Constants and domain rules:**
- Centralized constants live in module files like `backend/velocity/constants.py`, `backend/rest_api/vars.py`, and `.opencode/hooks/*.js`.

---

*Convention analysis: 2026-04-08*
