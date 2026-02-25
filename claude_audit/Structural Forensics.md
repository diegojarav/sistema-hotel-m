# STRUCTURAL FORENSICS AUDIT - Hotel Munich PMS

**Audit Date:** 2026-02-04
**Branch:** feature/fastapi-agentes
**Auditor:** Claude Code (Opus 4.5)

---

## EXECUTIVE SUMMARY

> **STATUS UPDATE (2026-02-25):** All 3 critical and all 8 high-severity findings have been fully resolved. Exposed credentials were rotated and git history purged. `.next/` was removed from git. `app.py` was split from 1,402 LOC to 116 LOC orchestrator + 10 modules. `services.py` was extracted into 8-module package. Mobile page split into 4 components. All token keys consolidated. All fetch() calls routed through `api.ts`. Admin pages migrated to API. This document is retained as the historical audit trail.

| Area | Original Grade (2026-02-04) | Current Grade (2026-02-25) |
|------|---------------------------|---------------------------|
| Backend | B+ | **A** |
| Frontend PC | C | **A-** |
| Frontend Mobile | B- | **A** |

**Total Findings:** 38 issues identified
**Critical:** 3 (ALL RESOLVED) | **High:** 8 (ALL RESOLVED) | **Medium:** 15 (13 RESOLVED) | **Low:** 12 (ALL RESOLVED)
**Remaining backlog:** STRUCT-12 (snake_case rename), STRUCT-13 (English constants)

### Resolution Summary

| # | Original Severity | Issue | Resolution | Date |
|---|-------------------|-------|------------|------|
| 1 | CRITICAL | Exposed API Credentials | Keys rotated, .env in .gitignore, public repo history purged | 2026-02-04, purge 2026-02-25 |
| 2 | CRITICAL | .next/ in git (289 MB) | `git rm -r --cached`, added to .gitignore | 2026-02-04 |
| 3 | CRITICAL | Incomplete git migration | Migration committed | 2026-02-04 |
| 4 | HIGH | God file app.py (1,402 LOC) | Split to orchestrator 116 LOC + components/ + helpers/ (STRUCT-04) | 2026-02-08 |
| 5 | HIGH | services.py at threshold (1,181 LOC) | Extracted to services/ package, 8 modules (STRUCT-05) | 2026-02-08 |
| 6 | HIGH | Monolithic page.tsx (749 LOC) | Split to 286 LOC + 4 components (STRUCT-06) | 2026-02-08 |
| 7 | HIGH | Token key inconsistency | Centralized in src/constants/keys.ts (TOKEN-01) | 2026-02-04 |
| 8 | HIGH | Direct fetch() bypass | All routed through api.ts (STRUCT-08) | 2026-02-08 |
| 9 | HIGH | sys.path.append import | Config page uses API client | 2026-02-13 |
| 10 | HIGH | Duplicate import | Removed | 2026-02-04 |
| 11 | HIGH | Migration in database.py | Extracted to init_db.py | 2026-02-04 |

---

## CRITICAL FINDINGS (Blocks Production)

### 1. Exposed API Credentials
**Location:** `backend/.env`
**Pattern:** Security Vulnerability
**Evidence:**
```
GOOGLE_API_KEY=REDACTED_KEY_ROTATED
JWT_SECRET_KEY=REDACTED_KEY_ROTATED
```
**Fix:** Rotate credentials immediately, move to system environment variables or secrets manager
**Effort:** Quick

### 2. Build Artifacts Committed to Git
**Location:** `frontend_mobile/.next/` (289 MB)
**Pattern:** Repository Bloat
**Evidence:** Entire Next.js build directory in version control
**Fix:**
```bash
git rm -r --cached frontend_mobile/.next/
echo "frontend_mobile/.next/" >> .gitignore
```
**Effort:** Quick

### 3. Incomplete Git Migration
**Location:** Project root
**Pattern:** Orphaned Files
**Evidence:** 21 files marked as deleted (D flag) but changes not committed:
- `api/`, `app.py`, `database.py`, `services.py`, `schemas.py`, `hotel.db`, etc.
**Fix:** Commit migration or revert: `git add -A && git commit -m "refactor: complete v4.0 migration"`
**Effort:** Quick

---

