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
  tests/          # pytest test suite (824 tests, 83% coverage)
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
9. **Agent Tool Reliability** - All 18 AI tools callable, return strings, handle errors

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
- `backend/api/v1/endpoints/ai_tools.py` - AI agent tools (18 functions)
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
1. **backend-tests**: Install deps → all 824 tests (v1.10.0-dev: 752 v1.10.0-Phase-2b baseline + 12 Phase 2c multi-vehicle + 33 Phase 2d multi-currency + 27 Phase 2e hotel-day) with coverage (75% min) → KPI + perf included → upload reports
2. **frontend-check**: npm ci → npm run build
3. **notify-discord**: Sends Discord alert if any job fails (uses `DISCORD_WEBHOOK_URL` repo secret)

## Development Notes

- Always use `encoding='utf-8'` when opening files in Python
- Test DB uses in-memory SQLite with StaticPool for thread safety
- Credentials for testing: admin/admin123, recepcion/recep123
  > **Nota**: Las credenciales en `README.md` (`admin/1234`, `recepcion/1234`) son credenciales de demo para el repositorio público. Las credenciales reales del entorno de desarrollo y prod están seedeadas por `seed_monges.py` (admin/admin123, recepcion/recep123) y los tokens viven en `.env` (gitignored).
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
- **AI tool args in TOOLS_LIST**: Every AI tool called by `test_tools_return_strings` (KPI test) is invoked with `()` unless listed in `tool_inputs`. If a tool has a required `str` arg (not Optional), the KPI test will fail with `TypeError: missing required positional argument`. Always use `Optional[str] = None` for AI tool query params and handle the None case gracefully.
- **AI tools must use @with_db services, NOT session_factory() directly**: `conftest.py` patches `SessionLocal` (used by `@with_db`) but NOT `session_factory`. AI tools that call `db = session_factory()` bypass the test DB → `OperationalError: no such table` in CI. See commit `439294c` for the fix pattern.
- **slowapi rate limiter**: `request: Request` must be the FIRST positional parameter in any endpoint decorated with `@limiter.limit()`. If a path param comes first, slowapi silently ignores the rate limit. See commit `f464059`.
- **st.download_button cannot be inside st.form()**: Streamlit raises `StreamlitAPIException`. Store PDF paths in `st.session_state` inside the form, render download buttons outside. See commit `3bc0a58`.
- **Gemini agent: keep system prompt short with many tools**. Gemini 2.5 Flash returns `response.text=None` and `candidate.content.parts=None` when a ~3000+ char `system_instruction` combines with 16 tools. Tool docstrings are read directly from `tools=` so don't duplicate them in the prompt. See commits `544e0ca`, `202b8dd`, `f3a71e6` (null guards + trimmed prompt to ~800 chars).
- **Calendar service methods must include `Completada`/`COMPLETADA` status**. `get_occupancy_map`, `get_weekly_view`, `get_monthly_events`, `get_daily_status` are used for historical views — past reservations must render. `get_range_status` and `create_reservations` should EXCLUDE completed/cancelled (they check availability for new bookings). See commit `9dd4f3e`.
- **Deploy `scripts/deploy_staging.sh` pushes `dev:main` to both origin + private**. If the public `origin/main` has PR-merge commits that don't exist locally, the push is rejected — force-push with `git push --force origin dev:main` (safe because the PR commits are just GitHub UI wrappers over content already in `dev`).
- **Schema drift between dev DB and VM DB**: always add a numbered migration in `scripts/migrations/NNN_*.py` when adding a column to any SQLAlchemy model. The VM's `hotel.db` predates reseeding. Missing migrations surface as `OperationalError: no such column` on deploy. See migration 004 for the contact_email backfill pattern.
- **`launch.json` backend bind: `--host 0.0.0.0`** (NOT `127.0.0.1`). Mobile dev is configured with `NEXT_PUBLIC_API_URL=http://192.168.3.140:8000` (LAN IP) so testing from a real phone on Wi-Fi works. Binding only to `127.0.0.1` makes the Claude_Preview in-browser preview AND the phone fail with `TypeError: Failed to fetch` (no HTTP response — the api client's hardcoded Spanish messages don't intercept network failures). Bind on `0.0.0.0` and both interfaces (localhost + LAN IP) respond. See v1.10.0-dev fix.
- **Streamlit caches `services/__init__.py` exports across hot-reloads**. When you ADD a new export (e.g. `from services.currency_service import CurrencyService`) and any page tries `from services import CurrencyService`, Streamlit's hot-reload reruns the PAGE script but NOT the cached top-level package. The page hits `ImportError: cannot import name 'CurrencyService'` until the streamlit process is fully restarted (`Ctrl+C` + relaunch). Backend uvicorn doesn't have this problem — its `--reload` flag does a full child-process restart on file change. Symptom is a fresh ImportError after pulling new code; remedy is always "restart Streamlit", never a code fix. Documented after Phase 2d ship (2026-05-18).
- **`api_get` in PC pages returns `None` for both HTTP failures AND legitimate JSON `null` responses**. `/caja/actual` legitimately returns `null` when there's no open session — that's the API's "no shift right now" signal, not an error. Pages that error-stop on `current is None` mask the real "no session" UI below. Pattern: use `if not current:` to treat None/empty as "no data, render empty state"; only catch true API failures via try/except around `api_get` OR via inspecting status code (currently `api_get` swallows both, so `not current` is the pragmatic check). Fixed in `96_💰_Caja.py` 2026-05-18 (commit `ac55be4`).
- **`tab_reserva.py` has been hit twice by missing-import bugs** (`time` from `datetime` in commit `a7ada20`). The pattern: a pre-existing `isinstance(x, time)` check uses a symbol that was never imported; the bug doesn't surface until someone exercises that exact code path (an edit on a reservation that has `arrival_time` set). When adding code that uses ANY symbol, double-check the top-level imports — Streamlit pages don't have a linter in CI. Same applies to `from datetime import date`, `from typing import Optional`, etc.
- **React `useEffect` dependency arrays — the auto-shrink/auto-cap pattern is dangerous**. Effects that read-and-write the same state (e.g. "if `mealGuests > cap`, set `mealGuests = cap`") must NOT include the value-being-shrunk in their dep array, or they fire on every keystroke and snap-back any decrement attempt. Depend only on the thing whose CHANGE triggers the action (`totalRoomCapacity` in our case). Add `eslint-disable-next-line react-hooks/exhaustive-deps` with an inline comment so future readers don't "fix" the dep array back. See commit `a7ada20` for the breakfast-guests case.
- **GCP staging external IP is ephemeral** — every `gcloud compute instances stop/start` cycle reassigns the external IP. Tracked recent values: `34.29.241.50` (2026-05-17), `34.10.52.145` (2026-05-18), `136.119.0.159` (2026-05-19). Fix: reserve a static external IP in GCP console (~$3/mo) and bind it to the instance — eliminates the demo-URL drift each session. Until then, post-start the user has to fetch the new IP via `gcloud compute instances describe ... --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`.

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

## Channel Manager v2 (v1.5.0 — Phase 2)

### Tables
- `ical_feeds` — extended with `last_sync_status` (OK|ERROR|NEVER), `last_sync_error`, `consecutive_failures`, `last_sync_attempted_at`
- `ical_sync_log` — per-attempt audit trail (status, counts, error_message, duration_ms); pruned to last 100 per feed
- `reservations` — extended with `ota_booking_id`, `needs_review`, `review_reason`

### Sources supported (v1.5.0)
`Booking.com`, `Airbnb`, `Vrbo`, `Expedia`, `Custom` (Custom accepts any standard .ics URL with a free-text source label).

### Sync behavior
- `_periodic_ical_sync()` runs every 15 minutes (unchanged)
- `ICalService.sync_feed()` now also:
  - Detects cancellations: UIDs that disappeared from the feed → mark reservation `needs_review=True` (Discord alert)
  - Detects conflicts: overlapping bookings on same room → log + count (still creates the OTA reservation since OTA is authoritative)
  - Tracks per-feed health: `consecutive_failures` increments on failure, resets on success
  - Sends Discord ERROR-level alert when `consecutive_failures >= 3` (auto-routed via `DiscordWebhookHandler`)
  - Writes `ICalSyncLog` row with all stats per attempt
  - Extracts OTA booking IDs from VEVENT DESCRIPTION via regex (`Reservation: 1234`, `airbnb.com/reservations/HM...`, etc.)

### Cancellation handling
**Decision: flag for review, not auto-cancel.** When a UID disappears:
1. Reservation marked `needs_review=True` with `review_reason`
2. Discord alert fires
3. Operator confirms via PC admin or mobile detail page:
   - **Acknowledge** → `needs_review=False`, reservation stays active
   - **Confirm OTA cancellation** → `status=CANCELADA` with reason

If the same UID reappears in a later sync (transient OTA glitch), the flag is auto-cleared.

### API endpoints
- `GET /api/v1/ical/feeds/{feed_id}/health` — per-feed health summary
- `GET /api/v1/ical/feeds/{feed_id}/logs?limit=20` — sync history
- `GET /api/v1/reservations/needs-review` — list flagged reservations
- `POST /api/v1/reservations/{id}/acknowledge-review` — clear flag, keep active
- `POST /api/v1/reservations/{id}/confirm-ota-cancellation` — set CANCELADA
- `GET /api/v1/ical/export/{room_id}.ics` — rate limited to **60 req/min per IP**
- `GET /api/v1/ical/export/all.ics` — rate limited to **30 req/min per IP**

### Frontend
- **PC**: `09_🔧_Configuracion.py` with health badges (🟢/🟡/🔴/⚪), per-feed history modal, source dropdown (5 sources), and a "Reservas por revisar" section with acknowledge/cancel buttons
- **Mobile**: `/dashboard/channels` read-only status page (recepcionist) + "Canales" tile on dashboard with feed counts and alert badge
- **Mobile**: needs_review banner on reservation detail with [No, mantener] / [Confirmar cancelación] actions

