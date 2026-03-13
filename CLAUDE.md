# Hotel Munich PMS - Project Instructions

## Architecture

- **Backend**: FastAPI + SQLAlchemy + SQLite (Python 3.14)
- **Frontend PC**: Streamlit (admin dashboard)
- **Frontend Mobile**: Next.js (guest-facing / reception mobile app)
- **Auth**: JWT-based via FastAPI with bcrypt password hashing
- **Database**: SQLite with WAL mode for concurrent reads

## Directory Structure

```
backend/          # FastAPI API + services + models
  api/            # Endpoints, deps, middleware, auth
  services/       # Business logic (ReservationService, PricingService, etc.)
  database.py     # SQLAlchemy models + session management
  tests/          # pytest test suite (286 tests, 82% coverage)
    reports/      # Auto-generated KPI/perf JSON reports
frontend_pc/      # Streamlit admin dashboard
frontend_mobile/  # Next.js mobile app
```

## Test Commands

```bash
# Run all tests
cd backend && python -m pytest tests/ -v

# Run with coverage
cd backend && python -m pytest tests/ -v --cov=services --cov=api --cov-report=term-missing

# Run KPI evaluations only (scored 0-100)
cd backend && python -m pytest tests/test_kpis.py -v -m kpi

# Run performance benchmarks only
cd backend && python -m pytest tests/test_performance.py -v -m perf

# Run excluding slow perf tests
cd backend && python -m pytest tests/ -v -k "not perf"
```

## KPI Thresholds

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Overall KPI Score | >= 95 | 90-94 | < 80 |
| Individual KPI | >= 90 | 80-89 | < 70 |
| Performance pass rate | >= 90% | 80-89% | < 80% |
| Test coverage | >= 75% | 60-74% | < 60% |
| Full test pass rate | 100% | >= 95% | < 95% |

## KPIs Measured (test_kpis.py)

1. **Booking Integrity** - Reservation CRUD roundtrips
2. **Occupancy Accuracy** - Occupancy calculations vs expected
3. **Pricing Accuracy** - Price calculations with all modifiers
4. **API Response Time** - Endpoint response under thresholds
5. **Data Consistency** - CRUD cycles, zero orphans
6. **Calendar Sync** - Views agree with each other
7. **Revenue Accuracy** - Revenue sums match manual calculations
8. **Security Compliance** - Protected endpoints reject unauthenticated
9. **Agent Tool Reliability** - All 11 AI tools callable, return strings, handle errors

## Performance Baselines (test_performance.py)

| Method | N=10 | N=100 | N=500 |
|--------|------|-------|-------|
| get_occupancy_map() | <200ms | <500ms | <1500ms |
| get_today_summary() | <200ms | <500ms | <1500ms |
| get_monthly_room_view() | <200ms | <500ms | <1500ms |
| get_revenue_by_room_month() | <200ms | <1000ms | <3000ms |
| get_room_report() | <200ms | <500ms | <2000ms |
| calculate_price() avg | - | - | <50ms |

## Critical Business Logic Files

Changes to these files MUST be validated with KPI tests:

- `backend/services/reservation_service.py` - All reservation operations
- `backend/services/pricing_service.py` - Price calculation engine
- `backend/services/room_service.py` - Room management
- `backend/api/v1/endpoints/reservations.py` - Reservation API
- `backend/api/v1/endpoints/pricing.py` - Pricing API
- `backend/api/v1/endpoints/calendar.py` - Calendar endpoints
- `backend/api/v1/endpoints/ai_tools.py` - AI agent tools (11 functions)
- `backend/api/v1/endpoints/agent.py` - AI agent endpoint + system prompt

## Monthly Maintenance Workflow

A scheduled task runs on the 1st of each month at 9 AM:
1. Runs KPI evaluation suite (including Agent Tool Reliability KPI)
2. Runs performance benchmarks
3. Runs full test suite with coverage
4. Evaluates AI agent: verifies all tools callable, return valid strings, handle edge cases
5. Generates monthly summary with regressions

## Skills Available

- `/hotel-health-check` - On-demand KPI evaluation + full test suite
- `/hotel-perf-benchmark` - On-demand performance benchmarks with analysis

## Monitoring Stack

| Channel | What | How |
|---------|------|-----|
| Discord (runtime) | Backend ERROR/CRITICAL logs | `DiscordWebhookHandler` in `logging_config.py` — auto-sends on error, 5-min dedup, non-blocking |
| Discord (CI) | GitHub Actions failures | `notify-discord` job in `ci.yml` — uses `DISCORD_WEBHOOK_URL` secret |
| Healthchecks.io | Backend uptime | Push ping every 15 min from `_periodic_ical_sync()` in `api/main.py` |
| GitHub Email | CI workflow results | Automatic on push to `main`/`dev` |

## CI Pipeline (GitHub Actions)

Runs on push to `main`/`dev`:
1. **backend-tests**: Install deps → all 286 tests with coverage (75% min, currently 82%) → KPI + perf included → upload reports
2. **frontend-check**: npm ci → npm run build
3. **notify-discord**: Sends Discord alert if any job fails (uses `DISCORD_WEBHOOK_URL` repo secret)

## Development Notes

- Always use `encoding='utf-8'` when opening files in Python
- Test DB uses in-memory SQLite with StaticPool for thread safety
- Credentials for testing: admin/admin123, recepcion/recep123
- Rate limiter is auto-disabled during tests
- The `@with_db` decorator manages session lifecycle for Streamlit calls and AI tool functions
- FastAPI endpoints use `Depends(get_db)` for session injection
- `conftest.py` patches `database.SessionLocal` and `services._base.SessionLocal` so `@with_db` uses test DB
- `PricingService.calculate_price()` requires `client_type_id` (not optional)
- `database.py` must NOT import pandas (removed — was causing CI failures)
- `Pillow` is required in `requirements.txt` for `vision.py` OCR endpoint

## Two-Repo Architecture

- **Public** (`sistema-hotel-m` / origin): deployment code only — no internal docs
- **Private** (`hotel-PMS-dev` / private): full codebase + internal docs
- `origin` has dual push URLs — single `git push origin dev` pushes to both repos
- `.gitignore` excludes: `claude_audit/`, `PROJECT_CONTEXT.md`, `REQUIREMENTS.md`, `.bat` scripts, `.claude/` configs
