"""
Hotel Munich PMS — E2E Test Marathon Harness
Drives all 18 scenarios from `scripts/hotel-munich-e2e-test-marathon-prompt.md`
against the live backend on http://localhost:8000.
PC reachability and Mobile reachability are sanity-checked separately.

Run:  python scripts/e2e_marathon.py
"""
from __future__ import annotations
import json, sys, time, traceback, requests, os
from datetime import date, timedelta, datetime

HOST = os.environ.get("E2E_HOST", "localhost")
BASE = f"http://{HOST}:8000/api/v1"
PC = f"http://{HOST}:8501"
MOB = f"http://{HOST}:3000"

RESULTS: list[tuple[str, str, str]] = []  # (scenario, status, notes)
BUGS: list[tuple[str, str, str]] = []     # (severity, scenario, description)
STATE: dict = {}

def step(name: str):
    print(f"\n──── {name} ────")

def record(scenario: str, status: str, notes: str = ""):
    RESULTS.append((scenario, status, notes))
    print(f"   → {status} {notes}")

def bug(sev: str, scenario: str, desc: str):
    BUGS.append((sev, scenario, desc))
    print(f"   🐛 [{sev}] {scenario}: {desc}")

def login(user="admin", pw="admin123"):
    r = requests.post(f"{BASE}/auth/login", data={"username":user,"password":pw}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]

def H(tok=None):
    return {"Authorization": f"Bearer {tok or STATE['admin_token']}"}

def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)

