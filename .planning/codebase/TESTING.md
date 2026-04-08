# Testing Patterns

**Analysis Date:** 2026-04-08

## Test Framework

**Runner:**
- Django test runner via `make test` from `Makefile`.
- CI uses `.github/workflows/test_task.yml` to run `make test` on pushes and pull requests.

**Assertion Library:**
- Standard `unittest` assertions through `django.test.TestCase` and `django.test.SimpleTestCase`.
- DRF test helpers via `rest_framework.test.APITestCase` and `rest_framework.test.APIClient`.

**Run Commands:**
```bash
make test
make test_down
```

## Test File Organization

**Location:**
- Tests are co-located inside app-specific `tests/` packages, e.g. `backend/rest_api/tests/`, `backend/user/tests/`, and `backend/velocity/tests/`.

**Naming:**
- Files use `test_*.py` and `tests_*.py` patterns, with one module often grouping a related test area.

**Structure:**
```text
backend/<app>/tests/
├── __init__.py
├── test_*.py
└── tests_*.py
```

## Test Structure

**Suite Organization:**
```python
class BaseTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

    def _make_request(self, client, method, url, data=None, status_code=status.HTTP_200_OK, json_process=False, **additional_method_params):
        response = method_obj(url, data, **additional_method_params)
        if response.status_code != status_code:
            print(f"error {response.status_code}: {response.content}")
            self.assertEqual(status_code, response.status_code)

        if json_process:
            return json.loads(response.content)
        return response
```

**Patterns:**
- Use shared base classes for request helpers and authentication setup (`backend/rest_api/tests/tests_views_base.py`, `backend/backend/tests/baseTest.py`).
- Split tests by behavior area: model behavior (`backend/rest_api/tests/test_models.py`), utility logic (`backend/rest_api/tests/test_util.py`), view APIs (`backend/user/tests/tests_views_user.py`), and algorithmic behavior (`backend/velocity/tests/test_expedition.py`).
- Prefer scenario-driven methods with descriptive names like `test_verify_wrong_token()` and `test_continuous_stop_over_threshold_flagged()`.

## Mocking

**Framework:**
- `unittest.mock` via `patch` and `MagicMock`.
- `factory_boy` for generating model instances in tests.

**Patterns:**
```python
from unittest.mock import MagicMock, patch

@patch("velocity.expedition.get_current_timezone")
def test_small_negative_delta_is_skipped_not_clamped(self, mock_tz):
    mock_tz.return_value = UTC
    sc = self._make_segment_criteria_mock()
    exp = self._make_routed_exp_with_distances([1000.0, 997.0, 1050.0])
    rows = exp.calculate_speed(sc, local_timezone=UTC)
```

**What to Mock:**
- External time sources, expensive algorithm dependencies, and collaborator objects that do not need DB access, as seen in `backend/velocity/tests/test_expedition.py`.
- Non-deterministic route/segment selection in speed-calculation tests.

**What NOT to Mock:**
- Core model behavior and serializer output when the test is intended to verify actual persistence or response shape, such as `backend/rest_api/tests/test_models.py` and `backend/user/tests/tests_views_user.py`.

## Fixtures and Factories

**Test Data:**
```python
class SegmentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Segment

    shape = factory.SubFactory(ShapeFactory)
    segment_id = factory.Faker("uuid4")
    sequence = 0
    bearing = 0.0
    geometry = [[0.0, 0.0], [0.0, 0.1], [1.0, 1.0]]
```

**Location:**
- Shared factories live in `backend/rest_api/factories.py`.
- Test helper methods live in `backend/rest_api/tests/tests_views_base.py` and `backend/backend/tests/baseTest.py`.
- A fixed GeoJSON fixture path is referenced from `backend/rest_api/tests/test_util.py` via `config.paths.FIXTURE_PATH`.

## Coverage

**Requirements:**
- No coverage threshold is enforced in config.
- `coverage` is present in `requirements-dev.txt`, but no coverage config file is detected.

**View Coverage:**
```bash
coverage run -m pytest
coverage report
```
Not configured in-repo; use Django test execution through `make test` as the canonical workflow.

## Test Types

**Unit Tests:**
- Pure logic tests target algorithmic code in `backend/velocity/tests/test_expedition.py` and data transformation in `backend/rest_api/tests/test_models.py`.

**Integration Tests:**
- Request/response tests hit DRF endpoints with `APIClient`, especially `backend/user/tests/tests_views_user.py`.
- Model + DB integration is common in `backend/rest_api/tests/test_models.py` and `backend/rest_api/tests/test_util.py`.

**E2E Tests:**
- Not detected.

## Common Patterns

**Async Testing:**
```python
class BaseTestCase(APITestCase):
    def login_process(self):
        user_credentials = {"username": "TestUser", "password": "TestPassword"}
        self.create_user(**user_credentials)
        login_response = self._make_request(self.client, self.POST_REQUEST, reverse('login'), data=user_credentials)
        login_token = json.loads(login_response.content.decode('utf-8'))['token']
        self.client.credentials(HTTP_AUTHORIZATION='Token {}'.format(login_token))
```

**Error Testing:**
```python
with self.assertRaises(ValueError) as ctx:
    exp.calculate_speed(MagicMock(), local_timezone=UTC)
self.assertIn("shape_id", str(ctx.exception))
```

## Practical Guidance

**Authentication tests:**
- Use `BaseTestCase.login_process()` from `backend/rest_api/tests/tests_views_base.py` or explicit token setup when testing authenticated views.

**Geometry-heavy tests:**
- Build shapes and segments with factory methods or helper methods, then compare GeoJSON structures directly.

**Request helpers:**
- Reuse `_make_request()` for status-code assertions to keep API tests consistent and to surface response payloads on failure.

---

*Testing analysis: 2026-04-08*
