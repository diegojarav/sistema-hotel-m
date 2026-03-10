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
  database/       # SQLAlchemy models + session management
  tests/          # pytest test suite (237+ tests)
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

-  - All reservation operations
-  - Price calculation engine
-  - Room management
-  - Reservation API
-  - Pricing API
-  - Calendar endpoints

## Monthly Maintenance Workflow

A scheduled task runs on the 1st of each month at 9 AM:
1. Runs KPI evaluation suite
2. Runs performance benchmarks
3. Runs full test suite with coverage
4. Generates monthly summary with regressions

## Skills Available

-  - On-demand KPI evaluation + full test suite
-  - On-demand performance benchmarks with analysis

## Development Notes

- Always use  when opening files in Python
- Test DB uses in-memory SQLite with StaticPool for thread safety
- Credentials for testing: admin/admin123, recepcion/recep123
- Rate limiter is auto-disabled during tests
- The  decorator manages session lifecycle for Streamlit calls
- FastAPI endpoints use  for session injection
-  requires  (not optional)