## HIGH SEVERITY FINDINGS (Major Tech Debt)

### 4. Frontend PC: God File - app.py
**Location:** `frontend_pc/app.py` (1,402 LOC)
**Pattern:** God File + Mixed Concerns
**Evidence:**
- UI rendering (450+ lines CSS/HTML)
- Business logic (price calculation)
- Database operations
- Authentication
- 23 functions at module level
**Fix:** Split into:
```
frontend_pc/
├── app.py (main, 300 LOC max)
├── ui_components/ (calendar, forms)
├── styles/ (CSS extraction)
└── constants.py
```
**Effort:** Refactor

### 5. Backend: services.py at Threshold
**Location:** `backend/services.py` (1,181 LOC)
**Pattern:** God File Warning
**Evidence:** 7 service classes, 28+ imports
**Fix:** Extract to module structure:
```
backend/services/
├── __init__.py
├── auth.py (77 LOC)
├── reservations.py (466 LOC)
├── guests.py (152 LOC)
├── pricing.py (142 LOC)
├── rooms.py (196 LOC)
└── settings.py (77 LOC)
```
**Effort:** Refactor

### 6. Mobile: Monolithic Page Component
**Location:** `frontend_mobile/app/dashboard/reservations/new/page.tsx` (749 LOC)
**Pattern:** God File
**Evidence:** 8 distinct UI sections in single file
**Fix:** Extract components:
- `DocumentScannerSection`
- `ClientDataForm`
- `ParkingSection`
- `DateRangeSection`
- `CategorySelection`
- `RoomSelection`
- `PriceSummary`
**Effort:** Medium

### 7. Mobile: Inconsistent Token Key Names
**Location:** Multiple files
**Pattern:** Code Inconsistency
**Evidence:**
```typescript
// Three different constants for same concept:
'hotel_munich_access_token'  // pages, pricing.ts, rooms.ts
'hms_access_token'           // auth.ts
'ACCESS_TOKEN_KEY'           // dashboard/login
```
**Fix:** Create single source of truth in `src/constants/keys.ts`
**Effort:** Medium

### 8. Mobile: Direct fetch() Bypassing API Wrapper
**Location:** 5 page components
**Pattern:** Architecture Violation
**Evidence:**
- `/app/login/page.tsx` (lines 13-33)
- `/app/dashboard/calendar/page.tsx` (lines 60-94)
- `/app/dashboard/chat/page.tsx` (lines 69-107)
- `/app/dashboard/availability/page.tsx`
- `/app/dashboard/reservations/new/page.tsx` (line 186)
**Fix:** Route all API calls through `src/services/api.ts`
**Effort:** Medium

### 9. Frontend PC: Import Anti-Pattern
**Location:** `frontend_pc/pages/09_Configuracion.py:6`
**Pattern:** Fragile Import
**Evidence:**
```python
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../backend')))
```
**Fix:** Use proper Python package structure or relative imports
**Effort:** Medium

### 10. Backend: Duplicate Import
**Location:** `backend/services.py:13-14`
**Pattern:** Dead Code
**Evidence:** `from sqlalchemy import and_, or_` imported twice
**Fix:** Remove duplicate import
**Effort:** Quick

### 11. Backend: Migration Code in database.py
**Location:** `backend/database.py:332-431`
**Pattern:** Mixed Concerns
**Evidence:** Excel import and migration logic in DB model file
**Fix:** Extract to `backend/init_db.py`
**Effort:** Medium

---

## MEDIUM SEVERITY FINDINGS (Code Smells)

### 12. Frontend PC: Page File Naming Violations
**Location:** `frontend_pc/pages/`
**Pattern:** Naming Convention
**Evidence:**
- `04_Asistente_IA.py` should be `04_asistente_ia.py`
- `09_Configuracion.py` should be `09_configuracion.py`
- `98_Admin_Habitaciones.py` should be `98_admin_habitaciones.py`
- `99_Admin_Users.py` should be `99_admin_users.py`
**Fix:** Rename files to snake_case
**Effort:** Quick

