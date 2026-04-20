"""End-to-end UX test for v1.7.0 Phase 4 — hits real API on localhost:8000."""
import sys
from datetime import date, timedelta

import requests

BASE = "http://127.0.0.1:8000/api/v1"
results = []


def section(name):
    print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")


def check(label, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, label, detail))
    print(f"  [{status}] {label}" + (f" -- {detail}" if detail else ""))
    return cond


def login(user, pwd):
    r = requests.post(f"{BASE}/auth/login", data={"username": user, "password": pwd})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ==========================================
# Hotel A -- meals disabled (zero-regression gate)
# ==========================================
section("Hotel A -- default (meals disabled)")

r = requests.get(f"{BASE}/settings/meals-config")
cfg = r.json()
check("Public meals-config GET returns enabled=false", not cfg["meals_enabled"], str(cfg))
check("Mode is null when disabled", cfg["meal_inclusion_mode"] is None)

admin_hdr = login("admin", "admin123")
recep_hdr = login("recepcion", "recep123")

# Kitchen report returns enabled=false
r = requests.get(f"{BASE}/reportes/cocina", headers=admin_hdr)
check("GET /reportes/cocina returns 200 when disabled", r.status_code == 200, f"status={r.status_code}")
check("Kitchen report enabled=false by default", not r.json().get("enabled"))
check("Kitchen rooms empty when disabled", r.json().get("rooms") == [])

# PDF endpoint 404 when disabled
r = requests.get(f"{BASE}/reportes/cocina/pdf", headers=admin_hdr)
check("PDF endpoint 404 when disabled", r.status_code == 404, r.text[:100])

# AI tool returns disabled message
r = requests.post(f"{BASE}/agent/query",
                  headers=admin_hdr,
                  json={"prompt": "Cuantos desayunos hay para manana?"})
if r.status_code == 200:
    body = r.json().get("response", "").lower()
    # Accept any phrasing that signals the service is not available:
    # "no habilitado", "no está habilitado", "no disponible", "no hay", etc.
    disabled_in_reply = "habilitado" in body or "no disponible" in body or "no hay" in body
    check("AI agent 'desayunos' => disabled/empty reply", disabled_in_reply, body[:200])
else:
    check(f"AI agent endpoint reachable (got {r.status_code})", False, r.text[:200])

# Recepcion can GET kitchen (whitelisted)
r = requests.get(f"{BASE}/reportes/cocina", headers=recep_hdr)
check("Recepcion allowed on /reportes/cocina", r.status_code == 200, f"status={r.status_code}")

# Non-admin 403 on PUT meals-config
r = requests.put(f"{BASE}/settings/meals-config",
                 headers=recep_hdr,
                 json={"meals_enabled": True, "meal_inclusion_mode": "INCLUIDO"})
check("Non-admin 403 on PUT meals-config", r.status_code == 403, f"status={r.status_code}")

# ==========================================
# Hotel B -- INCLUIDO mode
# ==========================================
section("Hotel B -- INCLUIDO mode (breakfast in rate)")

r = requests.put(f"{BASE}/settings/meals-config",
                 headers=admin_hdr,
                 json={"meals_enabled": True, "meal_inclusion_mode": "INCLUIDO"})
check("Admin enables INCLUIDO mode", r.status_code == 200, f"status={r.status_code}")
check("Config reflects INCLUIDO mode", r.json()["meal_inclusion_mode"] == "INCLUIDO")

# CON_DESAYUNO seeded automatically
r = requests.get(f"{BASE}/meal-plans", headers=admin_hdr)
plans = r.json()
codes = {p["code"] for p in plans}
check("SOLO_HABITACION seeded", "SOLO_HABITACION" in codes)
check("CON_DESAYUNO auto-seeded for INCLUIDO", "CON_DESAYUNO" in codes)
con_des = next((p for p in plans if p["code"] == "CON_DESAYUNO"), None)
if con_des:
    check("Auto-seeded CON_DESAYUNO has 0 surcharge (INCLUIDO)",
          con_des["surcharge_per_person"] == 0 and con_des["surcharge_per_room"] == 0)

# Price should NOT change when INCLUIDO
tomorrow = (date.today() + timedelta(days=1)).isoformat()
r = requests.post(f"{BASE}/pricing/calculate",
                  headers=admin_hdr,
                  json={"category_id": "los-monges-estandar", "check_in": tomorrow,
                        "stay_days": 2, "client_type_id": "los-monges-particular",
                        "meal_plan_id": con_des["id"] if con_des else None, "breakfast_guests": 2})
if r.status_code == 200:
    res = r.json()
    mods = res["breakdown"]["modifiers"]
    plan_mods = [m for m in mods if m["name"].startswith("Plan:")]
    check("INCLUIDO => no 'Plan:' modifier row (price unchanged)",
          len(plan_mods) == 0, f"final={res['final_price']}")
else:
    check("Pricing endpoint reachable in INCLUIDO", False, r.text[:200])

# Kitchen report enabled now
r = requests.get(f"{BASE}/reportes/cocina", headers=admin_hdr)
check("Kitchen report enabled in INCLUIDO", r.json().get("enabled") == True)
check("Kitchen report mode=INCLUIDO", r.json().get("mode") == "INCLUIDO")

