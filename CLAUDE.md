# Hotel Munich PMS — Development Guide

## Overview

Property Management System for small/mid-size hotels. Single-tenant SQLite today, multi-tenant Postgres in roadmap. Powers Hotel Los Monges (Ciudad del Este) in production; demo-ready for additional hotels via `DEFAULT_PROPERTY_ID`. Three frontends share one backend: PC admin (Streamlit), mobile reception (Next.js), AI agent (Gemini). v1.10.0-dev (post-Phase-2e).

## Tech Stack

- **Backend**: FastAPI + SQLAlchemy + SQLite (WAL mode), Python 3.14
- **Frontend PC**: Streamlit multipage (10 pages) — `frontend_pc/`
- **Frontend Mobile**: Next.js 16 + React 19 + TypeScript — `frontend_mobile/`
- **Auth**: JWT (bcrypt) — 365-day access + refresh TTL (hotel runs 24/7)
- **AI**: Google Gemini 2.5 Flash (tool-calling agent)
- **PDF**: fpdf2 | **Encryption**: cryptography.Fernet | **Image OCR**: Pillow
- **Deploy**: GCP staging VM (`hotel-munich-staging`, us-central1-a)
- **Tests**: pytest, in-memory SQLite + StaticPool

## Project Structure

```
backend/           API + services + models + tests + generated PDFs
  api/             Endpoints, deps, middleware, auth, core/config
  services/        Business logic (one file per domain)
  database.py      SQLAlchemy models + session management
  hotel/           Generated PDFs (Reservas/, Clientes/, Cuentas/, Reportes_Cocina/) [gitignored]
  tests/           Pytest suite + reports/
frontend_pc/       Streamlit admin (pages/, components/, helpers/)
frontend_mobile/   Next.js mobile app (app/, src/components, src/services)
scripts/           Migrations (NNN_*.py), seeds, deploy, retention
```

## Current State Snapshot

| Item | Value |
|---|---|
| HEAD commit | `28e3661`+ (E2E marathon: room-overlap guard + configurable harness) |
| Released tag | `v1.10.0` at `c342a4b` (Phase 2b) |
| Working tree | clean, both `private/dev` + `origin/main` synced |
| Tests | **832 passing**, 83% coverage |
| Migrations | **018 applied**, next slot **`019_*.py`** |
| Staging VM | `hotel-munich-staging` (STOPPED — ephemeral IP on restart) |
| AI Tools | 20 (last added: `buscar_vehiculo`) |
| Roles | admin, supervisor, gerencia, recepcion, recepcionista, cocina |

## Test Commands

```bash
# All tests
cd backend && python -m pytest tests/ -v

# Coverage
cd backend && python -m pytest tests/ -v --cov=services --cov=api --cov-report=term-missing

# KPI evaluations
cd backend && python -m pytest tests/test_kpis.py -v -m kpi

# Performance benchmarks
cd backend && python -m pytest tests/test_performance.py -v -m perf

# Skip slow perf
cd backend && python -m pytest tests/ -v -k "not perf"
```

Credentials for testing: **admin/admin123**, **recepcion/recep123** (dev/prod from `seed_monges.py`). Public README uses demo `admin/1234`, `recepcion/1234`.

## KPI Thresholds

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| Overall KPI Score | ≥ 95 | 90-94 | < 80 |
| Individual KPI | ≥ 90 | 80-89 | < 70 |
| Performance pass rate | ≥ 90% | 80-89% | < 80% |
| Test coverage | ≥ 75% | 60-74% | < 60% |
| Full test pass rate | 100% | ≥ 95% | < 95% |

9 KPIs measured (test_kpis.py): Booking Integrity, Occupancy Accuracy, Pricing Accuracy, API Response Time, Data Consistency, Calendar Sync, Revenue Accuracy, Security Compliance, Agent Tool Reliability.

Performance baselines (N=10/100/500): occupancy_map, today_summary, monthly_room_view < 200ms / 500ms / 1500ms · revenue_by_room_month < 200/1000/3000 · room_report < 200/500/2000 · calculate_price avg < 50ms.

## Skills Available

- `/hotel-health-check` — On-demand KPI evaluation + full test suite
- `/hotel-perf-benchmark` — On-demand performance benchmarks with analysis

---

## Model Conventions