### 13. Frontend PC: Inconsistent Constant Naming
**Location:** `frontend_pc/app.py:113-127`
**Pattern:** Naming Convention
**Evidence:**
```python
LISTA_HABITACIONES_LEGACY  # Should be LEGACY_ROOM_LIST
LISTA_TIPOS_LEGACY          # Should be LEGACY_ROOM_TYPES
MESES_ES                    # Should be SPANISH_MONTHS
DIAS_SEMANA                 # Should be WEEKDAY_NAMES
```
**Fix:** Rename to UPPER_SNAKE_CASE English
**Effort:** Quick

### 14. Frontend PC: Conditional Import
**Location:** `frontend_pc/app.py:548`
**Pattern:** Import Anti-Pattern
**Evidence:**
```python
# Inside login form conditional block:
from api.core.security import create_access_token
```
**Fix:** Move to module-level imports
**Effort:** Quick

### 15. Frontend PC: CSS Duplication
**Location:** `frontend_pc/app.py:132-222, 344-441`
**Pattern:** Code Duplication
**Evidence:** Calendar CSS defined twice with slight differences
**Fix:** Extract to single `styles/calendar.css`
**Effort:** Medium

### 16. Frontend PC: Direct SQLite in Admin Page
**Location:** `frontend_pc/pages/98_Admin_Habitaciones.py:93-96`
**Pattern:** Inconsistent Data Access
**Evidence:** Uses raw `sqlite3` instead of SQLAlchemy SessionLocal
**Fix:** Standardize to use SessionLocal
**Effort:** Medium

### 17. Mobile: Duplicate getAuthHeaders()
**Location:** `frontend_mobile/src/services/rooms.ts`, `auth.ts`
**Pattern:** Code Duplication
**Evidence:** Same function defined in both files
**Fix:** Export from auth.ts only
**Effort:** Quick

### 18. Mobile: Missing Route Boundaries
**Location:** `frontend_mobile/app/`
**Pattern:** Next.js Convention
**Evidence:** No `loading.tsx` or `error.tsx` in route groups
**Fix:** Add boundary components for better UX
**Effort:** Medium

### 19. Mobile: Duplicate Login Structure
**Location:** `frontend_mobile/src/app/login/` AND `frontend_mobile/app/login/`
**Pattern:** Code Duplication
**Evidence:** Login page exists in two locations
**Fix:** Remove `src/app/login/`, keep only `app/login/`
**Effort:** Quick

### 20. Mobile: Calendar Page at Threshold
**Location:** `frontend_mobile/app/dashboard/calendar/page.tsx` (360 LOC)
**Pattern:** Large Component
**Evidence:** Approaching but not exceeding limit
**Fix:** Could extract `ReservationCard` component
**Effort:** Medium

### 21. Backend: Hardcoded URL
**Location:** `frontend_pc/app.py:34`
**Pattern:** Configuration
**Evidence:**
```python
AGENT_QUERY_URL = "http://localhost:8000/api/v1/agent/query"
```
**Fix:** Move to environment variable
**Effort:** Quick

### 22-26. Mobile Services Bypass api.ts
**Location:** Multiple service files
**Pattern:** Architecture Bypass
**Evidence:**
- `rooms.ts` (lines 64-120): raw fetch()
- `auth.ts` (lines 35-106): raw fetch()
- `pricing.ts` (lines 34-73): raw fetch()
**Fix:** Route through api.ts wrapper
**Effort:** Medium

---

## LOW SEVERITY FINDINGS (Nitpicks)

### 27. Backend: Test Coverage
**Location:** `backend/tests/`
**Pattern:** Missing Tests
**Evidence:** Only 4 test files (conftest.py, test_pricing.py, verify_mobile_api.py, verify_parking.py)
**Fix:** Add comprehensive unit tests (target >80% coverage)
**Effort:** Refactor

### 28. Frontend PC: No Cache in Admin Pages
**Location:** `frontend_pc/pages/98_*.py`, `99_*.py`
**Pattern:** Performance
**Evidence:** Direct DB calls without @st.cache_data
**Fix:** Add caching for `get_all_users()`, `get_room_statistics()`
**Effort:** Medium

### 29. Backend: Potential Unused File
**Location:** `backend/migrate_sessions.py`
**Pattern:** Dead Code
**Evidence:** Migration utility - verify if still needed post-v4.0
**Fix:** Remove if obsolete
**Effort:** Quick

