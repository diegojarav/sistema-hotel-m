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
  hotel/          # Generated PDF documents (gitignored)
    Reservas/     # Reservation confirmation PDFs
    Clientes/     # Client registration PDFs
  tests/          # pytest test suite (313 tests, 83% coverage)
    reports/      # Auto-generated KPI/perf JSON reports
frontend_pc/      # Streamlit admin dashboard
  pages/          # Admin pages (Rooms, Users, Config, Documents, AI Assistant)
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
9. **Agent Tool Reliability** - All 12 AI tools callable, return strings, handle errors

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
- `backend/api/v1/endpoints/ai_tools.py` - AI agent tools (12 functions)
- `backend/api/v1/endpoints/agent.py` - AI agent endpoint + system prompt
- `backend/services/document_service.py` - PDF document generation
- `backend/api/v1/endpoints/documents.py` - Document download/list API

## Document Generation System

- **Reservation PDFs**: Auto-generated on creation (both PC and mobile), saved to `backend/hotel/Reservas/`
- **Client PDFs**: Auto-generated on check-in creation, saved to `backend/hotel/Clientes/`
- **Filename format**: `{guest_name}_{dd-mm-yy}_{reservation_id}.pdf` (reservations), `{last_name}_{first_name}_{dd-mm-yy}.pdf` (clients)
- **On-demand generation**: Download endpoints regenerate PDFs if file is missing
- **Mobile download**: Uses `fetch()` + blob pattern with JWT auth header
- **PC browse**: Streamlit "Documentos del Hotel" page reads files directly from disk
- **API endpoints**: `GET /documents/reservations/{id}`, `GET /documents/clients/{id}`, `GET /documents/download/{folder}/{filename}`, `GET /documents/list/{folder}`

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
1. **backend-tests**: Install deps → all 369 tests (v1.4.0: 313 legacy + 56 new caja/transaccion) with coverage (75% min) → KPI + perf included → upload reports
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
- `fpdf2` is required in `requirements.txt` for PDF document generation (`DocumentService`)
- `DocumentService` uses `@with_db` for dual FastAPI/Streamlit compatibility
- PDF documents auto-generate on reservation/check-in creation, saved to `backend/hotel/`
- Streamlit accesses PDF files via direct filesystem read (same machine as backend)

## Reservation Status Lifecycle (v1.4.0 — payment-aware)

5 statuses with auto-transitions based on payments:

```
RESERVADA → SEÑADA → CONFIRMADA → COMPLETADA
    └───────┴──────────┴──→ CANCELADA
```

| Status | How it's set | Blocks rooms? | Color |
|--------|-------------|---------------|-------|
| RESERVADA | Created with zero payments | Yes | Gray |
| SEÑADA | 0 < sum(active transactions) < total | Yes | Amber |
| CONFIRMADA | sum(active transactions) >= total | Yes | Green |
| COMPLETADA | Automatic — check-out date passed (every 15 min) | No (past) | Blue |
| CANCELADA | Manual — admin/reception cancels | No | Red |

- Status is **derived from transactions** — recalculated automatically in `TransaccionService._recalcular_status_reserva()` on every pago registered or voided
- Terminal states (CANCELADA, COMPLETADA) are NEVER auto-changed
- `auto_complete_reservations()` filters on all active states: `["RESERVADA", "SEÑADA", "CONFIRMADA", "Confirmada", "Pendiente"]` for backward compatibility
- `update_status()` endpoint still allows manual overrides

### Backward compatibility
The system supports **both** legacy values (`Pendiente`, `Confirmada`, `Completada`, `Cancelada`) AND new values (`RESERVADA`, `SEÑADA`, `CONFIRMADA`, `COMPLETADA`, `CANCELADA`) simultaneously. All status filters use expanded `.in_()` lists. Migration script `scripts/migrate_caja_transacciones.py` renames existing values in place and creates synthetic TRANSFERENCIA transactions for historical CONFIRMADA reservations.

## Cash Register (Caja) & Transactions (v1.4.0)

### Tables
- `caja_sesion` — cash session per user (opening_balance, closing_balance_declared, closing_balance_expected, difference, status ABIERTA|CERRADA)
- `transaccion` — immutable payment records (amount, payment_method EFECTIVO|TRANSFERENCIA|POS, reserva_id, caja_sesion_id, voided)

### Business rules
- Only one ABIERTA session per user at a time
- EFECTIVO payments REQUIRE an open caja session (hard reject with 400 if none)
- TRANSFERENCIA and POS do NOT require an open session
- Transactions are immutable — only voided, never deleted or updated
- Void requires reason ≥ 3 chars; both admin and recepcion can void
- Closing a session: `expected = opening + sum(EFECTIVO in session)`, `difference = declared - expected`

### Services
- `CajaService` (`backend/services/caja_service.py`) — abrir_sesion, cerrar_sesion, get_current_session, list_sessions, get_session_summary
- `TransaccionService` (`backend/services/transaccion_service.py`) — registrar_pago, anular_transaccion, get_saldo, list_transactions, _recalcular_status_reserva
- Both exported from `services/__init__.py`

### API endpoints
- `POST/GET /api/v1/caja/*` — abrir, cerrar, actual, historial, {session_id}
- `POST/GET /api/v1/transacciones/*` — register, anular, list, reserva/{id}
- `GET /api/v1/reservations/{id}/saldo` — total/paid/pending + transactions
- `GET /api/v1/reportes/ingresos-diarios?fecha=YYYY-MM-DD`
- `GET /api/v1/reportes/transferencias?desde=&hasta=`
- `GET /api/v1/reportes/resumen-periodo?desde=&hasta=`

### Frontend pages
- **Mobile**: `/dashboard/caja` (open/close/transactions), `RegistrarPagoModal` component on reservation detail
- **PC**: `frontend_pc/pages/96_💰_Caja.py` with tabs Sesion Actual / Historial / Reportes Financieros

## Session & Auth Configuration

- JWT access token TTL: **365 days** (hotel runs 24/7, manual logout only)
- JWT refresh token TTL: **365 days**
- `BeaconLogout` removed from layout (no auto-logout on tab close)
- Sessions persist until "Cerrar Sesion" button is clicked
- Config in `backend/api/core/config.py` (ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS)

## AI Agent Tools (14 functions in ai_tools.py)

1. `check_availability` — Room availability for date/stay
2. `get_hotel_rates` — Pricing by category
3. `get_today_summary` — Today's occupancy snapshot
4. `search_guest` — Find guest by name/document
5. `search_reservation` — Find reservation by ID/name
6. `get_reservations_report` — Date range reservation list
7. `calculate_price` — Price calculation with modifiers
8. `get_occupancy_for_month` — Monthly occupancy stats
9. `get_room_performance` — Room revenue/occupancy report
10. `get_booking_sources` — Channel distribution (Direct, Booking, Airbnb, etc.)
11. `get_parking_status` — Parking utilization
12. `get_revenue_summary` — Daily/weekly/monthly/yearly income with breakdown
13. `consultar_caja` — Current cash register session status (balance, movements) — **v1.4.0**
14. `resumen_ingresos_por_metodo` — Income breakdown by payment method — **v1.4.0**

## Two-Repo Architecture

- **Public** (`sistema-hotel-m` / origin): deployment code only — no internal docs
- **Private** (`hotel-PMS-dev` / private): full codebase + internal docs
- `origin` has dual push URLs — single `git push origin dev` pushes to both repos
- `.gitignore` excludes: `claude_audit/`, `PROJECT_CONTEXT.md`, `REQUIREMENTS.md`, `.bat` scripts, `.claude/` configs