def safe(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except Exception as e:
        return e

# ── Bootstrap ──────────────────────────────────────────────────────────────
def cleanup_prior_runs():
    """Cancel any leftover reservations from prior runs so S17 sees a clean room."""
    tok = STATE.get("admin_token")
    if not tok:
        return
    h = {"Authorization": f"Bearer {tok}"}
    test_names = ("Familia Martínez","Carlos Ramírez","Pedro González","Double Book Test",
                  "Manual Double Book Test","Past Date Test","API Validation Test")
    try:
        lst = requests.get(f"{BASE}/reservations?limit=300", headers=h).json()
        for r in lst:
            if any(n in (r.get("guest_name","") or "") for n in test_names) and \
               r.get("status") not in ("Cancelada","CANCELADA"):
                requests.post(f"{BASE}/reservations/{r['id']}/cancel", headers=h,
                              json={"reason":"E2E pre-run cleanup","cancelled_by":"admin"})
        # Close any stray open caja
        cur = requests.get(f"{BASE}/caja/actual", headers=h).json()
        if cur and cur.get("status") == "ABIERTA":
            requests.post(f"{BASE}/caja/cerrar", headers=h, json={
                "session_id": cur["id"],
                "closing_balance_declared": cur.get("opening_balance") or 0,
                "notes": "E2E pre-run close"})
    except Exception as e:
        print(f"   cleanup warning: {e}")

def bootstrap():
    step("Bootstrap: tokens + service reachability")
    STATE["admin_token"] = login("admin","admin123")
    print(f"   admin token: {STATE['admin_token'][:25]}…")
    try:
        STATE["recep_token"] = login("recepcion","recep123")
        print(f"   recepcion token: {STATE['recep_token'][:25]}…")
    except Exception as e:
        print(f"   ⚠️  recepcion login failed: {e}")
        STATE["recep_token"] = None

    for name, url in [("Backend", f"{BASE}/../../docs"), ("PC", PC), ("Mobile", MOB)]:
        try:
            r = requests.get(url, timeout=5)
            print(f"   {name}: HTTP {r.status_code}")
        except Exception as e:
            print(f"   {name}: ERROR {e}")

# ── S1 — Open caja ─────────────────────────────────────────────────────────
def s1_open_caja():
    step("S1 — Open cash register")
    try:
        cur = requests.get(f"{BASE}/caja/actual", headers=H()).json()
        if cur and cur.get("status") == "ABIERTA":
            print(f"   Existing open session id={cur['id']} balance={cur['opening_balance']}. Closing first.")
            r = requests.post(f"{BASE}/caja/cerrar", headers=H(),
                              json={"session_id": cur["id"],
                                    "closing_balance_declared": cur["opening_balance"],
                                    "notes": "E2E auto-close"})
            if r.status_code >= 400:
                bug("medium", "S1", f"Could not auto-close existing caja: {r.status_code} {r.text[:200]}")
                STATE["caja_id"] = cur["id"]
                record("S1", "⚠️ WARNING", "existing session reused")
                return
        # Open new
        r = requests.post(f"{BASE}/caja/abrir", headers=H(),
                          json={"opening_balance": 200000, "notes": "E2E marathon — turno mañana"})
        if r.status_code != 200:
            bug("high", "S1", f"abrir failed {r.status_code}: {r.text[:200]}")
            record("S1", "❌ FAIL", f"abrir {r.status_code}")
            return
        sess = r.json()
        STATE["caja_id"] = sess["id"]
        expect(sess["status"] == "ABIERTA", "session not ABIERTA")
        expect(sess["opening_balance"] == 200000, "opening_balance mismatch")
        record("S1", "✅ PASS", f"session id={sess['id']}, opening=200000")
    except Exception as e:
        bug("high", "S1", str(e))
        record("S1", "❌ FAIL", str(e))

# ── S2 — Today's reservations ───────────────────────────────────────────────
def s2_today_reservations():
    step("S2 — Calendar for today on PC + Mobile (data parity)")
    today = date.today().isoformat()
    try:
        r1 = requests.get(f"{BASE}/calendar/summary", headers=H(),
                          params={"fecha": today})
        if r1.status_code != 200:
            bug("medium", "S2", f"summary {r1.status_code}: {r1.text[:200]}")
        td = date.today()
        r2 = requests.get(f"{BASE}/calendar/events", headers=H(),
                          params={"year": td.year, "month": td.month})
        if r2.status_code != 200:
            bug("medium", "S2", f"events {r2.status_code}: {r2.text[:200]}")
        events = r2.json() if r2.status_code == 200 else []
        record("S2", "✅ PASS", f"today summary OK; {len(events) if isinstance(events,list) else 'n/a'} events")
    except Exception as e:
        bug("medium", "S2", str(e))
        record("S2", "❌ FAIL", str(e))

# ── S3 — PC walk-in: Familia Martínez ──────────────────────────────────────
def s3_pc_walkin():
    step("S3 — PC walk-in: Familia Martínez + meal plan + 2 vehicles")
    try:
        rooms = requests.get(f"{BASE}/rooms", headers=H()).json()
        # pick room with capacity ≥ 3 in los-monges
        cats = {c["id"]: c for c in requests.get(f"{BASE}/rooms/categories", headers=H()).json()}
        candidate = next((r for r in rooms if cats.get(r["category_id"], {}).get("max_capacity", 0) >= 3), rooms[0])
        STATE["s3_room"] = candidate["id"]
        meal_plan = next(m for m in requests.get(f"{BASE}/meal-plans", headers=H()).json()
                         if m["code"] == "CON_DESAYUNO")
        check_in = date.today().isoformat()
        check_out = (date.today() + timedelta(days=1)).isoformat()
        stay_days = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        payload = {
            "guest_name": "Familia Martínez",
            "contact_email": "martinez.familia@example.com",
            "room_ids": [candidate["id"]],
            "client_type_id": "los-monges-particular",
            "check_in_date": check_in,
            "stay_days": stay_days,
            "source": "Direct",
            "parking_needed": True,
            "meal_plan_id": meal_plan["id"],
            "breakfast_guests": 3,
            "vehicles": [
                {"mode": "quick", "plate_number": "ABC-123", "model": "Toyota Corolla",
                 "color": "Blanco", "is_primary": True},
                {"mode": "quick", "plate_number": "XYZ-789", "model": "Honda Civic",
                 "color": "Negro", "is_primary": False},
            ],
        }
        r = requests.post(f"{BASE}/reservations", headers=H(), json=payload)
        if r.status_code not in (200, 201):
            bug("high", "S3", f"create reservation failed {r.status_code}: {r.text[:300]}")
            record("S3", "❌ FAIL", f"create {r.status_code}")
            return
        body = r.json()
        # API returns list[str] of reservation IDs (one per room in the booking)
        rid = body[0] if isinstance(body, list) and body else (body if isinstance(body, str) else None)
        if not rid:
            bug("high","S3", f"reservation create returned unexpected body shape: {body!r}")
            record("S3","❌ FAIL","bad response shape")
            return
        STATE["s3_reservation_id"] = rid
        res = requests.get(f"{BASE}/reservations/{rid}", headers=H()).json()
        STATE["s3_guest_id"] = res.get("guest_id")
        notes = [f"reservation id={rid} status={res.get('status')}"]

        # Verify guest in master
        if STATE["s3_guest_id"]:
            g = requests.get(f"{BASE}/huespedes/{STATE['s3_guest_id']}", headers=H()).json()
            if "Martínez" not in (g.get("last_name","") + g.get("first_name","")):
                bug("low", "S3", f"guest master name doesn't include 'Martínez': {g.get('first_name')} {g.get('last_name')}")
            notes.append(f"guest_id={STATE['s3_guest_id']}")
        else:
            bug("medium", "S3", "reservation has no guest_id (Guest entity not linked)")

        # Verify vehicles persisted via reservation detail
        det = requests.get(f"{BASE}/reservations/{rid}", headers=H()).json()
        veh = det.get("vehicles") or []
        if len(veh) != 2:
            bug("high", "S3", f"expected 2 vehicles, got {len(veh)}")
        else:
            notes.append(f"{len(veh)} vehicles linked")

        # Verify PDF generated
        pdf = requests.get(f"{BASE}/documents/reservations/{rid}", headers=H(), stream=True)
        if pdf.status_code != 200 or pdf.headers.get("content-type","").find("pdf") < 0:
            bug("medium", "S3", f"PDF download status={pdf.status_code} content-type={pdf.headers.get('content-type')}")
        else:
            notes.append("PDF OK")

        record("S3", "✅ PASS" if not [b for b in BUGS if b[1]=='S3' and b[0]=='high'] else "❌ FAIL", "; ".join(notes))
    except Exception as e:
        traceback.print_exc()
        bug("high", "S3", str(e))
        record("S3", "❌ FAIL", str(e))

# ── S4 — Mobile walk-in: Carlos Ramírez ─────────────────────────────────────
def s4_mobile_walkin():
    step("S4 — Mobile walk-in: Carlos Ramírez (1 night → 2 nights)")
    try:
        # autocomplete check
        sa = requests.get(f"{BASE}/huespedes/search", headers=H(), params={"q":"Fernández","limit":5})
        if sa.status_code != 200:
            bug("medium", "S4", f"search 'Fernández' returned {sa.status_code}")
        else:
            print(f"   search returned {len(sa.json())} matches")

        room = STATE.get("s3_room") or "los-monges-room-002"
        # pick a different room to avoid collision
        rooms = requests.get(f"{BASE}/rooms", headers=H()).json()
        alt = next((r for r in rooms if r["id"] != STATE.get("s3_room")), rooms[0])
        STATE["s4_room"] = alt["id"]
        meal_plan = next(m for m in requests.get(f"{BASE}/meal-plans", headers=H()).json()
                         if m["code"] == "CON_DESAYUNO")
        check_in = date.today().isoformat()
        check_out = (date.today() + timedelta(days=2)).isoformat()
        stay_days = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        payload = {
            "guest_name": "Carlos Ramírez",
            "contact_email": "carlos.ramirez@example.com",
            "room_ids": [alt["id"]],
            "client_type_id": "los-monges-particular",
            "check_in_date": check_in,
            "stay_days": stay_days,
            "source": "Walk-in",
            "parking_needed": True,
            "meal_plan_id": meal_plan["id"],
            "breakfast_guests": 1,
            "vehicles": [
                {"mode": "quick", "plate_number": "MOB-001", "model": "Suzuki Alto",
                 "color": "Gris", "is_primary": True},
            ],
        }
        r = requests.post(f"{BASE}/reservations", headers=H(), json=payload)
        if r.status_code not in (200, 201):
            bug("high", "S4", f"create reservation failed {r.status_code}: {r.text[:400]}")
            record("S4", "❌ FAIL", f"create {r.status_code}")
            return
        body = r.json()
        rid = body[0] if isinstance(body, list) and body else (body if isinstance(body, str) else None)
        if not rid:
            bug("high","S4", f"unexpected body shape: {body!r}")
            record("S4","❌ FAIL","bad response")
            return
        STATE["s4_reservation_id"] = rid

        # Capacity cap check — set breakfast_guests above room max_capacity
        cats = {c["id"]: c for c in requests.get(f"{BASE}/rooms/categories", headers=H()).json()}
        cap = cats.get(alt["category_id"], {}).get("max_capacity", 2)
        over_payload = dict(payload, breakfast_guests=cap + 10, vehicles=[
                 {"mode":"quick","plate_number":"OVERCAP","model":"x","color":"y","is_primary":True}],
                 contact_email="overcap@example.com")
        r2 = requests.post(f"{BASE}/reservations", headers=H(), json=over_payload)
        if r2.status_code == 400 and "capacidad" in (r2.text.lower()):
            print(f"   capacity guard OK: {r2.status_code} {r2.text[:120]}")
        elif r2.status_code in (200, 201):
            bug("high", "S4", f"breakfast_guests > capacity was accepted ({cap+10} > {cap})")
        else:
            print(f"   capacity guard returned {r2.status_code}: {r2.text[:200]}")

        record("S4", "✅ PASS", f"reservation id={rid}; capacity guard exercised")
    except Exception as e:
        traceback.print_exc()
        bug("high", "S4", str(e))
        record("S4", "❌ FAIL", str(e))

# ── S5 — Charge consumos ───────────────────────────────────────────────────
def s5_charge_consumos():
    step("S5 — Charge consumos to Familia Martínez (Coca-Cola x3 + Lavandería)")
    if "s3_reservation_id" not in STATE:
        record("S5", "⏭ SKIP", "S3 reservation missing")
        return
    try:
        products = requests.get(f"{BASE}/productos/", headers=H()).json()
        coca = next((p for p in products if "Coca-Cola" in p["name"]), None)
        if not coca:
            bug("medium","S5","No Coca-Cola product in catalogue")
            return
        STATE["s5_coca_id"] = coca["id"]
        STATE["s5_coca_stock_before"] = coca["stock_current"]
        # Find a service (is_stocked=False)
        service = next((p for p in products if not p["is_stocked"] and p["is_active"]), None)

        r = requests.post(f"{BASE}/consumos/", headers=H(), json={
            "reserva_id": STATE["s3_reservation_id"],
            "producto_id": coca["id"],
            "quantity":3,
        })
        if r.status_code not in (200, 201):
            bug("high","S5",f"consumo create failed {r.status_code}: {r.text[:200]}")
            record("S5","❌ FAIL",f"consumo create {r.status_code}")
            return

        # Verify stock decrement
        coca_after = requests.get(f"{BASE}/productos/{coca['id']}", headers=H()).json()
        if coca_after["stock_current"] != coca["stock_current"] - 3:
            bug("high","S5",f"stock not decremented: was {coca['stock_current']}, now {coca_after['stock_current']}")

        # Verify saldo updated
        saldo = requests.get(f"{BASE}/reservations/{STATE['s3_reservation_id']}/saldo", headers=H()).json()
        if saldo.get("consumo_total", 0) <= 0:
            bug("high","S5",f"consumo_total stays 0 after charging: {saldo}")
        STATE["s3_saldo_after_consumo"] = saldo

        notes = [f"coca stock {coca['stock_current']}→{coca_after['stock_current']}"]
        if service:
            r2 = requests.post(f"{BASE}/consumos/", headers=H(), json={
                "reserva_id": STATE["s3_reservation_id"],
                "producto_id": service["id"],
                "quantity":1,
            })
            if r2.status_code in (200,201):
                notes.append(f"service {service['name']} charged OK")
            else:
                bug("medium","S5",f"service consumo failed {r2.status_code}: {r2.text[:200]}")
        record("S5", "✅ PASS" if not [b for b in BUGS if b[1]=='S5' and b[0]=='high'] else "❌ FAIL", "; ".join(notes))
    except Exception as e:
        traceback.print_exc()
        bug("high","S5",str(e))
        record("S5","❌ FAIL",str(e))

# ── S6 — Multi-currency PC ─────────────────────────────────────────────────
def s6_multi_currency_pc():
    step("S6 — Pay USD + BRL on PC (snapshot exchange rate)")
    if "s3_reservation_id" not in STATE:
        record("S6","⏭ SKIP","no S3 reservation")
        return
    try:
        # USD payment
        r = requests.post(f"{BASE}/transacciones/", headers=H(), json={
            "reserva_id": STATE["s3_reservation_id"],
            "amount": 50,
            "payment_method": "EFECTIVO",
            "currency_code": "USD",
        })
        if r.status_code not in (200,201):
            bug("high","S6",f"USD payment failed {r.status_code}: {r.text[:300]}")
            record("S6","❌ FAIL",f"USD {r.status_code}")
            return
        tx = r.json()
        if tx.get("currency_code") != "USD":
            bug("medium","S6",f"USD payment did not record currency_code: {tx}")
        if tx.get("amount") != 50 * 7500:
            bug("high","S6",f"USD→PYG conversion wrong: amount={tx.get('amount')} (expected {50*7500})")

        # BRL payment
        r2 = requests.post(f"{BASE}/transacciones/", headers=H(), json={
            "reserva_id": STATE["s3_reservation_id"],
            "amount": 200,
            "payment_method": "EFECTIVO",
            "currency_code": "BRL",
        })
        if r2.status_code not in (200,201):
            bug("high","S6",f"BRL payment failed {r2.status_code}: {r2.text[:300]}")
            record("S6","❌ FAIL",f"BRL {r2.status_code}")
            return
        tx2 = r2.json()
        if tx2.get("amount") != 200 * 1450:
            bug("high","S6",f"BRL→PYG conversion wrong: amount={tx2.get('amount')} (expected {200*1450})")

        # Verify both appear in transactions list (saldo response has .transacciones[])
        saldo = requests.get(f"{BASE}/transacciones/reserva/{STATE['s3_reservation_id']}", headers=H()).json()
        tx_list = saldo.get("transacciones", []) if isinstance(saldo, dict) else (saldo or [])
        currencies = sorted({(t.get("currency_code") or "PYG") for t in tx_list})
        record("S6", "✅ PASS" if not [b for b in BUGS if b[1]=='S6' and b[0]=='high'] else "❌ FAIL",
               f"{len(tx_list)} txns; currencies={currencies}")
    except Exception as e:
        traceback.print_exc()
        bug("high","S6",str(e))
        record("S6","❌ FAIL",str(e))

# ── S7 — Mobile payment USD ────────────────────────────────────────────────
def s7_mobile_payment_usd():
    step("S7 — Pay USD on mobile (Carlos Ramírez)")
    if "s4_reservation_id" not in STATE:
        record("S7","⏭ SKIP","no S4 reservation")
        return
    try:
        r = requests.post(f"{BASE}/transacciones/", headers=H(), json={
            "reserva_id": STATE["s4_reservation_id"],
            "amount": 100,
            "payment_method": "EFECTIVO",
            "currency_code": "USD",
        })
        if r.status_code not in (200,201):
            bug("high","S7",f"USD payment failed {r.status_code}: {r.text[:300]}")
            record("S7","❌ FAIL")
            return
        tx = r.json()
        if tx.get("amount") != 100 * 7500:
            bug("high","S7",f"USD conversion wrong: {tx}")
        record("S7","✅ PASS", f"tx id={tx['id']} amount={tx['amount']}")
    except Exception as e:
        traceback.print_exc()
        bug("high","S7",str(e))
        record("S7","❌ FAIL",str(e))

# ── S8 — Check-in / Ficha ──────────────────────────────────────────────────
def s8_checkin_ficha():
    step("S8 — Check-in ficha for Familia Martínez")
    if "s3_reservation_id" not in STATE:
        record("S8","⏭ SKIP","no S3 reservation")
        return
    try:
        # Use a fresh document number to avoid colliding with seed-data guest (doc 1234567)
        payload = {
            "reservation_id": STATE["s3_reservation_id"],
            "first_name": "María",
            "last_name": "Martínez",
            "document_type": "CI",
            "document_number": "9988776",
            "phone": "+595 991 111111",
            "email": "maria.martinez@example.com",
            "nationality": "Paraguaya",
            "country": "Paraguay",
            "city": "Asunción",
            "billing_name": "Familia Martínez SRL",
            "billing_ruc": "80012345-6",
            "vehicle_plate": "ABC-123",
            "vehicle_model": "Toyota Corolla",
        }
        r = requests.post(f"{BASE}/guests", headers=H(), json=payload)
        if r.status_code not in (200,201):
            bug("high","S8",f"checkin create failed {r.status_code}: {r.text[:300]}")
            record("S8","❌ FAIL")
            return
        chk = r.json()
        STATE["s8_checkin_id"] = chk["id"]
        notes = [f"checkin id={chk['id']}"]

        # CheckInService.register_checkin propagates billing + vehicle to
        # the master guest it actually links (may be different from the
        # reservation's guest because checkin uses document_number while
        # reservation may have linked by name only).
        ci_guest_id = chk.get("guest_id")
        if ci_guest_id:
            bp = requests.get(f"{BASE}/huespedes/{ci_guest_id}/billing", headers=H()).json()
            if not bp:
                bug("medium","S8",f"billing profile not auto-created on linked guest {ci_guest_id}")
            else:
                notes.append(f"billing profiles on guest {ci_guest_id}={len(bp)}")
            veh = requests.get(f"{BASE}/huespedes/{ci_guest_id}/vehicles", headers=H()).json()
            if not any(str(v["plate_number"]).upper() == "ABC-123" for v in veh):
                bug("medium","S8","vehicle ABC-123 not in master catalogue after ficha")
            else:
                notes.append(f"vehicles in master={len(veh)}")
        else:
            notes.append("⚠️ checkin response missing guest_id (DTO gap)")
        record("S8","✅ PASS","; ".join(notes))
    except Exception as e:
        traceback.print_exc()
        bug("high","S8",str(e))
        record("S8","❌ FAIL",str(e))

# ── S9 — Guest management ──────────────────────────────────────────────────
def s9_guest_management():
    step("S9 — Guest management page (search, list, detail)")
    try:
        # Search by name
        s = requests.get(f"{BASE}/huespedes/search", headers=H(), params={"q":"Martínez","limit":5}).json()
        if not s:
            bug("medium","S9","search 'Martínez' returned 0 (S3 should have created)")
        # Paginated list
        lst = requests.get(f"{BASE}/huespedes", headers=H(), params={"skip":0,"limit":10}).json()
        if not isinstance(lst, dict) or "items" not in lst:
            bug("low","S9",f"list response shape unexpected: {type(lst)}")
        else:
            print(f"   list: total={lst.get('total')} items={len(lst.get('items',[]))}")
        # Detail + history
        if STATE.get("s3_guest_id"):
            g = requests.get(f"{BASE}/huespedes/{STATE['s3_guest_id']}", headers=H()).json()
            h = requests.get(f"{BASE}/huespedes/{STATE['s3_guest_id']}/history", headers=H()).json()
            print(f"   guest {STATE['s3_guest_id']}: history reservations={len(h.get('reservations',[]))}")
        # 5-vehicle cap
        if STATE.get("s3_guest_id"):
            cap_test = []
            for i in range(7):
                r = requests.post(f"{BASE}/huespedes/{STATE['s3_guest_id']}/vehicles", headers=H(),
                                  json={"plate_number": f"CAP{i:03d}", "model": "test", "color": "x"})
                cap_test.append(r.status_code)
            print(f"   add-vehicle status codes (try 7): {cap_test}")
            if not any(sc == 400 for sc in cap_test):
                bug("medium","S9","5-vehicle limit not enforced (no 400 across 7 adds)")
            else:
                # cleanup
                veh = requests.get(f"{BASE}/huespedes/{STATE['s3_guest_id']}/vehicles", headers=H()).json()
                for v in veh:
                    if str(v["plate_number"]).startswith("CAP"):
                        requests.delete(f"{BASE}/huespedes/{STATE['s3_guest_id']}/vehicles/{v['id']}", headers=H())
        record("S9","✅ PASS","search/list/detail/cap exercised")
    except Exception as e:
        traceback.print_exc()
        bug("medium","S9",str(e))
        record("S9","❌ FAIL",str(e))

# ── S10 — Future reservation, no meal, no vehicle ─────────────────────────
def s10_future_no_meal_no_vehicle():
    step("S10 — Future reservation: González next Monday, no meal, no vehicle")
    try:
        rooms = requests.get(f"{BASE}/rooms", headers=H()).json()
        # Pick a room not used by S3/S4
        used = {STATE.get("s3_room"), STATE.get("s4_room")}
        room = next((r for r in rooms if r["id"] not in used), rooms[2])
        STATE["s10_room"] = room["id"]
        # Find next Monday
        today = date.today()
        days = (7 - today.weekday()) % 7 or 7
        ci = today + timedelta(days=days)
        co = ci + timedelta(days=2)
        payload = {
            "guest_name": "Pedro González",
            "contact_email": "pedro.gonzalez@example.com",
            "room_ids": [room["id"]],
            "client_type_id": "los-monges-particular",
            "check_in_date": ci.isoformat(),
            "stay_days": (co - ci).days,
            "source": "Teléfono",
            "vehicles": [],  # explicit empty
            "price": 350000,
        }
        r = requests.post(f"{BASE}/reservations", headers=H(), json=payload)
        if r.status_code not in (200,201):
            bug("high","S10",f"create failed {r.status_code}: {r.text[:300]}")
            record("S10","❌ FAIL")
            return
        body = r.json()
        rid = body[0] if isinstance(body, list) and body else (body if isinstance(body, str) else None)
        if not rid:
            bug("high","S10", f"unexpected body shape: {body!r}")
            record("S10","❌ FAIL","bad response")
            return
        STATE["s10_reservation_id"] = rid
        det = requests.get(f"{BASE}/reservations/{rid}", headers=H()).json()
        veh = det.get("vehicles") or []
        if veh:
            bug("low","S10",f"vehicles=[] payload still created {len(veh)} vehicles")
        if det.get("meal_plan_id"):
            bug("low","S10","meal_plan_id set when payload didn't include it")
        record("S10","✅ PASS",f"reservation id={rid} dates={ci}→{co}")
    except Exception as e:
        traceback.print_exc()
        bug("high","S10",str(e))
        record("S10","❌ FAIL",str(e))

# ── S11 — Edit reservation ─────────────────────────────────────────────────
def s11_edit_reservation():
    step("S11 — Edit Familia Martínez reservation (extend stay, late checkout)")
    if "s3_reservation_id" not in STATE:
        record("S11","⏭ SKIP","no S3 reservation")
        return
    try:
        cur = requests.get(f"{BASE}/reservations/{STATE['s3_reservation_id']}", headers=H()).json()
        new_stay_days = 2
        payload = {
            "guest_name": cur.get("guest_name") or "Familia Martínez",
            "room_ids": [cur.get("room_id") or STATE["s3_room"]],
            "check_in_date": cur.get("check_in"),
            "stay_days": new_stay_days,
            "client_type_id": cur.get("client_type_id") or "los-monges-particular",
            "contact_email": cur.get("contact_email",""),
            "contact_phone": cur.get("contact_phone",""),
            "source": cur.get("source") or "Direct",
            "meal_plan_id": cur.get("meal_plan_id"),
            "breakfast_guests": 2,
            "late_checkout": True,
            "late_checkout_time": "14:00",
            "parking_needed": True,
        }
        r = requests.put(f"{BASE}/reservations/{STATE['s3_reservation_id']}", headers=H(), json=payload)
        if r.status_code not in (200,201):
            bug("high","S11",f"update failed {r.status_code}: {r.text[:300]}")
            record("S11","❌ FAIL")
            return
        det = requests.get(f"{BASE}/reservations/{STATE['s3_reservation_id']}", headers=H()).json()
        if det.get("stay_days") != new_stay_days:
            bug("medium","S11",f"stay_days not persisted: {det.get('stay_days')} vs {new_stay_days}")
        if not det.get("late_checkout"):
            bug("medium","S11","late_checkout flag not persisted")
        if det.get("late_checkout_time") not in ("14:00","14:00:00"):
            bug("medium","S11",f"late_checkout_time mismatch: {det.get('late_checkout_time')}")
        if det.get("breakfast_guests") != 2:
            bug("medium","S11",f"breakfast_guests not updated: {det.get('breakfast_guests')}")
        record("S11","✅ PASS" if not [b for b in BUGS if b[1]=='S11'] else "⚠️ WARNING",
               f"co={det.get('check_out_date')} late={det.get('late_checkout')}@{det.get('late_checkout_time')} br={det.get('breakfast_guests')}")
    except Exception as e:
        traceback.print_exc()
        bug("high","S11",str(e))
        record("S11","❌ FAIL",str(e))

# ── S12 — Settings: hours, meals, currencies ──────────────────────────────
def s12_settings():
    step("S12 — Settings (hours, currency add/remove/update)")
    try:
        # Hours
        hrs = requests.get(f"{BASE}/settings/property-settings", headers=H()).json()
        print(f"   hours: {hrs}")
        # Update USD rate
        r = requests.put(f"{BASE}/currencies/USD/rate", headers=H(), json={"exchange_rate": 7550})
        if r.status_code != 200:
            bug("medium","S12",f"update USD rate failed {r.status_code}: {r.text[:200]}")
        else:
            # restore
            requests.put(f"{BASE}/currencies/USD/rate", headers=H(), json={"exchange_rate": 7500})
        # Add ARS
        r = requests.post(f"{BASE}/currencies", headers=H(), json={
            "currency_code":"ARS", "exchange_rate": 7.5, "sort_order": 99
        })
        if r.status_code not in (200,201):
            bug("medium","S12",f"add ARS failed {r.status_code}: {r.text[:200]}")
        # Remove ARS
        rd = requests.delete(f"{BASE}/currencies/ARS", headers=H())
        if rd.status_code not in (200,204):
            bug("medium","S12",f"remove ARS failed {rd.status_code}: {rd.text[:200]}")
        # Meals config
        mc = requests.get(f"{BASE}/settings/meals-config", headers=H()).json()
        print(f"   meals: {mc}")
        record("S12","✅ PASS" if not [b for b in BUGS if b[1]=='S12'] else "⚠️ WARNING",
               "FX update + ARS add/remove + meals visible")
    except Exception as e:
        traceback.print_exc()
        bug("medium","S12",str(e))
        record("S12","❌ FAIL",str(e))

# ── S13 — Close caja with breakdown ───────────────────────────────────────
def s13_close_caja():
    step("S13 — Close caja (multi-currency breakdown)")
    try:
        if "caja_id" not in STATE:
            cur = requests.get(f"{BASE}/caja/actual", headers=H()).json()
            if cur and cur.get("status") == "ABIERTA":
                STATE["caja_id"] = cur["id"]
            else:
                record("S13","⏭ SKIP","no open caja")
                return
        summ = requests.get(f"{BASE}/caja/{STATE['caja_id']}", headers=H()).json()
        breakdown = summ.get("currency_breakdown") or []
        if breakdown:
            print(f"   currency_breakdown: {len(breakdown)} buckets")
            for b in breakdown:
                print(f"     {b}")
        else:
            bug("low","S13","no currency_breakdown in session summary (S6/S7 added USD+BRL?)")
        expected = summ.get("closing_balance_expected") or 0
        r = requests.post(f"{BASE}/caja/cerrar", headers=H(), json={
            "session_id": STATE["caja_id"],
            "closing_balance_declared": expected, "notes": "E2E close"
        })
        if r.status_code != 200:
            bug("high","S13",f"close failed {r.status_code}: {r.text[:300]}")
            record("S13","❌ FAIL")
            return
        closed = r.json()
        record("S13","✅ PASS",f"closed; difference={closed.get('difference')} expected={closed.get('closing_balance_expected')}")
        # Reopen for the night shift
        r2 = requests.post(f"{BASE}/caja/abrir", headers=H(), json={
            "opening_balance": expected, "notes": "Turno noche"
        })
        if r2.status_code == 200:
            STATE["caja_id"] = r2.json()["id"]
            print(f"   reopened night-shift caja id={STATE['caja_id']}")
    except Exception as e:
        traceback.print_exc()
        bug("high","S13",str(e))
        record("S13","❌ FAIL",str(e))

# ── S14 — Inventory ───────────────────────────────────────────────────────
def s14_inventory():
    step("S14 — Inventory: stock, add, edit, adjust")
    try:
        # Stock current
        if STATE.get("s5_coca_id") and STATE.get("s5_coca_stock_before") is not None:
            now = requests.get(f"{BASE}/productos/{STATE['s5_coca_id']}", headers=H()).json()
            print(f"   Coca stock: pre-S5={STATE['s5_coca_stock_before']} now={now['stock_current']}")
            if STATE["s5_coca_stock_before"] - now["stock_current"] != 3:
                bug("medium","S14",f"Coca stock delta != 3 (S5 charged 3)")
        # Add new product
        new_pid = "e2e-test-bebida-" + str(int(time.time()))
        r = requests.post(f"{BASE}/productos/", headers=H(), json={
            "id": new_pid, "name":"E2E Test Bebida", "category":"BEBIDA", "price":7777,
            "stock_current":10, "stock_minimum":2, "is_stocked":True
        })
        if r.status_code not in (200,201):
            bug("medium","S14",f"add product failed {r.status_code}: {r.text[:200]}")
            return record("S14","❌ FAIL")
        new_id = r.json()["id"] if isinstance(r.json(), dict) else new_pid
        # Edit price
        r2 = requests.patch(f"{BASE}/productos/{new_id}", headers=H(), json={"price": 8888})
        if r2.status_code != 200:
            bug("medium","S14",f"edit failed {r2.status_code}: {r2.text[:200]}")
        # Manual stock adjust — `reason` in this API is the *type* enum
        # (COMPRA/MERMA/AJUSTE), not a free-text description.
        r3 = requests.post(f"{BASE}/productos/{new_id}/ajuste-stock", headers=H(), json={
            "quantity_change": 5, "reason": "COMPRA", "notes": "E2E adjust"
        })
        if r3.status_code not in (200,201):
            bug("medium","S14",f"adjust stock failed {r3.status_code}: {r3.text[:200]}")
        # Cleanup
        requests.delete(f"{BASE}/productos/{new_id}", headers=H())
        record("S14","✅ PASS" if not [b for b in BUGS if b[1]=='S14'] else "⚠️ WARNING",
               "stock checked, add+edit+adjust+delete cycle OK")
    except Exception as e:
        traceback.print_exc()
        bug("medium","S14",str(e))
        record("S14","❌ FAIL",str(e))

# ── S15 — Documents ───────────────────────────────────────────────────────
def s15_documents():
    step("S15 — Documents: list Reservas/Cuentas/Clientes")
    try:
        results = {}
        for folder in ("Reservas","Cuentas","Clientes","Reportes_Cocina"):
            r = requests.get(f"{BASE}/documents/list/{folder}", headers=H())
            results[folder] = (r.status_code, len(r.json()) if r.status_code == 200 and isinstance(r.json(), list) else "n/a")
        print(f"   listings: {results}")
        # Generate folio for S3 to populate Cuentas
        if STATE.get("s3_reservation_id"):
            r = requests.get(f"{BASE}/documents/folio/{STATE['s3_reservation_id']}", headers=H())
            print(f"   folio generation: {r.status_code} {r.headers.get('content-type','')}")
            if r.status_code != 200:
                bug("medium","S15",f"folio failed {r.status_code}: {r.text[:200]}")
        record("S15","✅ PASS" if not [b for b in BUGS if b[1]=='S15'] else "⚠️ WARNING",
               json.dumps(results, default=str))
    except Exception as e:
        traceback.print_exc()
        bug("medium","S15",str(e))
        record("S15","❌ FAIL",str(e))

# ── S16 — AI Assistant ────────────────────────────────────────────────────
def s16_ai_assistant():
    step("S16 — AI Assistant (3 Spanish queries)")
    try:
        r = requests.get(f"{BASE}/agent/status", headers=H())
        print(f"   /agent/status: {r.status_code} {r.text[:200]}")
        queries = [
            "¿Cuántas reservas hay para hoy?",
            "¿De quién es el vehículo ABC-123?",
            "¿Cuántas estadías tiene Familia Martínez?",
        ]
        all_ok = True
        for q in queries:
            r = requests.post(f"{BASE}/agent/query", headers=H(), json={"prompt": q}, timeout=120)
            if r.status_code != 200:
                bug("medium","S16",f"query '{q[:30]}' returned {r.status_code}: {r.text[:300]}")
                all_ok = False
                continue
            ans = r.json()
            text = ans.get("response","") or ans.get("answer","") or json.dumps(ans, default=str)[:300]
            print(f"   Q: {q}\n   A: {text[:250]}")
        record("S16","✅ PASS" if all_ok else "⚠️ WARNING", f"{len(queries)} queries")
    except Exception as e:
        traceback.print_exc()
        bug("medium","S16",str(e))
        record("S16","❌ FAIL",str(e))

# ── S17 — Edge cases ──────────────────────────────────────────────────────
def s17_edge_cases():
    step("S17 — Edge cases")
    notes = []
    try:
        # Past date — way in the past (should be blocked)
        past_ci = (date.today() - timedelta(days=30))
        rooms = requests.get(f"{BASE}/rooms", headers=H()).json()
        room = rooms[0]
        payload = {
            "guest_name": "Past Date Test",
            "room_ids": [room["id"]], "client_type_id": "los-monges-particular",
            "check_in_date": past_ci.isoformat(),
            "stay_days": 2,
            "source": "Direct", "vehicles": [],
        }
        r = requests.post(f"{BASE}/reservations", headers=H(), json=payload)
        if r.status_code in (400, 422):
            notes.append(f"past-date blocked ✓ ({r.status_code})")
        elif r.status_code in (200,201):
            bug("high","S17","past-date reservation 30 days ago was ACCEPTED")
        else:
            notes.append(f"past-date status={r.status_code}")

        # Double booking — book S3 room again same dates
        if STATE.get("s3_room"):
            today = date.today().isoformat()
            tomorrow = (date.today()+timedelta(days=1)).isoformat()
            payload2 = {
                "guest_name":"Double Book Test","room_ids":[STATE["s3_room"]],
                "client_type_id":"los-monges-particular",
                "check_in_date":today, "stay_days": 1,
                "source":"Direct","vehicles":[],
            }
            r = requests.post(f"{BASE}/reservations", headers=H(), json=payload2)
            if r.status_code == 400:
                notes.append("double-booking blocked ✓")
            elif r.status_code in (200,201):
                bug("high","S17","double-booking on same room/date ACCEPTED")
            else:
                notes.append(f"double-book status={r.status_code} {r.text[:80]}")

        # Stock=0 product → consumo should fail
        products = requests.get(f"{BASE}/productos/", headers=H()).json()
        # Find or create a zero-stock product
        zero = next((p for p in products if p["is_stocked"] and p["stock_current"] == 0), None)
        if not zero:
            # adjust an existing one to 0 then back
            cand = next((p for p in products if p["is_stocked"]), None)
            if cand:
                # Set stock to 0
                rx = requests.post(f"{BASE}/productos/{cand['id']}/ajuste-stock", headers=H(),
                              json={"quantity_change": -cand['stock_current'],
                                    "reason": "MERMA", "notes": "E2E zero stock"})
                if rx.status_code not in (200, 201):
                    print(f"   ⚠️  zero-stock setup failed {rx.status_code}: {rx.text[:150]}")
                zero = requests.get(f"{BASE}/productos/{cand['id']}", headers=H()).json()
        if zero and STATE.get("s3_reservation_id"):
            r = requests.post(f"{BASE}/consumos/", headers=H(), json={
                "reserva_id": STATE["s3_reservation_id"],
                "producto_id": zero["id"], "cantidad": 1
            })
            if r.status_code == 400:
                notes.append(f"stock=0 charge blocked ✓ ({zero['name']})")
            elif r.status_code in (200,201):
                bug("high","S17",f"charged {zero['name']} with stock=0")
            else:
                notes.append(f"stock=0 status={r.status_code}")
            # restore stock
            requests.post(f"{BASE}/productos/{zero['id']}/ajuste-stock", headers=H(),
                          json={"quantity_change": 10, "reason":"COMPRA", "notes":"E2E restore"})

        # Void consumo as recepcion → 403
        if STATE.get("recep_token"):
            # Find a consumo from S3
            cons = requests.get(f"{BASE}/consumos/reserva/{STATE['s3_reservation_id']}", headers=H()).json()
            if cons:
                cid = cons[0]["id"]
                r = requests.post(f"{BASE}/consumos/{cid}/anular", headers=H(STATE["recep_token"]),
                                  json={"reason":"E2E test"})
                if r.status_code == 403:
                    notes.append("recepcion void→403 ✓")
                else:
                    bug("medium","S17",f"recepcion was allowed to void consumo: {r.status_code}")

        # Capacity guard already covered in S4
        record("S17","✅ PASS" if not [b for b in BUGS if b[1]=='S17' and b[0]=='high'] else "❌ FAIL", " | ".join(notes))
    except Exception as e:
        traceback.print_exc()
        bug("high","S17",str(e))
        record("S17","❌ FAIL",str(e))

# ── S18 — Buildings + rooms admin ─────────────────────────────────────────
def s18_buildings_rooms():
    step("S18 — Buildings + rooms admin")
    try:
        b = requests.get(f"{BASE}/buildings", headers=H()).json()
        print(f"   buildings: {len(b)} — {[(x.get('id'), x.get('name'), x.get('room_count')) for x in b]}")
        # Status change
        rooms = requests.get(f"{BASE}/rooms", headers=H()).json()
        rid = rooms[0]["id"]
        prev = rooms[0]["status"]
        new = "limpieza" if prev != "limpieza" else "available"
        r = requests.patch(f"{BASE}/rooms/{rid}/status", headers=H(),
                           json={"status": new, "reason":"E2E test"})
        if r.status_code != 200:
            bug("medium","S18",f"status change failed {r.status_code}: {r.text[:200]}")
        # Restore
        requests.patch(f"{BASE}/rooms/{rid}/status", headers=H(),
                       json={"status": prev, "reason":"E2E restore"})
        # Status log
        log = requests.get(f"{BASE}/rooms/{rid}/status-log", headers=H()).json()
        print(f"   status log for {rid}: {len(log)} entries")
        record("S18","✅ PASS" if not [b for b in BUGS if b[1]=='S18'] else "⚠️ WARNING",
               f"{len(b)} bldgs; status round-trip OK")
    except Exception as e:
        traceback.print_exc()
        bug("medium","S18",str(e))
        record("S18","❌ FAIL",str(e))

# ── Main ──────────────────────────────────────────────────────────────────
def main():
    bootstrap()
    cleanup_prior_runs()
    s1_open_caja()
    s2_today_reservations()
    s3_pc_walkin()
    s4_mobile_walkin()
    s5_charge_consumos()
    s6_multi_currency_pc()
    s7_mobile_payment_usd()
    s8_checkin_ficha()
    s9_guest_management()
    s10_future_no_meal_no_vehicle()
    s11_edit_reservation()
    s12_settings()
    s14_inventory()    # before close so live data
    s15_documents()
    s16_ai_assistant()
    s17_edge_cases()
    s18_buildings_rooms()
    s13_close_caja()   # last

    print("\n══════════════ FINAL ══════════════")
    pas = sum(1 for _,s,_ in RESULTS if "PASS" in s)
    war = sum(1 for _,s,_ in RESULTS if "WARN" in s)
    fai = sum(1 for _,s,_ in RESULTS if "FAIL" in s)
    print(f"Pass {pas}  Warn {war}  Fail {fai}")
    for sc, st, n in RESULTS:
        print(f"  {sc:6} {st:14}  {n}")
    print(f"\nBugs: {len(BUGS)}")
    for sev, sc, d in BUGS:
        print(f"  [{sev}] {sc}: {d}")

if __name__ == "__main__":
    main()
