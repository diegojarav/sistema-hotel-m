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
  tests/          # pytest test suite (539 tests, 83% coverage)
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
1. **backend-tests**: Install deps → all 539 tests (v1.8.0: 313 legacy + 56 caja/transaccion + 43 channel manager v2 + 54 room charges/inventory + 44 meal plans & kitchen + 29 email) with coverage (75% min) → KPI + perf included → upload reports
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
- **PC**: `09_🔧_Configuracion.py` gains a 3-step "Configuración de Comidas" section (toggle → mode → plans editor). New `94_👨‍🍳_Cocina.py` page with date picker (default: tomorrow), metric cards, detail table, CSV + PDF export. Shows "Servicio no habilitado" one-liner when disabled.
- **Mobile**: new `/dashboard/meals/page.tsx` (read-only; Hoy/Mañana toggle). Dashboard tile "Cocina — Desayunos hoy: N" conditionally renders only when `meals_enabled=true`. Reservation form conditionally shows plan selector + breakfast_guests input when mode ≠ INCLUIDO.

### Critical gotchas
- **Never show meal UI when `meals_enabled=false`.** Every mobile surface must check `getMealsConfig().meals_enabled` before rendering. Every backend path that doesn't check this flag risks leaking "0 desayunos" widgets to hotels that don't serve meals.
- **Kitchen date logic: night-of-(D-1)**, not "is staying on D". A guest checking in on D is NOT eating breakfast on D. A guest checking out on D IS. `KitchenReportService.get_daily_report` encodes this — don't re-invent it.
- **System plans are un-deletable.** `MealPlanService.soft_delete` raises on `is_system=1`. Set `is_active=0` via update if you need to hide one.
- **Legacy `Property.breakfast_included`** is deprecated v1.7 — migration 005 backfills to `meals_enabled=1, mode=INCLUIDO`. Plan removal en una migración futura (v1.9+); migración 006 quedó tomada por `email_log` de Phase 5.

## AI Agent Tools (18 functions in ai_tools.py)

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
15. `consultar_inventario` — Product stock query; low-stock list or name filter — **v1.6.0**
16. `consumos_habitacion` — Consumos for a reservation/guest/room — **v1.6.0**
17. `reporte_cocina` — Daily breakfast/meal count (or "no habilitado" if disabled) — **v1.7.0**
18. `estado_email_reserva` — Consulta si se envió el correo de una reserva, cuándo, a quién, y total de envíos exitosos/fallidos — **v1.8.0**

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
- **`AIAgentPermission` (database.py)** es andamio intencional para feature futura de control granular de tools IA por rol (ej: Recepcion no consulta reportes financieros via agente). No tiene endpoint ni servicio activo aún — **NO eliminar**.

## Two-Repo Architecture

- **Public** (`sistema-hotel-m` / origin): deployment code only — no internal docs
- **Private** (`hotel-PMS-dev` / private): full codebase + internal docs
- `origin` has dual push URLs — single `git push origin dev` pushes to both repos
- `.gitignore` excludes: `claude_audit/`, `PROJECT_CONTEXT*.md` (incluye archived), `REQUIREMENTS.md`, `.bat` scripts, `.claude/` configs

## Deployment to GCP Staging

- **One-command deploy**: `bash scripts/deploy_staging.sh` (also `npm run deploy:staging`)
  - Auto-detects VM IP via `gcloud compute instances describe` — IP changes are handled automatically
  - Runs local tests → pushes `dev:main` to origin → SSH to VM → resets to origin/main → pip install → `python scripts/run_migrations.py` → rebuild mobile with fresh IP → `sudo systemctl restart hotel-backend hotel-mobile hotel-pc`
  - VM: `hotel-munich-staging` in zone `us-central1-a` (e2-small Ubuntu 22.04)
- **DB migrations**: numbered files in `scripts/migrations/NNN_name.py` — each exports `MIGRATION_NAME`, `MIGRATION_DESCRIPTION`, and `run(conn)`. `run_migrations.py` auto-discovers and applies only pending ones (tracked via `migration_history` table). Idempotent — safe to re-run.
- **VM setup runbook**: `scripts/setup_gcp_staging.md` (initial VM provisioning) + `scripts/setup_tailscale.md` (remote access)
- **Disaster recovery**: `scripts/recreate_vm.sh` nukes and rebuilds the VM from scratch