## Session & Auth Configuration

- JWT access token TTL: **365 days** (hotel runs 24/7, manual logout only)
- JWT refresh token TTL: **365 days**
- `BeaconLogout` removed from layout (no auto-logout on tab close)
- Sessions persist until "Cerrar Sesion" button is clicked
- Config in `backend/api/core/config.py` (ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS)

## Room Charges & Product Inventory (v1.6.0 — Phase 3)

### Tables
- `producto` — catalog: id, name, category (BEBIDA|SNACK|SERVICIO|MINIBAR|OTRO), price, stock_current, stock_minimum, is_stocked, is_active
- `consumo` — line-item charges against a reservation (immutable, voided-only). Captures producto_name + unit_price as snapshots
- `ajuste_inventario` — audit trail of stock changes (COMPRA | MERMA | AJUSTE), signed quantity_change

### Business rules
- Consumo can only be registered for active reservations (RESERVADA | SEÑADA | CONFIRMADA + legacy)
- Stocked products have stock_current decremented on registration, restored on void
- Services (is_stocked=False) skip stock checks
- Unit price + producto_name are captured as snapshots (preserves history when prices change or products are renamed)
- After any consumo change, TransaccionService._recalcular_status_reserva() runs and status may downgrade (CONFIRMADA → SEÑADA if new pending balance)
- Low-stock Discord alert fires when post-adjustment stock ≤ stock_minimum (via DiscordWebhookHandler on ERROR log)
- Products can be soft-deleted via is_active=False (hides from selectors but preserves history)

### Services
- `ProductService` — create/update/deactivate, adjust_stock, list_products, get_low_stock_products, get_top_selling, list_adjustments
- `ConsumoService` — registrar_consumo, anular_consumo, list_by_reserva, get_consumo_total
- `TransaccionService.get_saldo()` — now returns `{total, room_total, consumo_total, paid, pending, transacciones}` (breakdown)
- `DocumentService.generate_folio_pdf(reservation_id)` — Cuenta del Huésped PDF with room charges, consumos, payments, balance. Saved to `hotel/Cuentas/`. Auto-generated on COMPLETADA transition.

### API endpoints
- `GET /api/v1/productos` — list, filter by category
- `GET /api/v1/productos/{id}` — detail
- `POST /api/v1/productos` — create (admin)
- `PATCH /api/v1/productos/{id}` — update (admin)
- `DELETE /api/v1/productos/{id}` — soft delete (admin)
- `POST /api/v1/productos/{id}/ajuste-stock` — adjust stock (admin)
- `GET /api/v1/productos/{id}/ajustes` — adjustment history (admin)
- `GET /api/v1/productos/stock-bajo` — low-stock list (admin)
- `GET /api/v1/productos/mas-vendidos?desde=&hasta=&limit=` — top-selling (admin)
- `POST /api/v1/consumos` — register (admin + recepcion)
- `POST /api/v1/consumos/{id}/anular` — void (admin only)
- `GET /api/v1/consumos/reserva/{reserva_id}` — list active consumos
- `GET /api/v1/documents/folio/{reservation_id}` — download (always regenerates)
- `GET /api/v1/documents/list/Cuentas` — list folio PDFs

### Permissions
| Action | Admin / Supervisor / Gerencia | Recepcion |
|---|---|---|
| Product CRUD, stock adjustments, reports | ✅ | ❌ 403 |
| Register consumo | ✅ | ✅ |
| Void consumo | ✅ | ❌ 403 |
| List products, download folio | ✅ | ✅ |

### Frontend
- **Mobile**: `RegistrarConsumoModal` on reservation detail (grouped-by-category selector + qty stepper + low-stock warnings). New "Consumos" section with itemized list + "Agregar consumo" button. New "Descargar Cuenta (folio)" button.
- **PC**: new `frontend_pc/pages/95_📦_Inventario.py` with 4 tabs (Productos, Stock y ajustes, Stock bajo, Mas vendidos + CSV export)

## Meal Plan Configuration & Kitchen Reports (v1.7.0 — Phase 4)

### Key principle: **optional everywhere**
Hotels that don't serve meals keep `meals_enabled=false` (the default). In that mode the system behaves **exactly as pre-Phase-4** — no UI changes on mobile, no plan selector, no kitchen page, no AI tool activity. This is a zero-regression gate and is covered by tests in `test_meal_config.py` + `test_kitchen_report.py::test_disabled_returns_empty`.

### 3 modes (when enabled)
| Mode | Behavior | Reservation form | Kitchen report |
|---|---|---|---|
| `INCLUIDO` | Breakfast built into room rate. No plan selector shown. Backend auto-assigns `CON_DESAYUNO` and counts all guests. | Hidden | All active overnight guests |
| `OPCIONAL_PERSONA` | Per-person-per-night surcharge. Form shows plan dropdown + "Desayunos" input. | Visible | Only guests with `breakfast_guests > 0` |
| `OPCIONAL_HABITACION` | Flat per-room-per-night surcharge. Form shows plan dropdown (no pax field). | Visible | Only rooms with a non-SOLO plan |

### Tables
- `properties` — extended with `meals_enabled` (Integer, default 0) + `meal_inclusion_mode` (String, nullable). Legacy `breakfast_included` kept for back-compat (auto-migrated by 005 to `meals_enabled=1, mode=INCLUIDO`).
- `meal_plans` (NEW) — catalog: `id, property_id, code, name, surcharge_per_person, surcharge_per_room, applies_to_mode, is_system, is_active, sort_order`. Unique `(property_id, code)`. `SOLO_HABITACION` always auto-seeded.
- `reservations` — extended with `meal_plan_id` (nullable FK) + `breakfast_guests` (nullable Integer).

### Services
- `MealPlanService` (`backend/services/meal_plan_service.py`) — list/get/create/update/soft_delete + `seed_system_plans(property_id, mode)`. System plans (SOLO_HABITACION, auto-seeded CON_DESAYUNO for INCLUIDO) cannot be deleted.
- `SettingsService.get_meals_config` / `set_meals_config` — triggers `seed_system_plans` on enable/mode-change.
- `KitchenReportService.get_daily_report(fecha)` — returns `{enabled, mode, rooms: [...], total_with_breakfast, total_without}`. Date logic: guest slept night of `fecha - 1 day` (so checkout-today IS included, checkin-today is NOT).
- `DocumentService.generate_kitchen_report_pdf(fecha)` — saves to `backend/hotel/Reportes_Cocina/cocina_YYYYMMDD.pdf`.
- `PricingService.calculate_price()` — new optional `meal_plan_id` + `breakfast_guests` args. Surcharge injected between season modifier and final rounding. INCLUIDO plans (surcharge=0) are a no-op → no modifier row added.

