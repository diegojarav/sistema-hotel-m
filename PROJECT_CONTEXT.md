# PROJECT_CONTEXT.md
# Hotel Management System - Single Source of Truth
**Last Updated:** 2026-02-27
**Phase:** Los Monges MVP -- Deployed to GCP Staging (v1.1.0)

---

## EXECUTIVE SUMMARY

**What:** A Hotel Management System (HMS) for "Hospedaje Los Monges" — category-based (sells by room type, not room number).

**Architecture:** Hybrid Monolith
- PC Frontend (Streamlit) imports backend directly (local deployment)
- Mobile Frontend (Next.js) uses REST API (clean separation)
- Both access the same SQLite database (`backend/hotel.db`)

**Business requirements:** See `REQUIREMENTS.md`
**Audit status:** See `claude_audit/00_SYNTHESIS_REPORT.md`

---

## PROJECT STRUCTURE

```
hotel_munich/
├── backend/
│   ├── database.py              # SQLAlchemy models, DB connection
│   ├── schemas.py               # Pydantic validation schemas
│   ├── logging_config.py        # Centralized logging
│   ├── hotel.db                 # SQLite database (SINGLE SOURCE OF TRUTH)
│   ├── services/                # Business logic (PACKAGE - extracted 2026-02-08)
│   │   ├── __init__.py          # Re-exports all classes for backward compat
│   │   ├── _base.py             # get_db(), @with_db hybrid decorator
│   │   ├── auth_service.py      # AuthService (115 LOC)
│   │   ├── reservation_service.py # ReservationService (905 LOC)
│   │   ├── guest_service.py     # GuestService (160 LOC)
│   │   ├── settings_service.py  # SettingsService (84 LOC)
│   │   ├── pricing_service.py   # PricingService (136 LOC)
│   │   ├── room_service.py      # RoomService (202 LOC)
│   │   └── ical_service.py      # ICalService (331 LOC) — iCal import/export/sync
│   └── api/                     # FastAPI routes
│       ├── core/                # security.py, config.py
│       ├── deps.py              # Auth dependencies + RBAC
│       ├── main.py              # App + CORS + lifespan (iCal auto-sync every 15min)
│       └── v1/endpoints/        # auth, reservations, guests, rooms, calendar,
│                                # agent, vision, settings, pricing, users, ical, admin
│   └── tests/                   # 224 tests across 22 files (pytest + SQLite StaticPool)
│       ├── conftest.py          # Fixtures (in-memory SQLite, test client, auth tokens)
│       └── test_*.py            # Auth, reservations, guests, rooms, pricing, calendar, etc.
│
├── frontend_pc/                 # Streamlit PC app (MODULARIZED 2026-02-08)
│   ├── app.py                   # Orchestrator (116 LOC) — login, sidebar, tabs
│   ├── components/              # UI rendering modules
│   │   ├── styles.py            # inject_custom_css() (96 LOC)
│   │   ├── calendar_render.py   # render_native_calendar() + render_monthly_room_grid() (370 LOC)
│   │   ├── tab_calendario.py    # Monthly/weekly/daily views (171 LOC)
│   │   ├── tab_reserva.py       # Reservation form — multi-category (restructured 2026-02-09)
│   │   └── tab_checkin.py       # Guest check-in form (176 LOC)
│   ├── helpers/                 # Shared utilities
│   │   ├── constants.py         # MESES_ES, DIAS_SEMANA, legacy lists
│   │   ├── data_fetchers.py     # @st.cache_data functions
│   │   ├── auth_helpers.py      # log_login, log_logout, logout
│   │   └── ui_helpers.py        # Validation formatting, Gemini doc analysis
│   ├── frontend_services/       # cache_service.py
│   ├── api_client.py            # HTTP client for config
│   └── pages/                   # Streamlit multipage
│       ├── 04_Asistente_IA.py   # AI chat assistant
│       ├── 09_Configuracion.py  # Hotel settings
│       ├── 98_Admin_Habitaciones.py  # Room inventory + Ficha Mensual + revenue heatmap
│       └── 99_Admin_Users.py    # User administration
│
├── frontend_mobile/             # Next.js 16 + React 19 + TypeScript
│   ├── src/
│   │   ├── constants/keys.ts    # ACCESS_TOKEN_KEY, API_BASE_URL
│   │   ├── services/            # rooms, pricing, auth, reservations, vision, chat
│   │   └── hooks/               # useAuth, useBeaconLogout
│   └── app/dashboard/
│       ├── reservations/new/    # (MODULARIZED 2026-02-08)
│       │   ├── page.tsx         # Orchestrator (286 LOC)
│       │   └── components/      # DocumentScanner, GuestForm, RoomSelection, PriceSummary
│       ├── calendar/page.tsx
│       ├── availability/page.tsx
│       └── chat/page.tsx
│
├── scripts/                     # Deployment, migration, and operations
│   ├── deploy.py                # Full deployment script with rollback
│   ├── deploy_frontend_only.py  # Frontend-only deploy shortcut
│   ├── seed_monges.py           # Base data seeder (property, rooms, categories)
│   ├── seed_test_data.py        # Test data generator (reservations, check-ins, sessions, iCal feeds)
│   ├── run_migrations.py        # Schema migrations runner
│   ├── add_indexes.py           # Database index migration
│   ├── migrate_*.py             # Schema migration scripts
│   ├── install_services.bat     # Windows NSSM service installer
│   ├── service_control.bat      # Windows service controller
│   ├── service_control_linux.sh # Linux systemd service manager
│   ├── setup_gcp_staging.sh     # GCP VM provisioning script
│   ├── setup_gcp_staging.md     # GCP staging setup guide
│   └── setup_tailscale.md       # Tailscale VPN remote access guide
│
├── PROJECT_CONTEXT.md           # THIS FILE (private repo only)
├── REQUIREMENTS.md              # Los Monges business requirements
└── claude_audit/                # Audit reports and tracking (private repo only)
    └── 00_SYNTHESIS_REPORT.md   # Active sprint tracker
```