- **Every FK declares `ondelete=`** (RESTRICT for masters, CASCADE for children, SET NULL for soft links).
- **Booleans use real `Boolean` type**, NOT `Column(Integer, default=0/1)`. SQLite stores INTEGER under the hood; Postgres gets native BOOLEAN.
- **JSON fields use `Column(JSON)`**, NOT `String # JSON`. Callers pass `dict`/`list` directly — DO NOT `json.dumps()` first (double-encode).
- **`property_id` is a real `FK` to `properties.id`** on every operational table (RESTRICT). Use `DEFAULT_PROPERTY_ID` env var from `api/core/config.py` — never hardcode `"los-monges"`.
- **Timestamps**: `DateTime` (not Date), `default=datetime.now`.
- **Soft delete**: `is_active Boolean` (not physical DELETE).
- **Snapshot pattern**: when capturing state-at-event (price, billing info, currency, vehicle plate), store both the snapshot fields AND the live FK. Snapshot wins for historical reports; FK for joining to current state.
- **Slug is canonical tenant ID**: `Property.slug` UNIQUE NOT NULL (SaaS prep).

## Service Conventions

- **Location**: `backend/services/<domain>_service.py`, exported from `services/__init__.py`.
- **`@with_db` decorator**: services use it for dual FastAPI/Streamlit injection. Signature: `db: Session` MUST be the FIRST positional parameter, NOT a kwarg with default. Decorator inserts db as first arg in Streamlit mode.
- **AI tools MUST call @with_db services**, never `session_factory()` directly (`conftest.py` patches `SessionLocal` but not `session_factory` → tests will see "no such table").
- **Service exceptions**: each service raises its own typed exception (`GuestServiceError`, `EmailError`, `TransaccionError`, etc.). Endpoints catch them as 400 with Spanish detail.
- **Spanish errors throughout**: business `ValueError` and service exceptions all carry Spanish messages — they surface to end users.
- **Two Guest services** (post-Phase 2a rename, ALWAYS pick the right one):
  - `GuestService` = master Guest entity (one row per person across stays)
  - `CheckInService` = per-stay ficha (one row per registration)
  - Mixing them throws `AttributeError` at runtime — there's no shared method surface.

## Endpoint Conventions

