# Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a reproducible, test-driven FastAPI foundation that strictly parses SRM attendance HTML and correctly calculates target attendance guidance.

**Architecture:** The backend is a small Python package whose pure `attendance` domain module parses sanitized HTML and performs all attendance arithmetic independently of HTTP or database state. A separate FastAPI application exposes a non-sensitive health endpoint and reads validated settings; persistence, authentication, and ingestion follow in the next milestone.

**Tech Stack:** Python 3.13+, FastAPI, Pydantic Settings, Beautiful Soup, Uvicorn, Pytest, Ruff, and mypy.

**Spec:** `docs/superpowers/specs/2026-09-09-srm-attendance-tracker-design.md`

## Global Constraints

- Python source is formatted and linted with Ruff; public functions are type checked with mypy.
- Test input is sanitized fixture HTML only; no live portal calls, credentials, cookies, or raw personal response data.
- Parser accepts exactly the six documented headers and rejects authentication pages, missing tables, malformed rows, and invalid numerics.
- Totals are integers, calculated percentages derive from totals, and impossible target results are explicit rather than invented.
- The application logs no portal responses, credentials, cookies, tokens, or secrets.
- Every completed task updates `docs/PROJECT_STATUS.md`, runs its stated verification, and is committed at the milestone boundary.

---

### Task 1: Reproducible backend shell

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/srm_tracker/__init__.py`
- Create: `backend/src/srm_tracker/config.py`
- Create: `backend/tests/conftest.py`
- Create: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `srm_tracker.config.Settings`, instantiated from environment with `environment: Literal["development", "test", "production"]`, `database_url: str`, `frontend_origin: str`.
- Produces: `pytest`, `ruff`, and `mypy` commands run from `backend/`.

- [ ] **Step 1: Create project metadata and test/tool configuration**

Create `backend/pyproject.toml` with a `src` package layout and pinned compatible direct dependencies: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `beautifulsoup4`, `pytest`, `httpx`, `ruff`, and `mypy`. Configure `pytest` to collect `tests`, Ruff for Python 3.13, and mypy with `strict = true` for `src/srm_tracker`.

- [ ] **Step 2: Create minimum environment contract**

Create `.env.example` containing only non-secret development placeholders:

```dotenv
SRM_TRACKER_ENVIRONMENT=development
SRM_TRACKER_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/srm_tracker
SRM_TRACKER_FRONTEND_ORIGIN=http://localhost:5173
```

Add an ignore rule for local backend virtual environments and a runtime `.env` file if not already covered.

- [ ] **Step 3: Install locked dependencies and verify tooling is executable**

Run: `cd backend; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install --upgrade pip; .\.venv\Scripts\python.exe -m pip install -e ".[dev]"`

Expected: package installation succeeds and `backend/.venv` remains ignored.

- [ ] **Step 4: Verify the empty test/tool baseline**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest; .\.venv\Scripts\python.exe -m ruff check .; .\.venv\Scripts\python.exe -m mypy src`

Expected: Pytest reports no collected tests (exit code 5 is recorded as expected until Task 2); Ruff and mypy exit 0.

### Task 2: Strict attendance HTML parser

**Files:**
- Create: `backend/src/srm_tracker/attendance/models.py`
- Create: `backend/src/srm_tracker/attendance/parser.py`
- Create: `backend/src/srm_tracker/attendance/__init__.py`
- Create: `backend/tests/fixtures/attendance-valid.html`
- Create: `backend/tests/fixtures/attendance-login.html`
- Create: `backend/tests/fixtures/attendance-malformed.html`
- Create: `backend/tests/test_attendance_parser.py`

**Interfaces:**
- Produces: frozen `AttendanceRecord(code: str, subject: str, total_hours: int, attended_hours: int, absent_hours: int, source_percentage: Decimal)`.
- Produces: `parse_attendance_html(html: str) -> list[AttendanceRecord]`.
- Produces: `AttendanceParseError(ValueError)` for non-attendance, malformed, and invalid numeric responses.

- [ ] **Step 1: Write the failing parser behavior tests**

Create sanitized fixture HTML with the exact header sequence `Code`, `Description`, `Max. hours`, `Attended hours`, `Absent hours`, `Total Percentage`. Write tests that assert a two-row fixture becomes typed records, an unrelated table is ignored, login markup raises `AttendanceParseError`, a table with no usable rows raises, values such as `23.5` for total hours raise, and a row where attended plus absent does not equal total raises.

```python
def test_parses_documented_course_table(valid_html: str) -> None:
    records = parse_attendance_html(valid_html)
    assert records[0].code == "21CSE385J"
    assert records[0].total_hours == 23
    assert records[0].source_percentage == Decimal("69.57")

def test_rejects_login_page(login_html: str) -> None:
    with pytest.raises(AttendanceParseError, match="authentication"):
        parse_attendance_html(login_html)
```