---

## ARCHITECTURE

```mermaid
graph TB
    subgraph "Client Layer"
        Mobile["Frontend Mobile<br/>(Next.js 16 + React 19)<br/>📱 Owner Dashboard"]
        PC["Frontend PC<br/>(Streamlit)<br/>🖥️ Reception Desk"]
    end

    subgraph "Application Layer"
        API["Backend API<br/>(FastAPI + SQLAlchemy)<br/>🔐 Auth, CRUD, Business Logic"]
        AI["AI Agent<br/>(Google Gemini 2.5 Flash)<br/>🤖 Virtual Receptionist"]
    end

    subgraph "Data Layer"
        DB[("SQLite Database<br/>(hotel.db)<br/>📊 Single File")]
    end

    Mobile -->|"REST API<br/>(HTTP/JSON)"| API
    PC -.->|"Direct Import<br/>(Hybrid Monolith)"| API
    API --> DB
    API --> AI
```

### Key Technical Patterns

| Pattern | Detail |
|---------|--------|
| **`@with_db` decorator** | Hybrid: auto-detects FastAPI (db injected) vs Streamlit (self-managed sessions). Lives in `services/_base.py`. **CRITICAL:** FastAPI endpoints MUST pass `db` to service methods — omitting it causes `SessionLocal.remove()` to kill the scoped session (see BUG-PRICING-02). |
| **`session_factory()` for FastAPI** | `deps.py:get_db()` uses `session_factory()` directly — NOT `SessionLocal` (scoped_session). `scoped_session` uses `threading.local()` which causes concurrency bugs when FastAPI's threadpool reuses threads. `SessionLocal` is only used by Streamlit via `@with_db`. |
| **PYTHONPATH** | `start_pc.bat` sets `PYTHONPATH=backend/`, so `from services import X` works from `frontend_pc/`. |
| **Backward-compat re-exports** | `services/__init__.py` re-exports all classes + schemas. All consumers unchanged. |
| **Cross-service deps** | `ReservationService` → `PricingService.calculate_price()`, `SettingsService.get_parking_capacity()`. No others. |
| **Centralized API client** | `api.ts` is the single gateway for all mobile HTTP calls. Auto-attaches JWT, handles FormData, consistent error handling. |
| **`useAuth` hook** | All protected mobile pages use `useAuth({ required: true })` for auth guards with automatic token refresh. |
| **Test suite (pytest)** | 224 tests across 22 files. In-memory SQLite with `StaticPool` (thread-safe for FastAPI). Covers services (Streamlit path) + API endpoints (Next.js path). Fixtures in `tests/conftest.py`. Run: `cd backend && python -m pytest tests/ -v`. |
| **Multi-category reservations** | Both frontends show all available rooms grouped by category. Users select rooms from any/multiple categories. Pricing calculates per-category and sums. Backend `create_reservations()` resolves each room's category from DB. |
| **Room ID vs internal_code** | `Room.id` = DB primary key (e.g. `los-monges-room-001`). `Room.internal_code` = human-friendly label (e.g. `DF-01`). All UIs display `internal_code`. Reservations store `room_id` but DTOs include `room_internal_code` for display. |
| **Date-range availability** | `/rooms/status?check_in=&check_out=` checks overlap across full range (prevents overbooking). Mobile re-fetches rooms when dates change. |
| **Property settings endpoint** | `GET /settings/property-settings` returns check-in/out times and breakfast policy from `properties` table. Public endpoint, fetched on reservation form mount. |
| **iCal sync (Booking.com/Airbnb)** | `ICalService` handles import (pull .ics from OTA URLs, upsert reservations with `source`/`external_id`) and export (serve .ics at `/ical/export/{room_id}.ics`). Background auto-sync every 15min via FastAPI lifespan. `ICalFeed` model stores per-room feed URLs. Admin UI in `09_Configuracion.py`. |
| **Admin API** | `admin.py` provides remote management: backup list/trigger, error log tail, deploy log, system info. All endpoints require `require_role("admin")`. |
| **Two-repo architecture** | Public repo (`sistema-hotel-m` / origin) for deployment only. Private repo (`hotel-PMS-dev` / private) with `main` (production code) and `dev` (main + internal docs + dev scripts). Internal docs never reach public repo. |
| **GCP staging** | `scripts/setup_gcp_staging.sh` provisions an e2-small VM in southamerica-east1 (~$16/mo, $300 free credits). `scripts/setup_gcp_staging.md` has the full runbook. |
| **Remote access** | Tailscale mesh VPN for NAT-traversal SSH. Guide in `scripts/setup_tailscale.md`. No port forwarding needed. |
| **Test data seeder** | `scripts/seed_test_data.py` generates 80-100 reservations, 40-50 check-ins, 100+ sessions, 4-6 iCal feeds. Supports `--dry-run` and `--reset`. Weighted random distributions matching real-world patterns. |
| **Linux service management** | `scripts/service_control_linux.sh` manages systemd services (hotel-backend, hotel-pc, hotel-mobile). Commands: status, start, stop, restart, logs. |