# ==========================================
# Hotel C -- OPCIONAL_PERSONA
# ==========================================
section("Hotel C -- OPCIONAL_PERSONA (per-pax surcharge)")

r = requests.put(f"{BASE}/settings/meals-config",
                 headers=admin_hdr,
                 json={"meals_enabled": True, "meal_inclusion_mode": "OPCIONAL_PERSONA"})
check("Admin switches to OPCIONAL_PERSONA", r.status_code == 200)

# Create CON_DESAYUNO plan with 30k/pax.
# Make idempotent: if a prior run left one soft-deleted, re-activate instead of re-creating.
TEST_CODE = "TEST_BREAKFAST_OPT"
all_plans = requests.get(f"{BASE}/meal-plans?include_inactive=true", headers=admin_hdr).json()
existing_test = next((p for p in all_plans if p["code"] == TEST_CODE), None)
if existing_test:
    r = requests.put(f"{BASE}/meal-plans/{existing_test['id']}",
                     headers=admin_hdr,
                     json={"name": "Con Desayuno Test",
                           "surcharge_per_person": 30000,
                           "applies_to_mode": "OPCIONAL_PERSONA",
                           "is_active": True})
    check("Admin re-activates existing OPCIONAL_PERSONA plan", r.status_code == 200,
          f"status={r.status_code} body={r.text[:200]}")
    new_plan = r.json() if r.status_code == 200 else None
else:
    r = requests.post(f"{BASE}/meal-plans",
                      headers=admin_hdr,
                      json={"code": TEST_CODE, "name": "Con Desayuno Test",
                            "surcharge_per_person": 30000, "applies_to_mode": "OPCIONAL_PERSONA"})
    check("Admin creates OPCIONAL_PERSONA plan", r.status_code == 201,
          f"status={r.status_code} body={r.text[:200]}")
    new_plan = r.json() if r.status_code == 201 else None

# Pricing: 150k x 3 + 2 pax x 3 nts x 30k = 450k + 180k = 630k
if new_plan:
    r = requests.post(f"{BASE}/pricing/calculate",
                      headers=admin_hdr,
                      json={"category_id": "los-monges-estandar", "check_in": tomorrow,
                            "stay_days": 3, "client_type_id": "los-monges-particular",
                            "meal_plan_id": new_plan["id"], "breakfast_guests": 2})
    if r.status_code == 200:
        res = r.json()
        mods = res["breakdown"]["modifiers"]
        plan_mods = [m for m in mods if m["name"].startswith("Plan:")]
        check("OPCIONAL_PERSONA => 'Plan:' modifier row present", len(plan_mods) == 1)
        if plan_mods:
            check("Surcharge = 2 pax x 3 nts x 30 000 = 180 000",
                  plan_mods[0]["amount"] == 180000, f"got {plan_mods[0]['amount']}")
    else:
        check("Pricing endpoint reachable in OPCIONAL_PERSONA", False)

# List filter works (only ACTIVE plans by default)
r = requests.get(f"{BASE}/meal-plans?mode=OPCIONAL_PERSONA", headers=admin_hdr)
if r.status_code == 200:
    codes = {p["code"] for p in r.json()}
    check("Filter mode=OPCIONAL_PERSONA returns SOLO + new",
          "SOLO_HABITACION" in codes and TEST_CODE in codes,
          f"codes={codes}")

# Delete test plan
if new_plan:
    r = requests.delete(f"{BASE}/meal-plans/{new_plan['id']}", headers=admin_hdr)
    check("Admin can soft-delete user plan", r.status_code == 200)

# System plan NOT deletable
solo = next((p for p in plans if p["code"] == "SOLO_HABITACION"), None)
if solo:
    r = requests.delete(f"{BASE}/meal-plans/{solo['id']}", headers=admin_hdr)
    check("System plan (SOLO_HABITACION) cannot be deleted",
          r.status_code == 400, f"status={r.status_code}")

# PDF endpoint works when enabled
r = requests.get(f"{BASE}/reportes/cocina/pdf", headers=admin_hdr)
check("PDF endpoint returns 200 when enabled",
      r.status_code == 200, f"status={r.status_code}")
if r.status_code == 200:
    check("PDF content-type is application/pdf",
          "application/pdf" in r.headers.get("content-type", ""),
          r.headers.get("content-type"))
    check("PDF body starts with %PDF", r.content[:4] == b"%PDF")

# ==========================================
# Disable again to restore default state
# ==========================================
section("Restore default state (disable meals)")

r = requests.put(f"{BASE}/settings/meals-config",
                 headers=admin_hdr,
                 json={"meals_enabled": False})
check("Admin disables meals", r.status_code == 200)
check("Config reflects disabled state", r.json()["meals_enabled"] == False)

# Verify zero-regression -- config now mirrors original default
r = requests.get(f"{BASE}/settings/meals-config")
check("Post-disable: meals_enabled=false", r.json()["meals_enabled"] == False)
check("Post-disable: mode cleared", r.json()["meal_inclusion_mode"] is None)

# ==========================================
# Summary
# ==========================================
section("SUMMARY")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"\n  {passed}/{passed + failed} checks passed")
if failed:
    print("\n  Failed checks:")
    for s, label, detail in results:
        if s == "FAIL":
            print(f"    - {label}" + (f" ({detail})" if detail else ""))
    sys.exit(1)