- **Path style**: `/api/v1/<noun-spanish>/...` for new domains (`/huespedes`, `/caja`, `/transacciones`, `/consumos`, `/productos`, `/buildings`, `/currencies`, `/meal-plans`, `/email`, `/reportes`). Legacy `/guests/*` kept for CheckIn compat — don't repurpose.
- **Role-based auth**: `require_role(*ROLES)` — note splat. Default role lists at top of each endpoint module.
- **Pydantic schemas in `schemas.py`**: requests + responses. JSON fields use `Optional[Any]`, never `Optional[str]`.
- **Spanish 400 errors**: catch service `ValueError` and re-raise as `HTTPException(400, detail=str(e))` BEFORE the generic `except Exception` swallows it as 500 ("Error al crear la reserva..."). Same for parking overflow, capacity guard, etc.
- **slowapi rate limiter**: `request: Request` MUST be the FIRST positional parameter in any `@limiter.limit()` endpoint. Path params first → limiter silently ignored.
- **Background tasks open their own session**: `fastapi.BackgroundTasks` callbacks run AFTER the endpoint closes its db. Use `session_factory()` (NOT the endpoint's `db`) and `try/finally` for state transitions.

## Migration Conventions

- **Location**: `scripts/migrations/NNN_description.py`
- **Next slot**: **`019_*.py`** (slots 001-018 taken)
- **Format**: each file exports `MIGRATION_NAME`, `MIGRATION_DESCRIPTION`, `run(conn)` function. Idempotent — safe to re-run.
- **Runner**: `python scripts/run_migrations.py` auto-discovers + applies only pending (tracked via `migration_history` table).
- **ALWAYS add a numbered migration when adding a column** to any SQLAlchemy model. VM `hotel.db` predates reseeding — missing migrations surface as `OperationalError: no such column` on deploy. Schema drift is a hard recurring bug.
- **Self-heal pattern**: migrations that backfill data from legacy columns should ALTER ADD any missing predecessor columns first (see migration 011 for `contact_phone` pattern, commit `509d386`).

## Test Conventions

- **In-memory SQLite + StaticPool** for thread safety.
- **`conftest.py` patches `database.SessionLocal` and `services._base.SessionLocal`** so `@with_db` uses test DB. Does NOT patch `session_factory` — AI tools that bypass `@with_db` will fail in CI.
- **Rate limiter auto-disabled during tests**.
- **`PRAGMA foreign_keys=ON` contamination**: enabling FKs in one test contaminates StaticPool's reused connection. Any test inserting into FK-bearing tables (e.g. `property_id` children) must depend on `seed_property` fixture.
- **JSON columns in fixtures**: use `amenities=[]`, NOT `amenities="[]"` (double-encode after Phase 2b).
- **`seed_rooms` auto-includes `seed_client_types`** (since Phase 2a, because `reservations.client_type_id` is now a real FK).
- **`seed_pricing_data` depends on `seed_property`**.
- **FK CASCADE tests**: SQLite doesn't enforce FK by default — use `db_session.execute(text("PRAGMA foreign_keys=ON"))` per-connection. See `test_multi_vehicle.py::TestCascadeDelete`.
- **NEVER hardcode check-in dates in tests** (`"2026-06-01"` style). The hotel-day validator (Phase 2e) rejects past dates → tests rot into 422 failures when the date passes (bit test_caja_api + test_consumo_api, July 2026). Use `(date.today() + timedelta(days=N)).isoformat()`.

## Commit Conventions

- **Imperative tense**: `fix(caja): treat null as no session`, `feat(currency): multi-currency MVP`
- **Body sections**: Bug / Root cause / Fix (when applicable), or a paragraph describing the change.
- **Co-authored footer**: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` on every commit.
- **Pre-commit hook runs full pytest** (~3min). Commit in background, wait for monitor signal — don't poll.
- **Push pattern**:
  - `git push private dev` → private/dev only
  - `git push origin dev:main` → BOTH origin + private (dual push URL)
  - `bash scripts/deploy_staging.sh` → does the dual-push + VM deploy

---

## Active Gotchas (will bite you)

### Backend / API

- **`launch.json` MUST bind `--host 0.0.0.0`** (NOT `127.0.0.1`). Mobile dev uses `NEXT_PUBLIC_API_URL=http://192.168.3.140:8000` (LAN IP) so phone testing works. 127.0.0.1 → Claude_Preview + phone fail with `TypeError: Failed to fetch`.
- **AI tool params must be `Optional[str] = None`** with None-handling. `test_tools_return_strings` (KPI) calls every tool with `()` unless listed in `tool_inputs` — required str args → `TypeError`.
- **Gemini system_instruction must be ~800 chars max**. With 16+ tools, longer prompts make Gemini return `response.text=None` + `candidate.content.parts=None`. Tool docstrings are read directly from `tools=` — don't duplicate them in the prompt.
- **Calendar service methods must include `"Completada"`/`"COMPLETADA"`** in status filters for historical views (`get_occupancy_map`, `get_weekly_view`, `get_monthly_events`, `get_daily_status`). EXCLUDE only for availability checks (`get_range_status`, `create_reservations`).
- **TZ consistency in rate-limit**: `email_log.created_at/sent_at` use `datetime.now()` (local). Query uses `datetime.now() - timedelta(hours=1)` (also local). NEVER mix with `datetime('now')` SQLite (UTC) — silent CI failure when running in different TZ.
- **Discord alerts only for infra fails** (SMTP down, PDF gen crash). User validation errors are 400/422/429 with Spanish — NOT logger.error.
- **`cryptography` must be installed in BOTH Python envs** (hybrid monolith): backend `C:\Python314`, PC `A:\Miniconda\envs\hotel_munich`. Missing in one → PC login fails with `No module named 'cryptography'`.

### Streamlit (PC frontend)

- **`st.form` cannot contain mutating widgets** (download_button, dynamic state). Render those OUTSIDE the form. Patterns: store PDF paths in `st.session_state` inside, render `st.download_button` outside; multi-vehicle / meal-plan widgets live OUTSIDE the form because the form blocks live recomputation.
- **`services/__init__.py` cache survives hot-reload**: adding a new export (e.g. `from services.currency_service import CurrencyService`) → pages get `ImportError` until full Streamlit restart (`Ctrl+C` + relaunch). NEVER a code fix — always "restart Streamlit".
- **PC token is `api_token`, NOT `access_token`** (recurring bug). Every new PC page MUST use `st.session_state.get("api_token")` for JWT. `app.py:82` stores it that way.
- **`api_get` returns `None` for HTTP failures AND legitimate JSON `null`**. `/caja/actual` returns null when no session — that's "no shift right now", not an error. Use `if not current:` for empty-state branches; don't error-stop on None.
- **Missing imports in Streamlit pages**: `tab_reserva.py` has been hit twice by missing-imports (e.g. `time` from `datetime`). The bug doesn't surface until a code path is exercised — Streamlit pages have no CI linter. When adding code that uses ANY symbol, double-check the top imports.

### Mobile (Next.js)

- **React `useEffect` auto-shrink pattern is dangerous**: effects that read-and-write the same state (e.g. `if mealGuests > cap, set mealGuests = cap`) must NOT include the value-being-shrunk in their dep array — fires on every keystroke, snaps back any decrement. Depend only on the trigger (`totalRoomCapacity`). Add `eslint-disable-next-line react-hooks/exhaustive-deps` with inline comment so future readers don't "fix" it back.

### Reservations / business rules

- **`vehicles=[]` is the path switch** (Phase 2c). Empty / missing → legacy single-vehicle path (1 spot per room). Any entry → multi-vehicle path (1 spot per vehicle). Beware "added by mistake" UI state.
- **Primary vehicle ALWAYS writes to legacy columns** (`reservations.vehicle_plate`/`vehicle_model`). If none marked `is_primary=True`, index 0 wins. No "exactly one" validation.
- **`search_by_plate` can return `guest=None`** for quick-add companions without a master Guest. `buscar_vehiculo` AI tool already handles None — any new caller must too.
- **5-vehicle limit per guest** hard-enforced in `GuestVehicleService.create_vehicle`. Overflow → best-effort log + skip (reservation succeeds, master not updated).
- **Plate normalization**: validator + `_norm_plate` uppercase + trim. Never compare plates raw.
- **`billing_ruc` validator strips non-digits/hyphens** (Paraguay format `XXXXXXXX-X`). Test values like `"MY-RUC"` become `"--"` — use real digits.
- **BillingProfile is NOT UNIQUE per (guest, tax_id)** — same guest can have personal + corporate with same RUC. De-dup done in `find_or_create_from_checkin`, not DB.
- **NEVER mix `GuestService` (master) and `CheckInService` (fichas)** — separate concepts, separate methods. Check which one you actually need before importing.
- **`find_or_create_guest` is best-effort**: if all identity inputs are blank → returns `None`. Caller treats `None` as "could not link" — reservation stays valid with `guest_id=NULL`.
- **`update_reservation` does NOT re-link `guest_id`** (intentional snapshot freeze). To change guest, cancel + re-book.
- **`update_reservation` clears `breakfast_guests` when `meal_plan_id` set to None** — prevents "2 guests with breakfast, no plan" → kitchen over-count.
- **Status auto-recalculates** on every payment/consumo change via `TransaccionService._recalcular_status_reserva()`. Don't manually set CONFIRMADA — register the payment and let the service derive it.

### Multi-currency

- **`amount` is ALWAYS in base currency**, no exceptions. All totals/saldos/reports sum `amount`. Iterating `amount_original` would mix currencies.
- **Exchange rate frozen at payment time**. Snapshot row keeps `exchange_rate`. Updating the TC later does not retroactively change historical reports.
- **Cannot change base currency with active transactions** (`CurrencyService.set_base_currency` rejects with Spanish error). Would re-significance all historical reports.
- **No auto-FX feeds**. Admin updates rates manually (PC-only). Mobile is read-only for currencies.
- **Migration 017 seed runs once per property**. To re-seed: delete `accepted_currencies` rows manually + re-run; `migration_history` won't re-trigger.

### Hotel-day / Check-in times

- **`Property.check_*_time` are STRINGS** (`Column(String, default="07:00")`). To operate as `time`, pass through `_coerce_time` or `datetime.strptime(value, "%H:%M").time()`. Comparing strings sort-textually works by coincidence (HH:MM zero-padded) but is fragile.
- **Pydantic validator uses default 10:00**, NOT a DB read (Pydantic validators are pure / sync). Conservative — rejects faster than strictly needed. Service-layer could be more permissive (next iteration).
- **`late_checkout_time` cleared to None when `late_checkout=False`** in service (defense vs stale UI).
- **Late-checkout availability blocking DEFERRED to Phase 6.5**. `late_checkout_time` stored but overlap check does NOT consult it. A reservation with late checkout until 14:00 does NOT block another check-in at 14:00.

### Meals

- **`meals_enabled=false` → NEVER show meal UI**. Every mobile surface checks `getMealsConfig().meals_enabled`; every PC page checks `get_meals_config()['meals_enabled']`. Hotels that don't serve meals must see zero meal widgets.
- **Kitchen date logic: night-of-(D-1)**. Guest checking IN on D is NOT eating breakfast on D. Guest checking OUT on D IS. Don't re-invent — encoded in `KitchenReportService.get_daily_report`.
- **`breakfast_guests` capacity guard**: service rejects `breakfast_guests > sum(rooms.custom_capacity ?? category.max_capacity)`. PC + mobile cap client-side, but OTA bridges can bypass UI.
- **System plans (`meal_plans.is_system=1`) un-deletable**. Use `is_active=0` via update to hide.

### Deployment / infra

- **GCP staging external IP is ephemeral** — every stop/start reassigns. Recent: `34.29.241.50` → `34.10.52.145` → `136.119.0.159`. Fetch fresh via `gcloud compute instances describe ... --format='get(networkInterfaces[0].accessConfigs[0].natIP)'`. Backlog: reserve static IP (~$3/mo).
- **Deploy `dev:main` to both origin + private**: if public `origin/main` has PR-merge commits not local, push rejected — force-push with `git push --force origin dev:main` (safe: PR commits are GitHub UI wrappers over content already in `dev`).

---

## Domain Quick References

### Reservation Status Lifecycle (v1.4.0)

```
RESERVADA → SEÑADA → CONFIRMADA → COMPLETADA
    └───────┴──────────┴──→ CANCELADA
```

Derived from payments; auto-recalculated. Terminal states (CANCELADA/COMPLETADA) never auto-changed. Supports both new (`RESERVADA`/`SEÑADA`/`CONFIRMADA`/`COMPLETADA`/`CANCELADA`) and legacy values (`Pendiente`/`Confirmada`/`Completada`/`Cancelada`) simultaneously via expanded `.in_()` lists. **Active (blocks rooms)**: RESERVADA, SEÑADA, CONFIRMADA. **Past (no block)**: COMPLETADA, CANCELADA.

### Cash Register Rules

- One ABIERTA session per user. EFECTIVO requires open caja (400 if none). TRANSFERENCIA/POS don't.
- Transactions are immutable — void only (reason ≥ 3 chars; admin + recepcion can void).
- Close: `expected = opening + sum(EFECTIVO)`, `difference = declared - expected`.

### Multi-currency Rules

- `Property.currency` = base. `accepted_currencies` per-property catalog with `exchange_rate`.
- `transaccion.amount` ALWAYS base. `currency_code`/`exchange_rate`/`amount_original` snapshot at register time.
- 20-currency CATALOG hard-coded in `services/currency_service.py` (Hispanic + USD/EUR/GBP).

### Multi-vehicle Rules

- 1 vehicle = 1 parking spot. Cap = `parking_capacity` (400 if exceeded, Spanish msg).
- Two modes per vehicle: `linked` (FK to master `guest_vehicles`) or `quick` (snapshot only).
- Mobile is quick-mode only (v1); linked-mode mobile = backlog.

### Hotel-day Rules

- Day D ends at `D+1 @ check_out_time`, not midnight.
- `services/hotel_day.py::can_create_reservation_for_date` is the gate.
- Pydantic validator uses default 10:00 (no DB read); PC date picker reads property settings.

### Channel Manager Rules

- `_periodic_ical_sync()` every 15 min. Cancellations → `needs_review=True` flag (Discord alert), NOT auto-cancel.
- 5 sources: Booking.com, Airbnb, Vrbo, Expedia, Custom.
- Per-feed health tracked (`consecutive_failures`); Discord alert at `>= 3`.

### Email Rules

- Async via `BackgroundTasks`, endpoint returns 202.
- Rate limit: 3 ENVIADO per reservation per hour (FALLIDO don't count → admin can debug SMTP).
- SMTP password Fernet-encrypted (key derived from `SECRET_KEY`). Rotating `SECRET_KEY` → invalidates stored passwords.
- PDF always regenerated before send (no stale data).

### Meal Plans

| Mode | Form selector | Kitchen report includes |
|---|---|---|
| disabled | hidden everywhere | nothing |
| INCLUIDO | hidden, auto-CON_DESAYUNO | all overnight guests |
| OPCIONAL_PERSONA | plan + `breakfast_guests` count | guests with > 0 |
| OPCIONAL_HABITACION | plan only (no count) | rooms with non-SOLO plan |

### Permissions Summary

| Action | admin / supervisor / gerencia | recepcion / recepcionista | cocina |
|---|---|---|---|
| Reservation CRUD | ✅ | ✅ | ❌ |
| Caja open/close, register payment | ✅ | ✅ | ❌ |
| Register consumo | ✅ | ✅ | ❌ |
| Void transaction / consumo | ✅ | ❌ | ❌ |
| Product CRUD, stock adjust, reports | ✅ | ❌ | ❌ |
| Email config + test | admin only | ❌ | ❌ |
| Send email + view historial | ✅ | ✅ | ❌ |
| Kitchen report | ✅ | ✅ | ✅ (only route they can hit) |
| Room status PATCH + log | admin/supervisor | view-log only | ❌ |
| AI permissions admin | admin only | ❌ | ❌ |
| Currency admin (rates, base) | admin only | view only | ❌ |
| Hotel hours / property settings | admin/supervisor/gerencia | ❌ | ❌ |

---

## Tables (~28 active)

**Tenant/config**: `properties`, `system_settings`, `buildings`
**Identity**: `users`, `session_logs`, `guests`, `billing_profiles`, `guest_vehicles`
**Inventory**: `room_categories`, `rooms`, `producto`, `ajuste_inventario`
**Booking**: `reservations`, `reservation_vehicles`, `checkins`, `checkin_vehicles`, `consumo`
**Pricing**: `pricing_seasons`, `price_calculations`, `client_types`, `client_contracts`, `meal_plans`
**Money**: `caja_sesion`, `transaccion`, `accepted_currencies`
**Channels**: `ical_feeds`, `ical_sync_log`
**Audit/ops**: `email_log`, `room_status_log`, `migration_history`, `ai_agent_permissions`

(Detailed column lists in `CLAUDE_ARCHIVE.md`.)

## Endpoints (paths, grouped)

**Auth**: `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/logout`
**Reservations**: `/reservations/*`, `/reservations/{id}/saldo`, `/reservations/needs-review`, `/reservations/{id}/acknowledge-review`, `/reservations/{id}/confirm-ota-cancellation`
**Guests (master)**: `/huespedes/*`, `/huespedes/{id}/billing[/*]`, `/huespedes/{id}/vehicles[/*]`, `/huespedes/{id}/history`
**Check-ins**: `/guests/*` (LEGACY path → CheckInService), `/checkins/{id}/vehicles[/*]`
**Vehicles**: `/vehicles/search?plate=` (OCR hook)
**Buildings**: `/buildings[/*]`
**Rooms**: `/rooms/*`, `/rooms/{id}/status`, `/rooms/{id}/status-log`
**Pricing**: `/pricing/*`, `/seasons/*`, `/contracts/*`, `/client-types/*`
**Calendar**: `/calendar/*`
**Caja**: `/caja/abrir`, `/caja/cerrar`, `/caja/actual`, `/caja/historial`, `/caja/{session_id}`
**Transacciones**: `/transacciones/*`
**Productos / Consumos**: `/productos[/*]`, `/productos/{id}/ajuste-stock`, `/productos/stock-bajo`, `/productos/mas-vendidos`, `/consumos[/*]`
**Currencies**: `/currencies/*`, `/currencies/catalog`, `/currencies/base`
**Meal plans**: `/meal-plans[/*]`, `/settings/meals-config`
**Reports**: `/reportes/ingresos-diarios`, `/reportes/transferencias`, `/reportes/resumen-periodo`, `/reportes/cocina[/pdf]`
**Documents**: `/documents/reservations/{id}`, `/documents/clients/{id}`, `/documents/folio/{id}`, `/documents/list/{folder}`, `/documents/download/{folder}/{filename}`
**Email**: `/settings/email`, `/settings/email/test`, `/email/reserva/{id}/enviar`, `/email/reserva/{id}/historial`
**Settings**: `/settings/property-settings`, `/settings/property-hours`
**iCal**: `/ical/feeds[/*]`, `/ical/feeds/{id}/health`, `/ical/feeds/{id}/logs`, `/ical/export/{room_id}.ics`, `/ical/export/all.ics`
**AI**: `/agent/query`, `/admin/ai-permissions[/*]`, `/admin/ai-permissions/{role}/allowed-tools`
**Vision (OCR)**: `/vision/*`

## AI Tools (20)

`check_availability`, `get_hotel_rates`, `get_today_summary`, `search_guest`, `search_reservation`, `get_reservations_report`, `calculate_price`, `get_occupancy_for_month`, `get_room_performance`, `get_booking_sources`, `get_parking_status`, `get_revenue_summary`, `consultar_caja`, `resumen_ingresos_por_metodo`, `consultar_inventario`, `consumos_habitacion`, `reporte_cocina`, `estado_email_reserva`, `buscar_huesped_historial`, `buscar_vehiculo`.

Tool ↔ permission mapping (5 columns control all 20): `can_view_reservations` (4 tools), `can_view_guests` (3 tools incl. buscar_huesped_historial + buscar_vehiculo), `can_view_rooms` (1), `can_view_prices` (2), `can_view_reports` (10). New tools without `TOOL_PERMISSION_MAP` entry are ALWAYS allowed (defensive default — add to map before deploy).

## Critical Business Logic Files

Changes to these require KPI test validation:

`backend/services/reservation_service.py`, `pricing_service.py`, `room_service.py`, `document_service.py` · `backend/api/v1/endpoints/reservations.py`, `pricing.py`, `calendar.py`, `ai_tools.py`, `agent.py`, `documents.py`

---

## Monitoring & CI

| Channel | What | How |
|---|---|---|
| Discord (runtime) | Backend ERROR/CRITICAL | `DiscordWebhookHandler` (5-min dedup, non-blocking) |
| Discord (CI) | GitHub Actions failures | `notify-discord` job in `ci.yml` |
| Healthchecks.io | Backend uptime | Push ping every 15min from `_periodic_ical_sync()` |
| GitHub Email | CI results | Automatic on push to `main`/`dev` |

**CI**: backend-tests (832 tests + KPI + perf, 75% min coverage) + frontend-check (npm ci + build) + notify-discord on fail. Runs on push to `main`/`dev`.

**Monthly maintenance** (1st of month, 9AM): KPI suite + perf benchmarks + full test + AI agent eval + summary with regressions.

## Two-Repo Architecture

- **Public** (`sistema-hotel-m` / `origin`): deployment code only — no internal docs
- **Private** (`hotel-PMS-dev` / `private`): full codebase + internal docs
- `origin` has dual push URLs — `git push origin dev` pushes to BOTH
- `.gitignore` excludes: `claude_audit/`, `PROJECT_CONTEXT*.md`, `.bat` scripts, `.claude/` configs

## Deployment to GCP Staging

- **One-command**: `bash scripts/deploy_staging.sh` (also `npm run deploy:staging`)
  - Auto-detects VM IP (handles ephemeral IP changes)
  - Local tests → push `dev:main` to origin → SSH to VM → reset to origin/main → pip install → `python scripts/run_migrations.py` → rebuild mobile with fresh IP → `sudo systemctl restart hotel-backend hotel-mobile hotel-pc`
  - VM: `hotel-munich-staging` in `us-central1-a` (e2-small Ubuntu 22.04, project `gen-lang-client-0259000236`)
- **DB migrations**: `scripts/migrations/NNN_*.py` discovered + applied by `run_migrations.py`. Idempotent.
- **Runbooks**: `scripts/setup_gcp_staging.md`, `scripts/setup_tailscale.md`
- **Disaster recovery**: `scripts/recreate_vm.sh` rebuilds VM from scratch
- **Retention cleanup**: `scripts/cleanup_retention.py` (price_calculations >90d without reservation_id, session_logs >365d). Idempotent, dry-run capable.

## Misc Notes

- Always use `encoding='utf-8'` when opening files in Python
- `PricingService.calculate_price()` requires `client_type_id` (not optional)
- `database.py` must NOT import pandas (was causing CI failures)
- `Pillow` required for `vision.py` OCR; `fpdf2` required for PDF generation
- PDF documents auto-generate on reservation/check-in creation, saved to `backend/hotel/`
- Streamlit reads PDFs via direct filesystem (same machine as backend)

---

## See Also

- `CLAUDE_ARCHIVE.md` — Historical phase details, full column listings, frontend specifics, migration history
- `CHANGELOG.md` — Version history
- `ROADMAP.md` — Planned work + Phase 6.5 backlog (late-checkout blocking, surcharge folio integration, auto-FX feeds, linked-mode mobile, static IP, original-currency payment history on mobile)
- `README.md` — Public documentation