---

## STABILITY RATING

**Overall Grade: A (Deployment-Ready)**

| Component | Rating | Notes |
|-----------|--------|-------|
| Backend API | A | FastAPI + SQLAlchemy. N+1 fixed. Pricing engine validated. Admin API for remote management. |
| PC App | A | Modularized (116 LOC orchestrator). Caching optimized. Light theme. iCal admin. |
| Mobile App | A | Connectivity issues resolved. Booking flow active. Multi-category. NaN nights + missing rooms fixed (2026-02-27). |
| Database | A- | SQLite with indexes. Performance optimized. WAL mode. |
| AI Agent | A | Gemini 2.5 Flash stable with fallback. 30s timeout. |
| Security | A+ | RBAC. JWT revocation. Error sanitization. Security headers. Git history purged. Keys rotated. |
| Testing | A | 224 tests across 22 files. 76.5% coverage. Pre-deployment validation. |
| Infrastructure | A | GCP staging scripts. Linux service manager. Tailscale VPN. Test data seeder. |

---

## GAP ANALYSIS: MVP vs. GLOBAL SAAS

| Capability | Los Monges MVP (Now) | Full SaaS (Phase 2+) | Debt |
|------------|----------------------|----------------------|------|
| Multi-Tenancy | No `tenant_id` | Required on ALL tables | Schema migration |
| Database | SQLite (local file) | PostgreSQL (managed) | Connection pooling |
| Authentication | JWT (single hotel) | Tenant-aware + SSO | OAuth2 |
| Billing | N/A | Stripe integration | New tables |
| Scalability | Vertical (single server) | Horizontal (LB) | Refactor PC app |
| Staging Environment | GCP VM (e2-small, southamerica-east1) | Auto-scaling (GKE/Cloud Run) | Container orchestration |
| Remote Access | Tailscale VPN + SSH | Zero-trust network | Production hardening |
| Test Data | seed_test_data.py (manual) | CI/CD pipeline | Automated integration |