### 30-38. Minor Configuration/Documentation Issues
- Missing ESLint naming convention rules (Mobile)
- .pytest_cache/ directories present
- Page numbering gaps (05-08, 10-97 unused)
- Various minor cleanups

---

## TOP 5 FILES -- CURRENT STATUS (All Resolved)

| Priority | File | Original Issue | Current Status |
|----------|------|---------------|----------------|
| 1 | `frontend_pc/app.py` | God file 1,402 LOC | **RESOLVED**: 116 LOC orchestrator + components/ + helpers/ |
| 2 | `backend/services.py` | At threshold 1,181 LOC | **RESOLVED**: services/ package with 8 modules |
| 3 | `mobile reservations/new/page.tsx` | Monolithic 749 LOC | **RESOLVED**: 286 LOC + 4 components |
| 4 | `backend/.env` | Exposed credentials | **RESOLVED**: .gitignore + keys rotated + history purged |
| 5 | `frontend_mobile/.next/` | 289 MB committed | **RESOLVED**: removed from git |

---

## QUICK-WIN LIST (Fixes Under 5 Minutes)

1. **Rotate API credentials** - Generate new keys, update .env
2. **Remove .next/ from git** - `git rm -r --cached frontend_mobile/.next/`
3. **Remove duplicate import** - services.py line 13-14
4. **Rename page files** - 4 files to snake_case
5. **Move conditional import** - app.py line 548 to top
6. **Delete duplicate login** - src/app/login/
7. **Fix constant names** - 4 constants in app.py

---

## SEVERITY SUMMARY

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 3 | Blocks production, security risk |
| HIGH | 8 | Major tech debt, architecture violations |
| MEDIUM | 15 | Code smells, inconsistencies |
| LOW | 12 | Nitpicks, minor improvements |
| **TOTAL** | **38** | |

---

## NAMING CONVENTION VIOLATIONS SUMMARY

### Python Files (Expected: snake_case.py)
| File | Current | Should Be |
|------|---------|-----------|
| `04_Asistente_IA.py` | PascalCase | `04_asistente_ia.py` |
| `09_Configuracion.py` | PascalCase | `09_configuracion.py` |
| `98_Admin_Habitaciones.py` | PascalCase | `98_admin_habitaciones.py` |
| `99_Admin_Users.py` | PascalCase | `99_admin_users.py` |

### TypeScript Naming (Mostly Correct)
- Files: camelCase.ts (services), PascalCase.tsx (components)
- Functions: camelCase
- Classes/Interfaces: PascalCase
- Constants: UPPER_SNAKE_CASE (with 3 inconsistent token keys)

### Python Constants (Expected: UPPER_SNAKE_CASE)
| Current | Should Be |
|---------|-----------|
| `LISTA_HABITACIONES_LEGACY` | `LEGACY_ROOM_LIST` |
| `LISTA_TIPOS_LEGACY` | `LEGACY_ROOM_TYPES` |
| `MESES_ES` | `SPANISH_MONTHS` |
| `DIAS_SEMANA` | `WEEKDAY_NAMES` |

---

## RECOMMENDED REMEDIATION ORDER

### Sprint 1 (Immediate - Security & Cleanup)
1. Rotate exposed API credentials
2. Remove .next/ from Git
3. Commit or revert orphaned root files
4. Fix quick-win naming issues

### Sprint 2 (Architecture)
5. Split frontend_pc/app.py into modules
6. Consolidate mobile token key names
7. Route mobile API calls through api.ts
8. Extract mobile NewReservationPage components

### Sprint 3 (Tech Debt)
9. Extract backend/services.py to module structure
10. Add comprehensive test coverage
11. Remove migration code from database.py
12. Standardize data access patterns

---

## VERIFICATION PLAN

After implementing fixes:

1. **Backend:** `uvicorn api.main:app --reload` - Verify all 36 endpoints respond
2. **Frontend PC:** `streamlit run app.py` - Verify all pages load
3. **Frontend Mobile:** `npm run build && npm run start` - Verify no build errors
4. **Git:** `git status` - Verify clean working tree
5. **Security:** Verify old API keys are revoked in Google Cloud Console

---

**END OF AUDIT REPORT**