- [ ] **Step 2: Run parser tests to verify they fail because the module is missing**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_attendance_parser.py -q`

Expected: FAIL during collection with `ModuleNotFoundError` for `srm_tracker.attendance`.

- [ ] **Step 3: Implement the smallest strict parser**

Implement header normalization, exact ordered-header matching, cell-count validation, non-empty code/subject validation, integer parsing that rejects decimal/negative values, decimal percentage parsing (allow an optional trailing `%`), and the `attended + absent == total` invariant. Detect an HTML login form/title before table scanning and use `AttendanceParseError`; never return an empty list for an invalid response.

- [ ] **Step 4: Run parser tests and quality checks**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_attendance_parser.py -q; .\.venv\Scripts\python.exe -m ruff check src tests; .\.venv\Scripts\python.exe -m mypy src`

Expected: parser tests, Ruff, and mypy exit 0.

### Task 3: Target calculation domain service

**Files:**
- Create: `backend/src/srm_tracker/attendance/calculations.py`
- Create: `backend/tests/test_attendance_calculations.py`

**Interfaces:**
- Consumes: `AttendanceRecord` source totals.
- Produces: frozen `AttendanceGuidance(current_percentage: Decimal | None, additional_attended_hours: int | None, additional_absences_allowed: int | None, target_reachable: bool)`.
- Produces: `calculate_attendance_guidance(attended_hours: int, total_hours: int, target_percentage: Decimal) -> AttendanceGuidance`.

- [ ] **Step 1: Write failing calculation tests**

Write tests covering zero total hours, exactly 75%, a 16/23 record at 75%, an above-target record, a 100% target with imperfect attendance, a perfect 100% record, and invalid targets (0, negative, greater than 100). Assert the documented answers, including 7 extra attended hours for 16/23 at 75% and 0 allowable further absences there.

```python
def test_calculates_hours_needed_below_target() -> None:
    result = calculate_attendance_guidance(16, 23, Decimal("75"))
    assert result.additional_attended_hours == 7
    assert result.additional_absences_allowed == 0
    assert result.target_reachable is True
```

- [ ] **Step 2: Run calculation tests to verify they fail because the service is missing**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_attendance_calculations.py -q`

Expected: FAIL during collection with `ModuleNotFoundError` for `calculations`.

- [ ] **Step 3: Implement integer-safe calculation logic**

Use `Decimal` and explicit ceiling/floor helpers. Reject negative hours and an `attended_hours` value greater than `total_hours`. For zero total, return `None` numerical guidance and `target_reachable = false`; for non-perfect 100% targets return `additional_attended_hours = None` and `target_reachable = false`; otherwise return exact non-negative integers.

- [ ] **Step 4: Run calculation tests and quality checks**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_attendance_calculations.py -q; .\.venv\Scripts\python.exe -m ruff check src tests; .\.venv\Scripts\python.exe -m mypy src`

Expected: calculation tests, Ruff, and mypy exit 0.

### Task 4: FastAPI settings and health endpoint

**Files:**
- Create: `backend/src/srm_tracker/main.py`
- Create: `backend/tests/test_health.py`

**Interfaces:**
- Consumes: `Settings` from `srm_tracker.config`.
- Produces: `create_app() -> FastAPI` and `GET /api/v1/health` returning `{"status": "ok"}`.

- [ ] **Step 1: Write the failing HTTP test**

```python
def test_health_endpoint_returns_ok() -> None:
    response = TestClient(create_app()).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails because the application factory is missing**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/test_health.py -q`

Expected: FAIL during collection with `ModuleNotFoundError` for `srm_tracker.main`.

- [ ] **Step 3: Implement minimal settings and app factory**

Implement a cached settings getter with the `SRM_TRACKER_` prefix, reject non-HTTPS frontend origins in production, and return the health payload without database access or secret values. Register the route under the versioned API prefix.

- [ ] **Step 4: Run the full Milestone 1 verification suite**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest -q; .\.venv\Scripts\python.exe -m ruff check .; .\.venv\Scripts\python.exe -m mypy src; .\.venv\Scripts\python.exe -c "from srm_tracker.main import create_app; assert create_app().title == 'SRM Attendance Tracker API'"`

Expected: all test commands and import assertion exit 0.

### Task 5: Checkpoint and handoff

**Files:**
- Modify: `docs/PROJECT_STATUS.md`
- Modify: `docs/IMPLEMENTATION_PLAN.md`

- [ ] **Step 1: Record exact tool and test results**

Update the status file with dependency versions, exact verification commands, result counts, current commit, and the next unfinished milestone.

- [ ] **Step 2: Review repository safety and whitespace**

Run: `git check-ignore -v .srm-chrome-session\Default .srm-session\Default venv\Scripts\python.exe backend\.venv\Scripts\python.exe; git diff --check; git status --short`

Expected: all sensitive/local paths are ignored, `git diff --check` has no output, and only intentional source/docs changes are present.

- [ ] **Step 3: Commit the verified milestone**

```powershell
git add .gitignore .env.example backend docs
git commit -m "feat: add attendance backend foundation"
```