### API endpoints
- `GET /api/v1/settings/meals-config` — public (read-only)
- `PUT /api/v1/settings/meals-config` — admin only; seeds plans on enable
- `GET/POST/PUT/DELETE /api/v1/meal-plans` — read any auth, writes admin-only
- `GET /api/v1/reportes/cocina?fecha=YYYY-MM-DD` — admin/recepcion/supervisor/gerencia/**cocina**; default `fecha`=mañana
- `GET /api/v1/reportes/cocina/pdf?fecha=YYYY-MM-DD` — same roles, returns `FileResponse`

### Cocina role
New role `cocina` (read-only) — can access only `/api/v1/reportes/cocina*`. Other endpoints' `require_role()` whitelists unchanged, so cocina users hit 403 everywhere else. No DB migration needed — `require_role` accepts any role string.

### Frontend
- **PC config**: `09_🔧_Configuracion.py` gains a 3-step "Configuración de Comidas" section (toggle → mode → plans editor). New `94_👨‍🍳_Cocina.py` page with date picker (default: tomorrow), metric cards, detail table, CSV + PDF export. Shows "Servicio no habilitado" one-liner when disabled.
- **PC reservation form** (`tab_reserva.py`, v1.10.0-dev meal-plan UI fix): "🍽️ Plan de comidas" section between Selección de Habitaciones and Precio Dinámico. Lives **outside `st.form`** so the price recalculates on every change. Renders only when `meals_enabled=true && mode != INCLUIDO`. Plan dropdown + `breakfast_guests` `number_input` capped by `sum(selected room max_capacity)` (defaults to 10 when no room is selected). Cached helpers `get_meals_config()` + `get_meal_plans(mode_filter)` in `frontend_pc/helpers/data_fetchers.py` (TTL 30s). `ReservationService.get_reservation` now returns `meal_plan_id` + `breakfast_guests` so edit-mode pre-fills the section.
- **Mobile**: new `/dashboard/meals/page.tsx` (read-only; Hoy/Mañana toggle). Dashboard tile "Cocina — Desayunos hoy: N" conditionally renders only when `meals_enabled=true`. Reservation form conditionally shows plan selector + breakfast_guests input when mode ≠ INCLUIDO. Input has `inputMode="numeric"` + `pattern="[0-9]*"` + `onFocus={(e)=>e.currentTarget.select()}` so typing replaces the value cleanly on touch keyboards. `max` is dynamic per-room-cap with inline Spanish error + auto-shrink via `useEffect` when the cap drops below the current value.

### Critical gotchas
- **Never show meal UI when `meals_enabled=false`.** Every mobile surface must check `getMealsConfig().meals_enabled` before rendering. Every PC page must check `get_meals_config()['meals_enabled']`. Every backend path that doesn't check this flag risks leaking "0 desayunos" widgets to hotels that don't serve meals.
- **Kitchen date logic: night-of-(D-1)**, not "is staying on D". A guest checking in on D is NOT eating breakfast on D. A guest checking out on D IS. `KitchenReportService.get_daily_report` encodes this — don't re-invent it.
- **`breakfast_guests` capacity guard** (v1.10.0-dev): `ReservationService.create_reservations` rejects `breakfast_guests > sum(rooms.custom_capacity ?? category.max_capacity)` with a Spanish `ValueError("Cantidad de huéspedes para comidas (X) excede la capacidad total de las habitaciones seleccionadas (N).")`. Defense-in-depth: PC + mobile already cap client-side, but scripts/OTA bridges can bypass UI. Test: `test_meal_plan_reservation.py::TestBreakfastGuestsCapacityValidation`.
- **Business-rule errors must surface as 400 + Spanish detail** (v1.10.0-dev fix): `api/v1/endpoints/reservations.py::create_reservation` catches `ValueError` and re-raises as `HTTPException(400, detail=str(e))` BEFORE the generic `except Exception` swallows it as 500 + "Error al crear la reserva. Intente de nuevo." Same pattern needed for any new endpoint that calls a service raising business `ValueError`. Parking overflow also uses `ValueError` (uplifted from bare `Exception` in the same fix). Regression test: `test_reservation_api.py::test_meal_capacity_exceeded_returns_400_with_spanish`.
- **`update_reservation` clears `breakfast_guests` when `meal_plan_id` is set to None** (v1.10.0-dev fix). Otherwise a reservation can end up with "2 guests with breakfast" but no plan attached — kitchen report would over-count.
- **System plans are un-deletable.** `MealPlanService.soft_delete` raises on `is_system=1`. Set `is_active=0` via update if you need to hide one.
- **Legacy `Property.breakfast_included`** is deprecated v1.7 — migration 005 backfills to `meals_enabled=1, mode=INCLUIDO`. Slots 006/007/008 ya tomados (email_log/room_status_log/ai_agent_permissions); removal va a migración `009_*` o posterior. Tracked en ROADMAP.md backlog.

## Master Guest Entity & Buildings (v1.10.0 — Phase 2a)

### Tablas
- `guests` (NEW) — entidad maestra del huésped (una row por persona, persiste a través de múltiples estadías). Distinta de `checkins` (registro per-estadía / ficha). Schema: `id` (Integer auto), `property_id` FK RESTRICT, identidad (`first_name`, `last_name`, `document_type`, `document_number`), contacto (`email`, `phone`), origen (`nationality`, `country`, `city`), metadata (`notes`, `source`, `is_active`), agregados denormalizados (`total_stays`, `total_spent`, `last_visit_at`), timestamps.
- `buildings` (NEW) — edificio/anexo dentro de una property. Schema: `id` String slug (e.g. `los-monges-principal`), `property_id` FK RESTRICT, `name`, `description`, `floors`, `sort_order`, `is_active`. UNIQUE `(property_id, name)`.
- `reservations.guest_id` (NEW Integer FK SET NULL) — link al Guest maestro. Snapshot fields (`guest_name`, `contact_email`) quedan congelados en la reserva.
- `checkins.guest_id` (NEW Integer FK SET NULL) — mismo patrón.
- `rooms.building_id` — promovido de `Column(String)` dead-column a FK real con `ondelete=SET NULL`. Migración 012 seedea "Edificio Principal" por property y backfilla todas las habitaciones.

### Servicios
- **Rename: `GuestService` → `CheckInService`** (en `services/checkin_service.py`). El nombre `GuestService` ahora pertenece a la entidad maestra. Métodos del CheckInService (`register_checkin`, `get_checkin`, `update_checkin`, `search_checkins`, `get_unlinked_reservations`, `get_all_guest_names`, `get_all_billing_profiles`, `get_billing_history`) idénticos.
- `GuestService` (NEW en `services/guest_service.py`) — `create_guest`, `get_guest`, `update_guest`, `list_guests`, `count_guests`, `search_guests`, **`find_or_create_guest`** (smart-match: documento → email → phone → exact name; crea si no hay match), `get_guest_history`, `refresh_aggregates`. Excepción `GuestServiceError`.
- `BuildingService` — `create_building`, `get_building`, `list_buildings` (con `room_count` agregado), `update_building`. Excepción `BuildingServiceError`.

### API endpoints
- `GET /api/v1/huespedes/search?q=&limit=` — autocomplete (mín. 2 chars). Roles: admin/supervisor/gerencia/recepcion/recepcionista.
- `GET /api/v1/huespedes` — listado paginado (`{items, total, skip, limit}`).
- `POST /api/v1/huespedes` — crear (mismos roles).
- `GET /api/v1/huespedes/{id}` — detalle.
- `PUT /api/v1/huespedes/{id}` — actualizar.
- `GET /api/v1/huespedes/{id}/history` — historial completo + agregados.
- `GET /api/v1/buildings` — listar (todos los roles operacionales).
- `POST /api/v1/buildings` — crear (admin only).
- `PUT /api/v1/buildings/{id}` — actualizar (admin only).
- `/api/v1/guests/*` LEGACY URL — sigue gestionando CheckIns, NO se rompe (mobile + PC dependen). Internamente ahora usa `CheckInService`.

### Wire al flujo de reserva
- `ReservationService.create_reservations` resuelve el Guest **una vez** por booking (vía `find_or_create_guest`) y enlaza `guest_id` en cada reserva creada. Best-effort: si la resolución falla, la reserva sigue sin Guest.
- `CheckInService.register_checkin` también enlaza al Guest maestro vía `_try_link_guest`.

### Frontend
- **PC**: nueva página `91_👥_Huespedes.py` (búsqueda + listado paginado + detalle editable + tabs Datos/Historial). En `98_🏠_Admin_Habitaciones.py`: selector "🏢 Filtrar por edificio" arriba de tabs (cuando hay >1 edificio) y expander "Gestionar edificios" admin-only para CRUD. Tabla de inventario suma columna "Edificio".
- **Mobile**: nuevo `frontend_mobile/src/services/guests.ts` (`getGuest`, `getGuestHistory`, `searchGuests`). En `/dashboard/calendar/[id]`: badge "N estadías previas" / "Primera visita" en sección Huésped. Tap expande historial inline.
- **PC `tab_reserva.py`**: import switched de `GuestService` → `CheckInService` para el dropdown de nombres existentes (no breaking change para el operador).

### Migraciones
- **011_guests_table.py**: crea `guests`, agrega `guest_id` a `reservations` y `checkins`, autopobla en cuatro pasos (documento → nombre → backfill reservations.guest_id + checkins.guest_id → refresca agregados). Resultado en dev DB: 107 reservas + 52 checkins → 96 guests, 100% linkeados.
- **012_buildings_table.py**: crea `buildings`, seedea `<property_id>-principal` "Edificio Principal" por property, backfillea `rooms.building_id` donde NULL.

### Phase 2a-ext — Guest Domain Completion (v1.10.0)

#### Tablas nuevas
- `guests.birth_date` (NEW Date) — hook para futura automatización de saludos de cumpleaños (ver ROADMAP.md). `find_or_create_guest` y `_augment_guest_if_empty` lo aceptan/propagan ("fill empty, never overwrite").
- `billing_profiles` (NEW) — perfiles de facturación reutilizables por huésped. Schema: `id` (Integer), `guest_id` FK CASCADE, `property_id` FK RESTRICT, `label`, `is_default` (Boolean), `tax_id_type` (RUC | CI | CUIT | CPF | CNPJ | NIT | …), `tax_id_number`, `business_name`, address fields, `is_active`. UNIQUE no declarado (mismo RUC puede aparecer bajo dos guests legítimamente — corporate + personal).
- `guest_vehicles` (NEW) — vehículos registrados por huésped, máx 5 (enforced en `GuestVehicleService.create_vehicle` → `MAX_VEHICLES_PER_GUEST = 5`). Plate normalizado a uppercase + trim. Soft-deleted no cuenta para el límite.
- `checkin_vehicles` (NEW N:M) — vincula `checkins` ↔ `guest_vehicles` por estadía + `parking_spot` + `key_deposited`. UNIQUE (checkin_id, vehicle_id).
- `checkins.billing_profile_id` (NEW Integer FK SET NULL) — qué perfil se usó para esta estadía. Snapshot fields `checkins.billing_name`/`billing_ruc` se conservan.

#### Servicios nuevos
- `BillingProfileService` — CRUD + `set_default` (clears siblings) + `find_or_create_from_checkin` (priority: tax_id → business_name → create). Excepción `BillingProfileError`.
- `GuestVehicleService` — CRUD + 5-limit enforcement + `search_by_plate` (case-insensitive, exact-then-partial, returns vehicle + guest + active reservation if any) + `link_to_checkin`/`unlink_from_checkin`/`get_checkin_vehicles`. Excepción `GuestVehicleError`.

#### Auto-propagación desde CheckIn (load-bearing)
`CheckInService.register_checkin` y `update_checkin` ahora corren **dos hooks adicionales** después del guest-link:
- `_propagate_billing_to_profile`: si la ficha tiene billing_name/billing_ruc + guest_id + sin billing_profile_id explícito → crea/encuentra BillingProfile y linkea.
- `_propagate_vehicle_to_master`: si la ficha tiene vehicle_plate + guest_id → crea/encuentra GuestVehicle y crea CheckinVehicle link.
Best-effort: errores se loguean y se ignoran (la ficha es load-bearing, los side effects no).

#### Auto-propagación desde Reserva (load-bearing) — v1.10.0-dev fix
Pre-fix la chapa solo se propagaba al catálogo maestro al hacer check-in. Eso dejaba el lookup `search_by_plate` (y el futuro OCR en la entrada) ciego para reservas hechas con anticipación. Ahora `ReservationService.create_reservations` corre **el mismo hook** después de refrescar agregados del Guest:

- Si la reserva trae `vehicle_plate` + Guest resuelto → llama `GuestVehicleService.create_vehicle` con `plate_number` + `model` + `color`. La service-layer dedupea por (guest, plate); si el vehículo ya existe re-usa.
- Color sigue patrón "fill empty, never overwrite": si el master tiene `color=None` y la reserva trae color → backfill. Si ya tiene color, no se pisa.
- Si FEAT-LINK-01 dispara y crea un CheckIn auto-vinculado → además crea el `CheckinVehicle` link explícitamente (el flujo de `register_checkin` no aplica acá porque el CheckIn lo arma `ReservationService` inline).
- Best-effort: 5-vehicle limit overflow / DB errors se loguean (`logger.warning`) y se ignoran. La reserva ya commitió y es load-bearing.

**Schema**: `ReservationCreate.vehicle_color: Optional[str]` y `CheckInCreate.vehicle_color: Optional[str]` son passthrough — NO se almacenan en `reservations` ni `checkins` (evita 2 ALTER TABLE migrations). Color vive canónicamente en `guest_vehicles.color`.

**UI**: campo "Color del Vehículo" agregado en PC (`tab_reserva.py`, `tab_checkin.py`) y mobile (`GuestForm.tsx`) — solo se muestra cuando hay parking marcado.

Tests: `test_guest_vehicles.py::TestReservationPropagatesVehicle` (6 tests cubren propagación + color + dedup + 5-limit overflow + color backfill).

#### API endpoints
- `GET/POST/PUT/DELETE /api/v1/huespedes/{id}/billing[/{profile_id}]` (admin/supervisor/gerencia/recepcion/recepcionista para todo).
- `POST /api/v1/huespedes/{id}/billing/{profile_id}/default` — marcar predeterminado.
- `GET/POST/PUT/DELETE /api/v1/huespedes/{id}/vehicles[/{vehicle_id}]`.
- `GET /api/v1/vehicles/search?plate=ABC` — "¿de quién es este auto?" + futuro OCR. Retorna vehicle + guest + active_reservation (404 si no hay match).
- `GET/POST/DELETE /api/v1/checkins/{checkin_id}/vehicles[/{vehicle_id}]` — per-stay link con parking_spot/key_deposited.

#### AI Tool nuevo (#20)
- `buscar_vehiculo(plate)` — busca por chapa, devuelve dueño + reserva activa/próxima. Mapeada a `can_view_guests`. Total tools = 20.

#### Migración 013
- Crea las 3 tablas + agrega `birth_date` y `billing_profile_id`.
- Auto-pobla desde data legacy: por cada checkin con `billing_name`/`billing_ruc` → 1 BillingProfile (primer perfil por guest = default), por cada checkin con `vehicle_plate` → 1 GuestVehicle + 1 CheckinVehicle.
- Resultado en dev DB: 27 BillingProfiles + 18 GuestVehicles + 18 CheckinVehicles + 27 checkins back-filled con billing_profile_id.
- Idempotente: re-run no duplica (skip si tablas tienen rows).

#### UI
- **PC `91_👥_Huespedes.py`**: tab "Datos" agrega "🎂 Fecha de nacimiento". Dos tabs nuevos: "🧾 Facturación" (lista perfiles, marcar predet., editar/eliminar, agregar) y "🚗 Vehículos" (lista, agregar con cap visible "N/5", editar/eliminar).
- **PC `tab_checkin.py`**: captions agregadas explicando que los datos de Facturación + Vehículo se replican automáticamente al huésped maestro (formularios viejos sin cambios — service-layer hace el trabajo). El dropdown rico (perfil predet. → preselect) queda como follow-up UX.

#### Critical gotchas
- **5-vehicle limit**: hard-enforced en service. Re-intento en migración: legacy data con >5 plates por guest se trunca silenciosamente al límite.
- **Plate normalisation**: el validator de `GuestVehicleCreate` y `_norm_plate` en service uppercase + trim. Nunca comparar plates raw.
- **`billing_ruc` validator strip**: `CheckInCreate.billing_ruc` solo permite dígitos + guiones (RUC paraguayo XXXXXXXX-X). Si testing con valores tipo "MY-RUC" → quedan "--" después del strip. Usar números reales (e.g. "80012345-6").
- **BillingProfile no es UNIQUE por (guest, tax_id)**: un mismo huésped puede tener dos perfiles con el mismo RUC (e.g. personal + empresa). El de-dup lo hace el service en `find_or_create_from_checkin`, no la base.
- **Snapshot pattern preservado** (igual que Phase 2a): `checkins.billing_name`/`billing_ruc`/`vehicle_model`/`vehicle_plate` siguen como snapshots frozen-at-registration. Las nuevas tablas son la versión "viva".

#### Próximo slot de migración: `014_*.py`.

### Critical gotchas
- **NUNCA mezclar GuestService y CheckInService**. `from services import GuestService` ahora trae la entidad maestra (Phase 2a). `from services import CheckInService` trae las fichas (renombrada). Cualquier import viejo que esperaba CheckIn methods en GuestService falla en runtime con `AttributeError: 'GuestService' has no attribute 'register_checkin'`. Los 7 sitios afectados ya están actualizados; nuevos sitios deben elegir el correcto según concepto.
- **Snapshot pattern preservado**: `reservations.guest_name`, `reservations.contact_email`, `checkins.last_name`/`first_name` siguen como valores frozen-at-creation. El Guest es la versión "viva". No replicar `find_or_create_guest`/`update_guest` en cada lugar — solo en el flujo donde el dato cambia.
- **`find_or_create_guest` es best-effort**: si todos los inputs son blancos (sin nombre/apellido/doc/email/phone), retorna `None` en vez de crear un Guest vacío. El caller debe tratar `None` como "no se pudo enlazar" — la reserva sigue válida con `guest_id=NULL`.
- **Endpoints en español `/huespedes/`**: el path `/api/v1/guests/*` ya estaba ocupado por endpoints de CheckIn (mobile + PC dependen). Spanish path para entidad maestra.
- **`Property.slug` ahora es UNIQUE en el modelo** (preparación SaaS). Backfill de NULL → `property.id` queda para Phase 2b junto con la promoción a NOT NULL.
- **3 FKs lógicas promovidas en `reservations`**: `category_id`, `client_type_id`, `contract_id` ahora son FKs reales con `ondelete=SET NULL`. Tests que crean reservas vía `ReservationService.create_reservations` ahora requieren `seed_client_types` (incluido automáticamente en `seed_rooms` desde Phase 2a).
- **Próximo slot de migración: `013_*.py`**.

### Guest-flow architecture (Phase 2a Bug #2 fix — single entry point)

Toda creación o referencia a un huésped pasa por **un único punto**: `GuestService.find_or_create_guest`. Esto reemplaza ~5 paths divergentes que coexistían pre-Phase 2a (cada uno con su propia fuzzy logic, generando duplicates).

**Reglas:**

1. **`reservations.guest_id` siempre se setea — explícito o vía `find_or_create_guest`.**
   - PC + mobile: el dropdown / autocomplete envía `ReservationCreate.guest_id`. Si está presente, el service lo valida (existe + property_id correcto + activo) y lo usa directo. Si la validación falla, fallback transparente a `find_or_create_guest`.
   - OTA / scripts / manual entry sin dropdown: `guest_id=None` → fallback a `find_or_create_guest` por nombre/doc/email.
   - Si todo falla, `guest_id` queda NULL (best-effort, no rompe la reserva).

2. **`checkins.guest_id` se setea automáticamente.**
   - `CheckInService.register_checkin` llama `_try_link_guest` (que delega en `find_or_create_guest`).
   - `ReservationService.create_reservations` (cuando auto-crea el CheckIn vía FEAT-LINK-01) hereda el mismo `guest_id` de la reserva — no doble resolución.

3. **"Fill empty, never overwrite"**: cuando `find_or_create_guest` matchea un Guest existente, propaga campos NUEVOS desde el form al master (email, phone, nationality, country) PERO solo donde el master tiene blank. Nunca pisa data existente. Mismo patrón en `_augment_guest_from_checkin` (cuando se actualiza una ficha).

4. **Snapshot freeze (intencional)**: `update_reservation` NO re-linkea `guest_id`. El nombre que aparece en la reserva (`guest_name`) es la foto al momento de la booking. Si alguien edita la reserva, el snapshot puede divergir del Guest "vivo" — ese es el diseño. Para cambiar de huésped, se cancela y re-bookea.

5. **Dropdown labels limpios**: `/api/v1/huespedes/dropdown` retorna `"Apellido, Nombre — Doc XXXX"` sin parens embebidos (Bug #1 cleanup). El PC `tab_reserva.py` y mobile `GuestForm.tsx` usan esta misma fuente.

**UX clarity** (single source of truth — la respuesta es siempre obvia):
- "¿Hacer una reserva?" → huésped se crea/encuentra automáticamente (dropdown / autocomplete + fallback)
- "¿Hacer un check-in?" → mismo huésped enlazado, master se enriquece con datos nuevos
- "¿Agregar manualmente?" → página Huéspedes (con detección de duplicados)
- "¿Editar info de huésped?" → página Huéspedes (snapshots de reservas viejas no se tocan)

**Removed**:
- `CheckInService.get_all_guest_names` ya no es la fuente del dropdown de reservas. Sigue existiendo para `tab_checkin.py` (billing profiles + ficha edit search), pero el dropdown de "A nombre de" ahora viene del master Guest. `frontend_services/cache_service.get_all_guest_names_cached` sigue funcional pero ahora lee de `GuestService.list_guests_for_dropdown`.

## AI Agent Tools (20 functions in ai_tools.py)

1. `check_availability` — Room availability for date/stay
2. `get_hotel_rates` — Pricing by category
3. `get_today_summary` — Today's occupancy snapshot
4. `search_guest` — Find guest by name/document (CheckIn records)
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
15. `consultar_inventario` — Product stock query; low-stock list or name filter — **v1.6.0**
16. `consumos_habitacion` — Consumos for a reservation/guest/room — **v1.6.0**
17. `reporte_cocina` — Daily breakfast/meal count (or "no habilitado" if disabled) — **v1.7.0**
18. `estado_email_reserva` — Consulta si se envió el correo de una reserva, cuándo, a quién, y total de envíos exitosos/fallidos — **v1.8.0**
19. `buscar_huesped_historial` — Busca por nombre/doc/email/teléfono en la **entidad maestra Guest** y devuelve estadías previas, total gastado, promedio, últimas 5 reservas. Distinto de `search_guest` (que busca en CheckIn). Mapeada a `can_view_guests`. — **v1.10.0**
20. `buscar_vehiculo` — Busca un vehículo por chapa (case-insensitive, exact-then-partial). Retorna dueño + reserva activa o próxima si existe. Mapeada a `can_view_guests`. Pensado para "¿de quién es el auto blanco?" + futuro OCR en la entrada. — **v1.10.0 Phase 2a-ext**

## Email Sending (v1.8.0 — Phase 5)

### Tables
- `email_log` (NEW) — append-only audit trail: `id, reserva_id (FK), recipient_email, subject, status (ENVIADO|FALLIDO|PENDIENTE), error_message, sent_at, sent_by (FK users), created_at`. Indexes on reserva_id, status, sent_at.
- `system_settings` — usado para SMTP config (key/value): `smtp_host`, `smtp_port`, `smtp_username`, `smtp_password_encrypted`, `smtp_from_name`, `smtp_from_email`, `smtp_enabled`, `email_body_template`. Password se almacena encriptada (Fernet).
- `reservations.contact_email` ya existía — se persiste cuando un envío usa override y el guest no tenía email.

### Encryption
- Helpers `encrypt_secret`/`decrypt_secret` en `backend/api/core/security.py` usan `cryptography.fernet.Fernet` con clave derivada de `SECRET_KEY` via PBKDF2HMAC-SHA256 (200k iterations, salt fijo).
- **Importante**: si rotás `SECRET_KEY`, los passwords SMTP encriptados se vuelven ilegibles → admin debe re-ingresar.

### Business rules
- Envío async via `fastapi.BackgroundTasks` — endpoint responde 202 inmediato, send corre en background con sesión propia (`session_factory()`).
- PDF se **regenera siempre** antes de enviar via `DocumentService.generate_reservation_pdf()` (evita enviar datos obsoletos).
- Rate limit: **3 envíos por reserva por hora**, cuenta SOLO `status='ENVIADO'` (admin puede debuggear SMTP sin auto-bloqueo). 4to → 429 + mensaje en español.
- Email override en body: si guest no tenía email → persiste en `reservations.contact_email`; si ya tenía email distinto → NO sobrescribe.
- Body template usa `str.format_map()` con `{nombre_huesped}` y `{nombre_hotel}` (placeholders desconocidos quedan literales, no crashean).
- MIME usa `email.message.EmailMessage` con `charset='utf-8'` explícito (acentos/ñ).
- Fallo de envío → `logger.error()` que dispara Discord alert via `DiscordWebhookHandler` automático.

### Services
- `EmailService` (`backend/services/email_service.py`) — `prepare_send`, `send_async`, `send_test_email`, `get_email_log`, `_check_rate_limit`, `_render_body`, `_build_mime`, `_send_smtp`. Excepción custom `EmailError`.
- `SettingsService.get_smtp_config(include_password=True)` / `set_smtp_config(...)` — encripta/desencripta password automáticamente.

### API endpoints
- `GET /api/v1/settings/email` — config SMTP actual (admin only). Password NUNCA expuesta — solo `smtp_password_set: bool`.
- `PUT /api/v1/settings/email` — guardar config SMTP (admin only). Si `smtp_password=null/empty`, preserva la existente.
- `POST /api/v1/settings/email/test` — envía email de prueba sincrónico (admin only). Devuelve `{success, message}`.
- `POST /api/v1/email/reserva/{id}/enviar` — encolar envío (admin/recepcion/recepcionista/supervisor/gerencia). Body opcional `{email}` para override. Retorna 202 + `email_log_id`.
- `GET /api/v1/email/reserva/{id}/historial` — lista de email_log ordenado DESC por created_at (mismos roles).

### Permissions
| Action | Admin | Recepcion / Recepcionista / Supervisor / Gerencia | Cocina |
|---|---|---|---|
| GET/PUT `/settings/email`, POST `/settings/email/test` | ✅ | ❌ 403 | ❌ 403 |
| POST `/email/reserva/{id}/enviar`, GET `/historial` | ✅ | ✅ | ❌ 403 |

### Frontend
- **PC**: sección "📧 Configuración de Correo" en `09_🔧_Configuracion.py` (form host/port/user/password type=password/from_name/from_email/toggle/template + botón "Enviar email de prueba" fuera del form). Botón "📧 Enviar correo" en `tab_reserva.py` modo edit (disabled si reserva nueva). Tab "📧 Historial de Emails" en `97_📄_Documentos_Hotel.py` con filtros fecha/status + export CSV (fuera de `st.form`).
- **Mobile**: `services/email.ts` (`sendReservationEmail`, `getEmailHistory`). `components/email/EnviarEmailModal.tsx` siguiendo patrón de `RegistrarPagoModal`. Botón "📧 Enviar por correo" en `app/dashboard/calendar/[id]/page.tsx` entre folio y Registrar Pago. Caption "Último envío: ..." debajo del botón. Toast verde de éxito / rojo de error.

### Critical gotchas
- **Token PC `api_token` vs `access_token`**: bug recurrente (BUG-TOKEN-PC-01, BUG-TOKEN-SETTINGS, también en `94_Cocina.py` resuelto 2026-04-21). Toda página PC nueva DEBE usar `st.session_state.get("api_token")` para el JWT — NO `access_token`. `app.py:82` lo guarda bajo `api_token`.
- **`cryptography` debe instalarse en AMBOS Python envs** (hybrid monolith). Backend usa `C:\Python314`, PC usa `A:\Miniconda\envs\hotel_munich`. Si falta en uno, login PC falla con `No module named 'cryptography'`.
- **TZ consistency en rate-limit**: `email_log.created_at`/`sent_at` se guardan con `datetime.now()` (local). El query de rate limit usa `datetime.now() - timedelta(hours=1)` (también local). NO mezclar con `datetime('now')` de SQLite (UTC) — falla silenciosamente cuando CI corre en otra TZ.
- **Background task abre sesión propia**: `send_async(log_id)` NO reusa la `db` del endpoint (ya cerrada). Usa `SessionLocal()` directo y try/finally garantiza transición PENDIENTE → ENVIADO/FALLIDO incluso en crash.
- **Discord alerts**: solo para fallos de infra (SMTP caído, PDF gen falla). NO para errores de validación del usuario (esos son 400/422/429 con mensaje en español).
- **`AIAgentPermission` (database.py)** ahora ES feature activa desde v1.9.0 (Phase 6). No volver a la nota previa de "andamio intencional". Ver sección "AI Agent Permissions (v1.9.0 — Phase 6)" más abajo.

## Room Status Audit Log (v1.9.0 — Phase 6)

### Tabla
- `room_status_log` (NEW) — append-only audit trail: `id, room_id (FK), previous_status, new_status, changed_by (username), reason, changed_at`. Indexes en `room_id` y `changed_at`.

### Comportamiento
- Cada `PATCH /api/v1/rooms/{id}/status` agrega automáticamente una fila — la lógica vive en el endpoint mismo (no servicio separado, es inserción directa via SQLAlchemy).
- `previous_status` es nullable porque la primera vez que una habitación tiene un cambio puede no tener un estado previo conocido.
- `changed_by` guarda el `username` (consistente con `room.status_changed_by` que ya usaba el patrón). NO un FK a `users.id` — ver gotcha más abajo.
- Migración `007_room_status_log.py` tiene drop+recreate idempotente para la tabla phantom que dejaba `migrate_monges.py` (eliminado en v1.9.0).

### API endpoints
- `PATCH /api/v1/rooms/{id}/status` — admin/supervisor (sin cambio de permisos; ahora también escribe el log).
- `GET /api/v1/rooms/{id}/status-log?limit=50` — admin/supervisor/recepcion/recepcionista/gerencia. Devuelve historial DESC por `changed_at`.

### Frontend
- **PC**: expander "📋 Historial de cambios de estado" en `98_🏠_Admin_Habitaciones.py` debajo del botón Eliminar (visible al seleccionar una habitación).
- No mobile UI — es herramienta de admin operacional.

### Gotcha
- `changed_by VARCHAR` (username), NO `Integer FK users.id`. Sigue el patrón de `room.status_changed_by` y `email_log.sent_by` (también username). Si un usuario cambia su username, los logs históricos quedan con el username viejo — comportamiento aceptado (auditoría debe reflejar quién hizo la acción al momento, no la identidad actual).

## AI Agent Permissions (v1.9.0 — Phase 6)

### Tabla
- `ai_agent_permissions` (existía como modelo desde v1.0, activada en v1.9 vía migración 008): `id, property_id, role, can_view_reservations, can_create_reservations, can_modify_reservations, can_cancel_reservations, can_view_guests, can_modify_guests, can_view_rooms, can_modify_rooms, can_modify_room_status, can_view_prices, can_modify_prices, can_view_reports, can_export_data, can_modify_settings, requires_confirmation, created_at, updated_at`. Una row por (property_id, role) — `property_id` actualmente nullable (single-tenant).
- 14 columnas booleanas. Hoy v1.9 sólo 5 están realmente activas (las view_*); las demás están reservadas para tools de modificación futuras (ningún tool de v1.9 escribe).

### Servicio
- `AIAgentPermissionService` (`backend/services/ai_agent_permission_service.py`) — `get_or_create`, `list_all`, `update_permissions` (con safety anti-lockout para admin/supervisor/gerencia), `get_allowed_tools`.
- Constantes exportadas: `PERMISSION_COLUMNS`, `TOOL_PERMISSION_MAP`, `DEFAULT_PERMISSIONS_BY_ROLE`.
- Sigue convención `@with_db` con `db: Session` como PRIMER parámetro posicional.

### Tool ↔ permission mapping
Las 18 tools del agente se mapean a 5 columnas:
| Permiso | Tools controladas |
|---|---|
| can_view_reservations | search_reservation, get_reservations_report, get_today_summary, get_occupancy_for_month |
| can_view_guests | search_guest |
| can_view_rooms | check_availability |
| can_view_prices | get_hotel_rates, calculate_price |
| can_view_reports | get_room_performance, get_booking_sources, get_parking_status, get_revenue_summary, consultar_caja, resumen_ingresos_por_metodo, consultar_inventario, consumos_habitacion, reporte_cocina, estado_email_reserva |

Tools nuevos que no estén en `TOOL_PERMISSION_MAP` quedan **siempre permitidos** (defensive default — agregar al mapa antes del deploy).

### Defaults seedeados por migración 008
| Rol | Defaults |
|---|---|
| admin / supervisor / gerencia | TODO en true |
| recepcion / recepcionista | view_reservations, view_guests, view_rooms, view_prices = true; resto false (incluyendo view_reports → bloquea las 10 tools de reportes) |
| cocina | TODO en false (cocina usa la página dedicada, no el agente) |

### Middleware en agent.py
- `filter_tools_for_role(role)` filtra `TOOLS_LIST` antes de pasarlo a Gemini. Cuando una tool está bloqueada, Gemini simplemente no la conoce → responde naturalmente "no tengo herramienta para eso" sin necesidad de mensajes de error custom.
- `query_agent` endpoint pasa `current_user.role` al `process_query()`.

### API endpoints
- `GET /api/v1/admin/ai-permissions` — listado completo (admin only). Auto-seedea defaults la primera vez.
- `GET /api/v1/admin/ai-permissions/{role}` — detalle (admin only).
- `PUT /api/v1/admin/ai-permissions/{role}` — partial update (admin only). Body: cualquier subset de las 14 columnas booleanas.
- `GET /api/v1/admin/ai-permissions/{role}/allowed-tools` — diagnóstico, devuelve lista de tools + el `tool_permission_map` completo.

### Frontend PC
- Página nueva `93_🤖_Permisos_IA.py` (admin only). Por cada rol: expander con 14 checkboxes (uno por permiso) + tooltip que muestra qué tools controla. Form per-rol, partial update vía diff (sólo manda lo que cambió). Panel de referencia al final con mapeo agrupado por permiso.

### Critical gotchas
- **Defensive default**: tools sin entry en `TOOL_PERMISSION_MAP` son SIEMPRE permitidas para todos los roles. Agregar al mapa cuando se sume una tool nueva, o quedará accesible para cocina (etc).
- **Safety anti-lockout**: `update_permissions` lanza `AIAgentPermissionError` si admin/supervisor/gerencia quedan con TODO en false (bloquearía el agente para roles de gestión). Otros roles sí pueden ser totalmente bloqueados.
- **Convención `@with_db`**: `db: Session` debe ser el PRIMER parámetro posicional, NO kwarg con default. El decorador inserta db como primer arg en modo Streamlit. Los callers pueden mezclar `db=db, role=...` (todo kwargs) sin problema.
- **`requires_confirmation` es columna sin uso activo en v1.9**. Reservada para feature futura donde el agente "sugiera y confirme" antes de acciones destructivas (cuando se agreguen tools de modificación).

## Type Harmonization (v1.10.0 — Phase 2b)

Última fase de cleanup del schema SQLite antes del cutover a Postgres (Phase 3+). Toca 4 dimensiones:

### Boolean-as-Integer → Boolean (27 columnas)

Reemplazadas todas las columnas que conceptualmente eran booleanas pero estaban declaradas `Column(Integer, default=0/1)`:
- `room_categories.active`, `rooms.active`, `client_types.active`/`requires_contract`, `client_contracts.active`, `pricing_seasons.active`, `properties.active`/`parking_available`/`meals_enabled`, `ical_feeds.sync_enabled`, `meal_plans.is_system`/`is_active`, `migration_history.success`
- Las 14 `AIAgentPermission.can_*` + `requires_confirmation`

SQLite almacena Boolean como INTEGER bajo el capó, así que data existente (`0`/`1`) round-trippea transparente via SQLAlchemy. Lectura desde Python ahora devuelve `bool` real (no `int`). En Postgres se vuelve `BOOLEAN` nativo.

### JSON-in-String → JSON (5 columnas)

`Column(String) # JSON` → `Column(JSON)`. Auto-encode/decode al guardar/leer:
- `room_categories.bed_configuration`, `room_categories.amenities`
- `reservations.price_breakdown`
- `pricing_seasons.applies_to_categories`
- `price_calculations.calculation_details`

**Importante para callers**: ahora pasás un `dict`/`list` directamente — NO `json.dumps()` previo. La service-layer `ReservationService.create_reservations` ya está actualizada (antes hacía `breakdown = json.dumps(...)`, ahora pasa el dict crudo). Los DTOs de respuesta usan `Optional[Any]` para no forzar el shape a string.

En Postgres estos columns se vuelven `JSONB` indexable.

### `properties.breakfast_included` REMOVIDA

Deprecated desde v1.7. SQLite 3.35+ soporta `ALTER TABLE ... DROP COLUMN` nativo — migration 014 ejecuta el DROP. Reemplazo: combinación `meals_enabled` + `meal_inclusion_mode == "INCLUIDO"`.

**Backward compat de API**: `GET /api/v1/settings/property-settings` sigue devolviendo el campo `breakfast_included` en su body. Ahora se deriva de `meals_enabled && mode == 'INCLUIDO'`. El mobile success banner (`"🍳 Desayuno incluido / no incluido"`) sigue funcionando sin cambios.

### `checkins.created_at` Date → DateTime

Captura hora de ingreso, no solo fecha. Data existente (`'YYYY-MM-DD'` strings) sigue leyéndose correctamente (SQLAlchemy parsea como datetime a 00:00:00). Filas nuevas obtienen full timestamp.

### `Property.slug` NOT NULL

Backfill `WHERE slug IS NULL → slug = id` en migration 014. Model promovido a `nullable=False`. Sirve como URL canónica de tenant cuando llegue el SaaS layer (`app.hotel.com/los-monges/`). En SQLite la enforcement del NOT NULL llega en fresh `init_db()` / Postgres cutover.

### 8 `property_id` columnas promovidas a FK real

`room_categories`, `rooms`, `reservations`, `system_settings`, `client_types`, `client_contracts`, `pricing_seasons`, `price_calculations` — todas pasan de `Column(String, nullable=False)` a `Column(String, ForeignKey("properties.id", ondelete="RESTRICT"))`. Option A model-only (Phase 1 convention): la enforcement llega en fresh `init_db()` o Postgres cutover. Migration 015 audita orphans antes de la promoción (0 encontrados en dev).

### Retention script

`scripts/cleanup_retention.py` — idempotente, dry-run capable. Reglas:
- `price_calculations`: borra rows con `reservation_id IS NULL` más viejas que 90 días (default). Rationale: rows con `reservation_id` son audit del precio aplicado; rows sin reservation son previews/calculator hits.
- `session_logs`: borra rows con `login_time` más viejo que 365 días (default).

Ejecutar manual o vía cron:
```bash
python scripts/cleanup_retention.py              # default
python scripts/cleanup_retention.py --dry-run    # reporta sin borrar
python scripts/cleanup_retention.py --price-days 60 --session-days 180
```

No toca el schema. No requiere downtime. Safe en cualquier momento.

### Critical gotchas Phase 2b
- **JSON callers**: si ves código viejo haciendo `json.dumps(some_dict)` antes de asignar a una columna JSON — quítalo. SQLAlchemy hace doble encode si pasás un string a una columna JSON.
- **DTOs con JSON fields**: usar `Optional[Any]` en pydantic, no `Optional[str]`. Pydantic rechazaría una lista/dict si el DTO la declara como str.
- **PRAGMA foreign_keys=ON contamination en tests**: `test_db_constraints.py::_enable_fk` activa FK en la connection del StaticPool, y como StaticPool reusa la misma connection, **el PRAGMA persiste para tests subsiguientes**. Test funcions que insertan en tablas con FK a `properties.id` ahora deben depender de `seed_property` (se hizo para `test_settings_service.py` + `test_settings_api.py` en Phase 2b).
- **`amenities=[]` en fixtures**, NO `amenities="[]"`. Después de Phase 2b las columnas JSON aceptan list/dict directo; pasar string a JSON column causa double-encode.
- **Migración 014 + 015 ya aplicadas en dev DB** (resultado: drop column breakfast_included + 0 orphans en property_id audits). Próximo slot: `016_*.py` ya ocupado por Phase 2c — siguiente disponible `017_*.py`.
- **breakfast_included en código frontend**: el mobile sigue leyendo `propertySettings.breakfast_included` — el backend devuelve el valor derivado. Cero cambios necesarios en mobile.

## Multi-vehicle per Reservation (v1.10.0 — Phase 2c)

Una reserva puede llevar **N vehículos** (no solo uno). Cada vehículo consume un lugar de estacionamiento. Soporta dos modos por vehículo:

- **Linked**: `guest_vehicle_id` apunta al catálogo maestro del booker. La recepcionista lo eligió de un dropdown de los vehículos registrados del huésped principal.
- **Quick-add**: `guest_vehicle_id IS NULL`. `plate_number`/`model`/`color` son la fuente de verdad. Para vehículos de acompañantes que NO requieren crear un Guest record (caso típico: segundo auto que llega a las 2 AM).

### Tabla
- `reservation_vehicles` (NEW, migración 016): `id, reservation_id FK reservations CASCADE, guest_vehicle_id FK guest_vehicles SET NULL, plate_number, model, color, is_primary BOOLEAN, notes, created_at`. Index en `(reservation_id)` para render de listado + `(plate_number)` para `search_by_plate` (OCR/futuro).

### Schemas
- `VehicleInput`: `{mode: "linked"|"quick", guest_vehicle_id?, plate_number?, model?, color?, is_primary, notes?}`. Validator rechaza linked sin id y quick sin plate.
- `ReservationCreate.vehicles: List[VehicleInput] = []` — campo opcional. Cuando se provee, **toma precedencia** sobre el path legacy single-vehicle.
- `ReservationVehicleDTO` en el response del endpoint `/reservations/{id}`.

### Reglas de parking (rewrite en `ReservationService.create_reservations`)
- Si `vehicles=[]` (legacy) → 1 lugar por habitación (comportamiento original).
- Si `vehicles=[...]` → **1 lugar por vehículo**, sin importar cantidad de habitaciones. 3 autos = 3 lugares.
- **Cap duro**: una reserva NUNCA puede pedir más vehículos que la capacidad total del hotel (`parking_capacity`). Caso `len(vehicles) > parking_capacity` → `ValueError` → 400 con mensaje en español.
- Overlap check ahora cuenta `reservation_vehicles` reales de las reservas existentes (fallback a 1 lugar por habitación cuando no hay rows — data legacy).

### Back-compat
- Las columnas `reservations.vehicle_plate` / `reservations.vehicle_model` **se preservan**. La fila marcada `is_primary=True` (o índice 0 si ninguna lo está) también escribe su plate/model en estas columnas legacy. Toda la lectura existente (PDFs, calendar views, AI tools, mobile detail page) sigue funcionando sin modificación.
- `_propagate_vehicle_to_master` y el hook de single-vehicle quedan envueltos en `if not data.vehicles:` — corren solo cuando el caller usa el path legacy.

### Search by plate extendido
- `GuestVehicleService.search_by_plate` ahora cae a `reservation_vehicles` si no encuentra match en `guest_vehicles`. Esto permite encontrar quick-add companions pre-arrival (use case OCR futuro). Cuando el match viene de `reservation_vehicles`, `guest` puede ser `None` (no hay Guest maestro registrado) — el AI tool `buscar_vehiculo` ya está guarded.
- Las quick-add vehicles también se promueven best-effort al master `guest_vehicles` bajo el nombre del booker (si hay `guest_id`). Así, la próxima vez la misma chapa aparece como `linked`.

### UI
- **PC `tab_reserva.py`**: expander "🚗 Vehículos adicionales" OUTSIDE el form (Streamlit constraint — el form bloquea estado mutable). El vehículo PRIMARY sigue siendo los campos chapa/modelo/color dentro del form (quick-mode). Los EXTRAS pueden ser quick OR linked (dropdown del catálogo del booker — solo disponible si el guest fue picked del dropdown).
- **Mobile `GuestForm.tsx`**: sección "Vehículos adicionales" dentro del bloque de Parking. **Solo quick-mode** en mobile v1 (typing es más natural en touch que el dropdown linked). Cada extra: chapa/modelo/color + botón ✕. Linked-mode para mobile queda en backlog.

### Critical gotchas
- **`vehicles=[]` es el switch entre paths**. Si el frontend manda `vehicles=[]` o no la incluye → path legacy single-vehicle. Si manda `vehicles=[1 entry]` → path multi-vehicle (incluso para 1 vehículo). Ojo con casos de "auto agregado por error" en el UI que quedan colgando.
- **Primary vehicle siempre se escribe en columnas legacy**. Si pasás 2 vehículos sin `is_primary=True` en ninguno → el de índice 0 gana. Si pasás varios con `is_primary=True` → solo el primero encontrado en ese estado se respeta (no hay validación de "exactamente uno"). Service-side es defensivo, no estricto.
- **FK CASCADE en SQLite tests**: por defecto SQLite no enforce FK. Para tests de cascade hay que `PRAGMA foreign_keys=ON` per-connection. Ver `test_multi_vehicle.py::TestCascadeDelete` para el patrón.
- **`search_by_plate` puede devolver `guest=None`**. Para quick-add companions sin Guest maestro registrado. El AI tool `buscar_vehiculo` ya maneja el None (muestra "sin huésped maestro registrado"). Cualquier caller nuevo del shape debe hacer lo mismo.
- **Quick-add promotion al master es best-effort**. Si el booker ya tiene 5 vehículos registrados (cap de Phase 2a-ext), la promotion se loguea y se ignora — el `reservation_vehicles` row es el record load-bearing. No rompe la reserva.
- **Mobile no soporta linked mode todavía**. Receptionists en mobile siempre tipean la chapa. Promotion automática al master sigue funcionando. Linked mode mobile = backlog futuro.
- **Próximo slot de migración: `017_*.py`** ya usado por Phase 2d (Multi-currency). Siguiente disponible: `018_*.py`.

## Multi-currency Payments (v1.10.0 — Phase 2d)

Cualquier hotel en cualquier país hispanohablante puede operar con N monedas. Cada hotel tiene UNA **moneda base** (todos los totales/saldos/reportes denominados ahí) y N **monedas aceptadas** que el huésped puede usar para pagar. Para el demo en Ciudad del Este (zona triple frontera): PYG base + USD + BRL diarios.

### Modelo conceptual
- `Property.currency` (columna pre-existente, reutilizada) = moneda base de la propiedad.
- `accepted_currencies` (NEW, migración 017) = catálogo per-property de monedas aceptadas + tipos de cambio.
- `transaccion` extendida con `currency_code` + `exchange_rate` + `amount_original`. El campo `amount` SIEMPRE está en moneda base — no cambia su semántica.

### Snapshot pattern
Cuando el receptionist registra un pago en USD:
- `amount_original = 100` (lo que el huésped entregó)
- `currency_code = "USD"` (moneda)
- `exchange_rate = 7500` (tipo de cambio CONGELADO al momento del pago)
- `amount = 750_000` (equivalente en moneda base, persiste para totales/saldos)

Si el admin actualiza el TC después, los reportes históricos NO cambian. Mismo patrón usado para `consumo.unit_price` y `checkin.billing_*`.

### Catálogo
`services/currency_service.py::CURRENCY_CATALOG` — 20 monedas hard-coded (todas hispanas + USD/EUR/GBP). Los hotels seleccionan de este catálogo, no crean nuevas. Para sumar un país nuevo: agregar entry al catálogo y agregar entry a `migration 017::SEED_BY_BASE` si querés seed automático.

### Service
- `CurrencyService.get_base_currency(property_id)` — lee `Property.currency`.
- `CurrencyService.set_base_currency(property_id, new)` — bloqueado si hay transacciones activas en otra base (preserva integridad de reportes históricos).
- `CurrencyService.get_accepted_currencies(property_id, active_only=True)` — lista ordenada por `sort_order`.
- `CurrencyService.add_accepted_currency(property_id, code, rate, sort_order)` — idempotente: si la moneda ya existe, actualiza rate + reactiva.
- `CurrencyService.update_exchange_rate(property_id, code, new_rate)` — rechaza si `code == base` (la base siempre es 1).
- `CurrencyService.remove_accepted_currency(property_id, code)` — soft-deactivate, rechaza si es base.
- `CurrencyService.convert_to_base(amount, code, property_id)` → `{amount_base, exchange_rate, currency_code, amount_original}`. Redondea al `decimal_places` de la moneda BASE (no de la original).
- `CurrencyService.format_amount(amount, code, with_symbol=True)` — convención española: punto miles + coma decimales. PYG `₲ 750.000`, USD `US$ 100,00`, BRL `R$ 1.234,50`.

### Endpoints
- `GET /api/v1/currencies/catalog` — lista read-only de las 20 monedas.
- `GET /api/v1/currencies/base` — moneda base actual.
- `GET /api/v1/currencies?active_only=true` — monedas aceptadas (con rate).
- `POST /api/v1/currencies` (admin) — agregar.
- `PUT /api/v1/currencies/{code}/rate` (admin) — actualizar tipo de cambio.
- `DELETE /api/v1/currencies/{code}` (admin) — desactivar.

### TransaccionService.registrar_pago
Nuevos kwargs `currency_code` + `property_id` (opcionales para back-compat). Si `currency_code` se omite o coincide con base → camino legacy (transaction.currency_code queda NULL). Si difiere → convierte vía CurrencyService y persiste snapshot completo. Errores de conversión se re-elevan como `TransaccionError` → 400 con mensaje en español.

### CajaService.get_session_summary
Agrega `base_currency: str` + `currency_breakdown: list[{currency_code, total_original, total_base, count, exchange_rate}]`. Las transacciones legacy (currency_code NULL) se agrupan bajo la base. Ordenado: base primero, luego alfabético.

### Back-compat
- Transacciones existentes (currency_code IS NULL) son tratadas como "moneda base" por todos los read paths. No hay backfill — el read código sabe interpretar NULL.
- El campo `amount` SIEMPRE está en base — su significado no cambió, solo se hizo explícito.
- Endpoints viejos sin `currency_code` siguen funcionando exactamente como antes (camino legacy).

### UI
- **PC `09_Configuracion.py`**: sección "💱 Monedas" con dropdown de moneda base + tabla de monedas aceptadas (con popovers para editar tasa / desactivar) + expander "+ Agregar nueva moneda" desde catálogo.
- **PC `calendar_render.py` (Registrar Pago)**: dropdown de moneda al inicio + amount input con step adaptativo (PYG 500, USD/BRL 1) + caption con preview en vivo `"💱 Equivale a 750.000 ₲ · TC: 1 USD = 7.500 ₲"`. Default amount = saldo pendiente convertido a la moneda elegida.
- **PC `96_Caja.py`**: sección "💱 Desglose por moneda" debajo del "Esperado en caja" cuando la sesión tiene pagos en más de una moneda o una sola no-base. Muestra cada moneda con monto original + TC + equivalente en base + cantidad de pagos.
- **Mobile `RegistrarPagoModal.tsx`**: pills horizontales con `símbolo + código` para elegir moneda. Step del input = 500 si base es entero, 1 si tiene decimales. Caption verde con preview de conversión. Si solo hay 1 moneda configurada, los pills NO se renderizan (UX sin clutter).

### Critical gotchas
- **`amount` SIEMPRE en base, sin excepción**. Toda la suma de saldos/totales lee `amount`. No iterar sobre `amount_original` para totales — está en monedas mixtas.
- **El tipo de cambio se congela al momento del pago** (`exchange_rate` se copia al row). Cambios posteriores no afectan reportes históricos. Si necesitás re-valorizar (ej. tipo "real" según FX feed), es un análisis SEPARADO — la base de auditoría se queda con el snapshot.
- **`Property.currency` vs columna nueva `base_currency`**: la primera ya existía (default 'PYG'). Reutilizada — NO se creó columna duplicada. La spec inicial pedía `base_currency` nueva; pragmática: usar lo existente.
- **No FX feeds automáticos**. Hotels en zona frontera tienen su propio TC del día — el admin actualiza manualmente via Settings. Auto-FX queda en backlog (requiere API externa + decisión sobre comisión).
- **Cambiar moneda base con transacciones activas está bloqueado**. `CurrencyService.set_base_currency` rechaza con error en español si hay `Transaccion.voided=False`. Cambiar la base re-significa todos los reportes históricos (1 USD = X PYG, ahora 1 USD = X EUR — los totales serían incomparables).
- **Seed migración 017 corre solo una vez por property**. Re-running la migración con `accepted_currencies` ya seedeada → skip. Para resetar un seed: borrar manualmente + re-correr `python scripts/run_migrations.py` (la check de `migration_history` no re-correrá la migración 017 — usar `seed_monges.py` o SQL directo).
- **Mobile NO permite cambiar tipos de cambio**. Toda la mutación es PC-only (admin). Mobile solo lee. Para apertura de hotel a un país nuevo: configurar la base + monedas desde PC primero.
- **Próximo slot de migración: `018_*.py`** ya ocupado por Phase 2e (Hotel-day + early/late check-in). Siguiente disponible: `019_*.py`.

## Hotel-day Logic + Early/Late Check-in/out (v1.10.0 — Phase 2e)

Un "día de hotel" no termina a la medianoche, sino al check-out del día siguiente. La noche del día D sigue vigente hasta `D+1 @ check_out_time`. Un recepcionista a las 02:00 del D+1 sigue trabajando "la noche de D" — debe poder crear una reserva con `check_in_date=D`.

### Utility module
`backend/services/hotel_day.py`:
- `get_current_hotel_day(check_out_time, *, now=None)` — devuelve el día operacional vigente. Acepta `time` o "HH:MM" string. Default 10:00 si no se pasa nada.
- `can_create_reservation_for_date(check_in_date, check_out_time, *, now=None)` — `True` si todavía estamos dentro del hotel-day del `check_in_date` (la noche aún no terminó) o si es futuro.
- `_coerce_time` (helper) acepta `time` / "HH:MM" / "HH:MM:SS" / None y devuelve un `time` válido. Property guarda check_*_time como strings — esta función lo normaliza.
- Constante `DEFAULT_CHECK_OUT_TIME = time(10, 0)` — fallback conservador usado por Pydantic validators y otros callers que no quieren leer la DB.

### Application points
- **Pydantic `ReservationCreate.validate_date_coherence`** (schemas.py): cambió de `if check_in_date < date.today(): reject` a `if not can_create_reservation_for_date(check_in_date): reject`. Mensaje en español: "La fecha de entrada ya pasó (el horario de check-out del día siguiente ya terminó)." Usa el default 10:00 — propiedades con check-out más tarde quedan más permisivas (lo cual es seguro).
- **PC tab_reserva.py** `date_input min_value`: cambió de `date.today()` a `get_current_hotel_day(check_out_time=<from settings>)`. Carga el check-out de la propiedad vía `SettingsService.get_property_settings()`. Si la carga falla → cae al default 10:00.
- **Mobile**: `<input type="date">` en RoomSelection.tsx NO tiene `min` attr → el browser acepta cualquier fecha. El backend validator hace el trabajo de rechazar fechas muy pasadas. Sin cambios mobile necesarios.

### Settings UI
`09_🔧_Configuracion.py` ahora expone una sección "⏰ Horarios del Hotel" con time pickers para `check_in_start` / `check_in_end` / `check_out_time`. Persiste vía nuevo `SettingsService.set_property_hours()`. Validador rechaza `check_in_start >= check_in_end` con mensaje en español. Endpoint: `PUT /api/v1/settings/property-hours` (admin/supervisor/gerencia).

### Early check-in / Late check-out (MVP — Migration 018)
Nuevas columnas en `reservations`:
- `early_checkin BOOLEAN default 0` — guest llega antes del check_in_start.
- `late_checkout BOOLEAN default 0` — guest sale después del check_out_time.
- `late_checkout_time VARCHAR` — "HH:MM" o NULL. Solo se persiste si `late_checkout=True` (el service ignora el value cuando el flag es false — previene stale data).

Nuevas columnas en `properties`:
- `early_checkin_surcharge INTEGER default 0` — en moneda base.
- `late_checkout_surcharge INTEGER default 0` — en moneda base.

UI en PC tab_reserva: checkboxes "Early check-in" + "Late check-out". Cuando late_checkout está marcado, aparece un `time_input` para la hora acordada.

### Critical gotchas
- **`Property.check_*_time` son STRINGS, no `time`**. La columna es `Column(String, default="07:00")`. Cualquier consumer que quiera operar con `time` debe pasar por `_coerce_time` (o `datetime.strptime(value, "%H:%M").time()` inline). Comparar strings como ordenamiento textual funciona por casualidad (HH:MM zero-padded) pero es frágil — usá `time` siempre.
- **El Pydantic validator usa default 10:00, NO consulta la DB**. Pydantic no puede leer DB en class-definition time, y agregar un DB-aware validator complicaría el contrato (validators son síncronos / pure). El validator es conservador: rechaza más rápido de lo que estrictamente debería. El service-layer en `create_reservations` SÍ podría consultar la DB y ser más permisivo — esa es la siguiente iteración si los hoteles con check-out 12:00+ se quejan. Para defecto 10:00 es correcto.
- **Availability blocking de late checkout está DEFERIDO a Phase 6.5**. `late_checkout_time` se guarda pero el overlap check en `create_reservations` NO lo consulta. Una reserva con late check-out hasta 14:00 NO bloquea otra reserva entrando a la misma habitación a las 14:00. Documentado en ROADMAP.md backlog Phase 6.5.
- **Surcharges no se aplican automáticamente en pricing**. `early_checkin_surcharge` / `late_checkout_surcharge` se guardan en Property pero `PricingService.calculate_price` no los suma. La aplicación debería ocurrir al generar el folio (`DocumentService.generate_folio_pdf`) — pero esa integración no está en este MVP. Quedaría como follow-up Phase 2e-ext.
- **`set_property_hours` valida `check_in_start < check_in_end`**, pero NO valida `check_out_time` vs `check_in_start` (un hotel puede tener check-out 10:00 y check-in 14:00 — son ventanas separadas). Si querés validar "check-out debe ser antes del próximo check-in", es lógica adicional que no está acá.
- **El campo `late_checkout_time` se limpia a None cuando `late_checkout=False`** en el service (defense-in-depth contra stale UI). El test `test_late_checkout_time_ignored_when_flag_false` confirma este comportamiento.
- **Próximo slot de migración: `019_*.py`**.

## Two-Repo Architecture

- **Public** (`sistema-hotel-m` / origin): deployment code only — no internal docs
- **Private** (`hotel-PMS-dev` / private): full codebase + internal docs
- `origin` has dual push URLs — single `git push origin dev` pushes to both repos
- `.gitignore` excludes: `claude_audit/`, `PROJECT_CONTEXT*.md` (incluye archived), `.bat` scripts, `.claude/` configs

## Deployment to GCP Staging

- **One-command deploy**: `bash scripts/deploy_staging.sh` (also `npm run deploy:staging`)
  - Auto-detects VM IP via `gcloud compute instances describe` — IP changes are handled automatically
  - Runs local tests → pushes `dev:main` to origin → SSH to VM → resets to origin/main → pip install → `python scripts/run_migrations.py` → rebuild mobile with fresh IP → `sudo systemctl restart hotel-backend hotel-mobile hotel-pc`
  - VM: `hotel-munich-staging` in zone `us-central1-a` (e2-small Ubuntu 22.04)
- **DB migrations**: numbered files in `scripts/migrations/NNN_name.py` — each exports `MIGRATION_NAME`, `MIGRATION_DESCRIPTION`, and `run(conn)`. `run_migrations.py` auto-discovers and applies only pending ones (tracked via `migration_history` table). Idempotent — safe to re-run.
- **VM setup runbook**: `scripts/setup_gcp_staging.md` (initial VM provisioning) + `scripts/setup_tailscale.md` (remote access)
- **Disaster recovery**: `scripts/recreate_vm.sh` nukes and rebuilds the VM from scratch