**Migration Trigger:** Client #3 or >20 concurrent users.

---

## RISK REGISTER

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SQLite write contention at peak | MEDIUM | HIGH | WAL mode enabled. Plan PostgreSQL migration. |
| Category pricing bugs | LOW | MEDIUM | **Materialized 2026-02-09:** missing `currency` field + missing `db` param. Fixed. Now mitigated by: Pydantic response validation, per-category pricing breakdown visible in both UIs, all endpoints audited for `db` passing. |
| scoped_session concurrency in FastAPI | LOW | HIGH | **Materialized 2026-02-10:** `SessionLocal` (scoped_session) shared sessions across threadpool threads. Fixed: `deps.py` now uses `session_factory()` directly. `SessionLocal` only used by Streamlit. |
| Overbooking (room double-booking) | LOW | HIGH | **Materialized 2026-02-10:** Room status loaded for TODAY only, never re-checked for selected dates. Fixed: date-range overlap API + frontend re-fetch on date change. |
| Multi-tenant data leak (if tenant_id not added before Client #2) | HIGH | CRITICAL | Block Client #2 until tenant isolation is live. |
| Deployment without staging validation | LOW | HIGH | GCP staging deployed and validated (2026-02-27). 3 deployment bugs found and fixed. seed_test_data.py for realistic data. 224 tests passing. |
| Git history data leak | ELIMINATED | -- | Public repo history purged 2026-02-25. Keys rotated. Two-repo architecture prevents future leaks. |

---

## TECHNICAL DECISIONS

| Decision | Why | When to Revisit |
|----------|-----|-----------------|
| Streamlit for PC | Pure Python, zero frontend learning curve, internal tool | >10 concurrent receptionists |
| Next.js for Mobile | SSR, TypeScript, SaaS-ready UX | Never (strategic) |
| SQLite | Zero-config, single file, sufficient for <15 users | Client #3 or >20 users |
| Hybrid Monolith | No network latency for PC, simpler deployment | True multi-tenant SaaS |
| services/ package | `__init__.py` re-exports preserve all import paths | Stable |

---

## VERIFIED IMPLEMENTATIONS

### Security
| Feature | Status |
|---------|--------|
| `.env` for secrets | Done |
| bcrypt passwords | Done |
| Rate limiting (5/min login) | Done |
| Session cleanup (startup + beacon) | Done |
| CORS hardening (explicit whitelist) | Done |
| Endpoint auth (JWT on all sensitive) | Done |
| RBAC enforcement (`require_role()`) | Done |
| JWT revocation (session-based) | Done |
| Error sanitization + global handler | Done |
| Security headers middleware (VULN-09) | Done |

### Performance
| Feature | Status |
|---------|--------|
| `@st.cache_data` TTL-based | Done |
| WAL mode SQLite | Done |
| Rotating logs | Done |
| N+1 query fix (batch room fetch) | Done |
| Date query bounds (365-day limit) | Done |
| Database indexes | Done |
| Vision hardening (5MB + 30s timeout) | Done |
| Occupancy map lower bound (PERF-003) | Done |
| Remove time.sleep() (PERF-11) | Done |

### Testing
| Feature | Status |
|---------|--------|
| Pre-deployment test suite (224 tests, 22 files) | Done |
| StaticPool fix for in-memory SQLite + FastAPI threading | Done |
| Auth API tests (login, refresh, logout, revocation, rate-limit) | Done |
| Auth service tests (login, sessions, password hashing) | Done |
| Reservation API + service tests (CRUD, cancel, search, weekly) | Done |
| Reservation analytics tests (daily/range status, monthly view) | Done |
| Overbooking + parking capacity tests | Done |
| Guest API + service tests (CRUD, billing, search, linking) | Done |
| Room API + service tests (CRUD, categories, availability, RBAC) | Done |
| iCal service + API tests (sync, export, edge cases, background) | Done |
| Calendar API tests (events, occupancy, summary) | Done |
| Pricing tests (calculation, seasons, corporate discount) | Done |
| Schema validation tests (Pydantic models) | Done |
| Security tests (JWT, bcrypt, RBAC) | Done |
| Settings API + service tests (hotel name, parking, property) | Done |
| Users API tests (CRUD, roles, session logs) | Done |
| DB integrity tests (FKs, unique constraints, nullable) | Done |
| FEAT-LINK-01 tests (auto check-in, duplicate prevention) | Done |
| Tier 3-5 tests (analytics, AI, infra) — ~69 remaining | Backlog |

### Structure
| Feature | Status |
|---------|--------|
| services.py → services/ package (STRUCT-05) | Done |
| app.py split into components/ + helpers/ (STRUCT-04) | Done |
| Mobile reservation page → 4 components (STRUCT-06) | Done |
| Admin pages use API (V8, V9) | Done |
| ai_tools through service layer (V2-V3) | Done |
| Centralized api.ts + useAuth hook (STRUCT-08) | Done |
| All endpoints pass `db` to services (BUG-PRICING-02) | Done |
| FastAPI uses `session_factory()` not `SessionLocal` (BUG-SESSION-01) | Done |
| CORS middleware outermost + global handler CORS (BUG-CORS-01) | Done |
| Date-range overbooking prevention (BUG-OVERBOOKING-01) | Done |
| All UIs display `internal_code` not `room_id` (BUG-ROOMNAME-01) | Done |
| Multi-category room selection (FEAT-MULTICATEGORY) | Done |
| Pydantic response schemas validated (BUG-PRICING-01) | Done |
| Property model synced with DB schema (FEAT-REQ-01) | Done |
| Arrival time picker in mobile form (FEAT-REQ-02) | Done |
| Property settings endpoint + confirmation display (FEAT-REQ-03) | Done |
| iCal import from Booking.com/Airbnb feeds (FEAT-ICAL-01) | Done |
| iCal export .ics for OTAs to pull (FEAT-ICAL-02) | Done |
| Background auto-sync every 15 min (FEAT-ICAL-03) | Done |
| iCal admin UI in Configuracion page (FEAT-ICAL-04) | Done |
| Source dropdown: Facebook, Instagram, Google added (FEAT-ICAL-05) | Done |
| PC admin token key fix — `api_token` consistent (BUG-TOKEN-PC-01) | Done |
| PC login JWT includes `role` + `sid` (BUG-TOKEN-PC-02) | Done |
| Light theme — both frontends white bg + black text (FEAT-THEME-01) | Done |
| Monthly room sheet — Gantt-style room×day grid (FEAT-FICHA-01) | Done |
| Source distribution bar chart by booking channel (FEAT-FICHA-02) | Done |
| Occupancy trend area chart — daily % (FEAT-FICHA-03) | Done |
| Parking utilization progress bars (FEAT-FICHA-04) | Done |
| Revenue heatmap by room×month in Resumen tab (FEAT-FICHA-05) | Done |
| Smart Reservation ↔ Check-in linking (FEAT-LINK-01) | Done |

---

## CHANGELOG

| Date | Change | Author |
|------|--------|--------|
| 2026-01-30 | Initial version | Claude Desktop |
| 2026-01-31 | Added pricing system (client types, seasons, contracts) | Claude Desktop |
| 2026-02-03 | Phase 1 (Database, Backend, Frontend PC/Mobile) DONE | Antigravity |
| 2026-02-04 | Security: CORS whitelist, endpoint auth (VULN-002, VULN-003) | Claude Opus 4.5 |
| 2026-02-04 | Performance: N+1 queries, date bounds, DB indexes (PERF-001, 002, 006) | Claude Opus 4.5 |
| 2026-02-04 | Code quality: TOKEN-01 (centralized keys), ZOMBIE-01/02 (cleanup) | Claude Opus 4.5 |
| 2026-02-05 | Architecture: V8/V9 (admin→API), V2-V3 (ai_tools→service layer), PERF-004 (pagination) | Claude Opus 4.5 |
| 2026-02-06 | Security: VULN-005 (RBAC), VULN-004 (JWT revocation), VULN-007 (error sanitization) | Claude Opus 4.6 |
| 2026-02-06 | Architecture: V1 (AuthService.login), PERF-08-10 (vision hardening), global exception handler | Claude Opus 4.6 |
| 2026-02-08 | **STRUCT-05**: Extracted `services.py` (1379 LOC) → `services/` package (8 modules) | Claude Opus 4.6 |
| 2026-02-08 | **STRUCT-04**: Split `app.py` (1400 LOC) → orchestrator (116 LOC) + `components/` + `helpers/` (10 modules) | Claude Opus 4.6 |
| 2026-02-08 | **PERF-003**: Occupancy map SQL optimization (lower bound filter) | Claude Opus 4.6 |
| 2026-02-08 | **PERF-11**: Removed `time.sleep()` from reservation flow | Claude Opus 4.6 |
| 2026-02-08 | **VULN-09**: Added security headers middleware (X-Content-Type-Options, X-Frame-Options, etc.) | Claude Opus 4.6 |
| 2026-02-08 | **STRUCT-06**: Split mobile `page.tsx` (750 LOC) → orchestrator (286 LOC) + 4 components | Claude Opus 4.6 |
| 2026-02-08 | Docs consolidation: retired TECHNICAL_BASELINE_REPORT (merged into this file) | Claude Opus 4.6 |
| 2026-02-08 | **STRUCT-08**: Route all fetch() through `api.ts` + adopt `useAuth` hook across pages | Claude Opus 4.6 |
| 2026-02-09 | **BUG-PRICING-01**: Fixed missing `currency` field in `pricing_service.py` (ResponseValidationError on every pricing call) | Claude Opus 4.6 |
| 2026-02-09 | **BUG-PRICING-02**: Fixed `pricing.py` endpoint not passing `db` to `get_client_types()` (SQLAlchemy identity map crash) | Claude Opus 4.6 |
| 2026-02-09 | **BUG-PC-FORM-01**: Fixed PC reservation form — category/room selectors were inside `st.form()`, never triggering reruns | Claude Opus 4.6 |
| 2026-02-09 | **FEAT-MULTICATEGORY**: Multi-category room selection in both PC and mobile frontends. Rooms grouped by category, per-category pricing. | Claude Opus 4.6 |
| 2026-02-10 | **BUG-SESSION-01**: Fixed `scoped_session` concurrency — `deps.py` now uses `session_factory()`. Eliminated "identity map is no longer valid" and "concurrent operations" errors. | Claude Opus 4.6 |
| 2026-02-10 | **BUG-CORS-01**: Fixed CORS middleware ordering (outermost) + added CORS headers to global exception handler. Eliminated "Failed to fetch" browser errors. | Claude Opus 4.6 |
| 2026-02-10 | **BUG-OVERBOOKING-01**: Added `get_range_status()` + `/rooms/status?check_in&check_out` params. Mobile re-fetches rooms on date change. Prevents double-booking. | Claude Opus 4.6 |
| 2026-02-10 | **BUG-ROOMNAME-01**: All UIs now display `internal_code` (e.g. `DF-01`) instead of `room_id` (e.g. `los-monges-room-001`). Fixed in: weekly view, daily view, reservation lists (PC + mobile), calendar. | Claude Opus 4.6 |
| 2026-02-12 | **BUG-ROOMNAME-02**: AI agent tools now display `internal_code` in all 4 tool responses. Fixed `search_reservations()`, `get_reservations_in_range()`, `search_checkins()` to include `room_code`. | Claude Opus 4.6 |
| 2026-02-12 | **PERF-10**: Shared `requests.Session()` in `api_client.py` for TCP connection reuse across all PC admin pages (Admin Habitaciones, Admin Users, Asistente IA). | Claude Opus 4.6 |
| 2026-02-12 | **FEAT-REQ-01**: Fixed `Property` model — synced with actual DB schema (22 columns). Was out of sync (had JSON `settings` column). | Claude Opus 4.6 |
| 2026-02-12 | **FEAT-REQ-02**: Added arrival time picker to mobile reservation form. Fixed `arrival_time` schema type (`datetime` → `time`). | Claude Opus 4.6 |
| 2026-02-12 | **FEAT-REQ-03**: Added `/settings/property-settings` endpoint. Reservation confirmation now shows check-in/out times + breakfast policy. | Claude Opus 4.6 |
| 2026-02-13 | **FEAT-ICAL-01**: iCal import — `ICalService.sync_feed()` pulls .ics from Booking.com/Airbnb URLs, upserts reservations with `source`/`external_id`. New `ICalFeed` model + `ical_feeds` table. | Claude Opus 4.6 |
| 2026-02-13 | **FEAT-ICAL-02**: iCal export — `GET /ical/export/{room_id}.ics` and `/ical/export/all.ics` serve .ics calendars for OTAs to pull. | Claude Opus 4.6 |
| 2026-02-13 | **FEAT-ICAL-03**: Background auto-sync every 15 min via FastAPI lifespan + `asyncio.to_thread()`. Replaces deprecated `@app.on_event("startup")`. | Claude Opus 4.6 |
| 2026-02-13 | **FEAT-ICAL-04**: Admin iCal UI in `09_Configuracion.py` — feed CRUD, per-feed/bulk sync, export URL display. | Claude Opus 4.6 |
| 2026-02-13 | **FEAT-ICAL-05**: Source dropdowns updated — Facebook, Instagram, Google added to both mobile and PC frontends. | Claude Opus 4.6 |
| 2026-02-13 | **BUG-TOKEN-PC-01**: Fixed PC admin pages (Users, Habitaciones) — token key mismatch `access_token` → `api_token`. Pages now send auth header correctly. | Claude Opus 4.6 |
| 2026-02-13 | **BUG-TOKEN-PC-02**: Fixed PC login JWT payload — added `role` and `sid` for proper RBAC + session revocation. Reordered `log_login()` before token creation. | Claude Opus 4.6 |
| 2026-02-13 | **FEAT-THEME-01**: Light theme migration — 13 mobile files + 2 PC files. Dark glassmorphism → clean white/gray backgrounds, black text, colored accents preserved. Streamlit config.toml added. | Claude Opus 4.6 |
| 2026-02-15 | **FEAT-FICHA-01**: Monthly room sheet — Gantt-style room×day matrix in Admin Habitaciones "Ficha Mensual" tab. 5 new backend service methods + 5 new API endpoints. HTML/CSS renderer with sticky columns, color-coded cells, today highlight. | Claude Opus 4.6 |
| 2026-02-15 | **FEAT-FICHA-02/03/04**: Visualization tools — source distribution bar chart, occupancy trend area chart, parking utilization progress bars. All below the monthly grid in Ficha Mensual tab. | Claude Opus 4.6 |
| 2026-02-15 | **FEAT-FICHA-05**: Revenue heatmap — room×month HTML table with green gradient intensity in Resumen tab. Annual totals per room. | Claude Opus 4.6 |
| 2026-02-16 | **FEAT-LINK-01**: Smart Reservation ↔ Check-in linking — document scan in "Nueva Reserva" auto-creates linked CheckIn, "Vincular a Reserva" dropdown in "Ficha de Cliente", duplicate prevention by document_number, mobile includes identity fields. Added `reservation_id` FK to CheckIn table. 6 identity fields in ReservationCreate schema. Both frontends upgraded. | Claude Sonnet 4.5 |
| 2026-02-23 | **TEST-01a**: Pre-deployment test suite — 189 tests across 19 files. StaticPool fix for SQLite threading with FastAPI. Covers auth, reservations, guests, rooms, pricing, calendar, iCal, settings, users, schemas, security, DB integrity, FEAT-LINK-01. | Claude Opus 4.6 |
| 2026-02-23 | **TEST-01b**: Tier 1+2 test expansion — 35 additional tests (→224 total). Reservation analytics (daily/range/monthly status), overbooking/parking capacity, iCal API endpoints, iCal edge cases (malformed, datetime, zero-stay), background sync, guest update + billing history, reservation update + weekly view. | Claude Opus 4.6 |
| 2026-02-23 | **INFRA-01**: Remote management API — `/admin/backups` (list, trigger), `/admin/logs/errors`, `/admin/deploy-log`, `/admin/system-info`. All require admin role. New `admin.py` endpoint file. | Claude Opus 4.6 |
| 2026-02-23 | **INFRA-02**: Tailscale VPN setup guide (`scripts/setup_tailscale.md`) for remote SSH access through NAT. | Claude Opus 4.6 |
| 2026-02-23 | **INFRA-03**: Linux systemd service manager (`scripts/service_control_linux.sh`) — start/stop/restart/logs for hotel-backend, hotel-pc, hotel-mobile. | Claude Opus 4.6 |
| 2026-02-23 | **INFRA-04**: GCP staging environment — `scripts/setup_gcp_staging.sh` + `setup_gcp_staging.md`. e2-small VM in southamerica-east1 (~$16/mo, $300 free credits). | Claude Opus 4.6 |
| 2026-02-23 | **INFRA-05**: Test data generator (`scripts/seed_test_data.py`) — 80-100 reservations, 40-50 check-ins, 100+ sessions, 4-6 iCal feeds. Weighted random distributions. Supports --dry-run and --reset. | Claude Opus 4.6 |
| 2026-02-25 | **REPO-01**: Two-repo architecture — public (`sistema-hotel-m` / origin) for deployment, private (`hotel-PMS-dev` / private) for development. Internal docs on `private/dev` branch only. | Claude Opus 4.6 |
| 2026-02-25 | **REPO-02**: Sensitive data redaction — API keys and JWT secrets redacted from tracked files. Public repo history purged (single clean commit). | Claude Opus 4.6 |
| 2026-02-25 | **REPO-03**: Internal content removal — claude_audit/, PROJECT_CONTEXT.md, debug scripts, dev configs removed from public repo via `.gitignore` + `git rm --cached`. | Claude Opus 4.6 |
| 2026-02-27 | **DEPLOY-01**: First GCP staging deployment — VM `hotel-munich-staging` (e2-small, southamerica-east1-a, IP 34.39.241.69). All 3 services running via systemd. | Claude Opus 4.6 |
| 2026-02-27 | **BUG-SEED-01**: Fixed `seed_monges.py` — removed reference to nonexistent `buildings` table. | Claude Opus 4.6 |
| 2026-02-27 | **BUG-INITDB-01**: Fixed `database.py` `init_db()` — removed legacy Excel migration code that used old Room schema fields (`type`, `status`). | Claude Opus 4.6 |
| 2026-02-27 | **BUG-NAN-NIGHTS-01**: Fixed NaN nights display in mobile reservation form — `RoomSelection.tsx` checkIn onChange passed `checkOut: undefined` via spread; `calculateNights()` hardened with guard clause + timezone-safe date parsing. | Claude Opus 4.6 |
| 2026-02-27 | **BUG-SEED-02**: Fixed `seed_monges.py` — room categories missing `active=1`, causing `/rooms/categories` API to return empty array (filter `WHERE active=1` excluded all NULL rows). | Claude Opus 4.6 |

---

**END OF PROJECT CONTEXT**
