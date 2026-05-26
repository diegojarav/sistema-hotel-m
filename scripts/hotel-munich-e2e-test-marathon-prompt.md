# Hotel Munich PMS — Autonomous E2E Test Marathon
## Claude Code Prompt — SELF-CONTAINED (runs independently)

---

## Skills to use (MANDATORY)

1. **hotel-munich-backend** — all service patterns, endpoints, business rules
2. **ui-ux-pro-max** — evaluate UX quality during testing
3. **frontend-design** — evaluate mobile components

---

## Your role

You are a Senior QA Engineer running a complete end-to-end test of the 
Hotel Munich PMS. You will simulate a FULL DAY of hotel operations, 
testing every major feature from a receptionist's perspective.

## Autonomy

You are running INDEPENDENTLY. The developer is working on something 
else on another monitor. You have full permission to:

1. Start all services (backend, PC, mobile)
2. Create test data (reservations, guests, payments, consumos)
3. Test via preview, HTTP requests, or any available tool
4. Fix any bug you find — code fixes, UX improvements
5. Commit and push fixes with descriptive messages
6. Report everything at the end

**DO NOT ask the developer questions.** Make decisions yourself.
If something is ambiguous, pick the safest option and document why.

**DO NOT stop if you hit a bug.** Document it, fix it if you can, 
and continue testing. The goal is to find ALL issues, not stop at the first one.

---

## Step 0 — Start all services

```bash
# Start backend
cd backend && uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
sleep 5

# Start PC frontend
cd frontend_pc && streamlit run app.py --server.port 8501 --server.headless true &
sleep 5

# Start mobile frontend
cd frontend_mobile && npm run dev -- --port 3000 &
sleep 10

# Health checks
curl -s --max-time 10 http://localhost:8000/docs > /dev/null && echo "Backend ✅" || echo "Backend ❌"
curl -s --max-time 10 http://localhost:8501 > /dev/null && echo "PC ✅" || echo "PC ❌"
curl -s --max-time 10 http://localhost:3000 > /dev/null && echo "Mobile ✅" || echo "Mobile ❌"
```

If any service fails, diagnose and fix before proceeding.

Get an auth token for API calls:
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token','FAILED'))")
echo "Auth: ${TOKEN:0:20}..."
```

---

## SIMULATION: A Full Day at the Hotel

Test EVERY scenario below. For each one, document:
- What you did (step by step)
- What happened (expected vs actual)
- Pass ✅ / Fail ❌ / Warning ⚠️
- Screenshot or evidence if relevant

### SCENARIO 1 — Morning: Open cash register (06:00)

```
Platform: PC
Flow: Login → Caja → Open new session
Test:
  ☐ Can login as admin
  ☐ Caja page loads without errors
  ☐ Can open a new caja session with opening balance
  ☐ Session shows "Abierta" status
  ☐ Opening balance shows correctly
```

### SCENARIO 2 — Morning: Check existing reservations (07:00)

```
Platform: PC + Mobile
Flow: Calendar → see today's reservations
Test:
  ☐ PC calendar shows today's date with reservations
  ☐ Mobile calendar shows the same data
  ☐ Reservation details match between PC and mobile
  ☐ Guest info, room, dates, amounts all correct
  ☐ SWB branding visible at bottom of both platforms
```

### SCENARIO 3 — Walk-in: Family arrives without reservation (10:00)

```
Platform: PC
Flow: New reservation → create → assign room
Test:
  ☐ Create reservation for "Familia Martínez" (2 adults + 1 child)
  ☐ Select a room (verify availability)
  ☐ Set check-in date = today
  ☐ Set check-out date = tomorrow
  ☐ Add meal plan "Con Desayuno" for 3 guests
  ☐ Price calculates correctly (room + meal plan surcharge)
  ☐ Add 2 vehicles:
    - Quick-add: plate "ABC-123", model "Toyota Corolla", color "Blanco"
    - Quick-add: plate "XYZ-789", model "Honda Civic", color "Negro"
  ☐ Save → reservation created with status CONFIRMADA or RESERVADA
  ☐ Guest "Martínez" appears in Huéspedes page
  ☐ Both vehicles registered
  ☐ PDF generated and downloadable
  ☐ PDF shows meal plan info
```

### SCENARIO 4 — Walk-in on Mobile: Solo traveler (10:30)

```
Platform: Mobile
Flow: New reservation from mobile
Test:
  ☐ Navigate to "Nueva Reserva"
  ☐ Search existing guests → type "Fernández" → verify autocomplete works
  ☐ If no match, enter new guest: "Carlos Ramírez"
  ☐ Select room, dates (today → +2 nights)
  ☐ Select meal plan, set breakfast guests = 1
  ☐ Try changing breakfast guests: 1 → 2 → 1 (verify NO snap-to-max bug)
  ☐ Add 1 vehicle via quick-add
  ☐ Confirm → reservation created
  ☐ Guest appears in the system
```

### SCENARIO 5 — Charge products to a room (12:00)

```
Platform: PC (daily view)
Flow: Calendar → expand reservation → Cargar Producto
Test:
  ☐ Find Familia Martínez's reservation in today's view
  ☐ Expand the reservation card
  ☐ "🧾 Consumos" section visible WITHOUT entering edit mode
  ☐ Open "➕ Cargar Producto" expander
  ☐ Select "Coca-Cola 500ml" → quantity 3
  ☐ See live total preview
  ☐ Register → success message
  ☐ Consumos list updates with the new charge
  ☐ Total/Saldo updates to reflect the charge
  ☐ Stock decremented (check via Inventario page)
  
  Then charge another:
  ☐ Select "Lavandería" (service, no stock)
  ☐ Register → success
```

### SCENARIO 6 — Register payment in foreign currency (14:00)

```
Platform: PC
Flow: Calendar → expand reservation → Registrar Pago
Test:
  ☐ Open Familia Martínez's reservation
  ☐ Select currency "USD" from the selector
  ☐ Type amount: 50
  ☐ See conversion preview: "💱 Equivale a 375.000 ₲ (TC: 7.500)"
  ☐ Select method: EFECTIVO
  ☐ Register payment → success
  ☐ Pagado amount updates (in Guaraníes)
  ☐ Saldo decreases

  Then pay more in Reales:
  ☐ Select "BRL"
  ☐ Type 200 → see "💱 Equivale a 290.000 ₲ (TC: 1.450)"
  ☐ Register → success
  ☐ Verify both payments show in history
```

### SCENARIO 7 — Register payment on Mobile (14:30)

```
Platform: Mobile
Flow: Reservation detail → Registrar Pago
Test:
  ☐ Open Carlos Ramírez's reservation on mobile
  ☐ Currency pills visible (₲ | US$ | R$)
  ☐ Select US$ → type 100
  ☐ See conversion preview
  ☐ Register → success
  ☐ Payment recorded correctly
```

### SCENARIO 8 — Check-in / Ficha de cliente (15:00)

```
Platform: PC
Flow: Ficha de Cliente tab
Test:
  ☐ Create a new ficha
  ☐ Search "Martínez" → "💡 ¿Es un huésped recurrente?" section works
  ☐ Pre-fill from Guest master → fields populate
  ☐ Add/modify: nationality, document, phone
  ☐ Add billing data (Razón Social + RUC)
  ☐ Save ficha → checkin created
  ☐ Guest master updated with new fields (fill empty, never overwrite)
  ☐ Billing profile created in guest's 🧾 tab
  ☐ Vehicle linked to this checkin
```

### SCENARIO 9 — Guest management (16:00)

```
Platform: PC
Flow: Huéspedes page
Test:
  ☐ Search bar works (by name, document, email, phone)
  ☐ Guest list paginated correctly (no empty pages)
  ☐ Click a guest → detail loads
  ☐ "Datos" tab → can edit, birth_date picker works
  ☐ "Historial" tab → shows reservations
  ☐ "🧾 Facturación" tab → shows billing profiles
  ☐ "🚗 Vehículos" tab → shows registered vehicles (counter X/5)
  ☐ Can add a vehicle (verify max 5 limit)
  ☐ Stats visible: total stays, total spent, last visit
```

### SCENARIO 10 — Phone reservation for next week (16:30)

```
Platform: PC
Flow: New reservation (future date)
Test:
  ☐ Create reservation for next Monday
  ☐ Guest: search for "González" from guest master dropdown
  ☐ Select guest → contact fields auto-fill (email, phone)
  ☐ Override email if needed
  ☐ Select room + dates (next week)
  ☐ No meal plan (verify "Sin plan de comidas" works)
  ☐ No vehicle (verify vehicles=[] is handled)
  ☐ Price: manually adjust to a negotiated rate (verify step=1 works)
  ☐ Save → reservation in PENDIENTE or RESERVADA status
```

### SCENARIO 11 — Edit existing reservation (17:00)

```
Platform: PC
Flow: Search reservation → edit
Test:
  ☐ Find Familia Martínez's reservation via search or calendar
  ☐ Enter edit mode
  ☐ Change check-out date → price recalculates
  ☐ Add late checkout → toggle appears → set time to 14:00
  ☐ Change meal plan guests from 3 to 2
  ☐ Save → updates persist
  ☐ PDF regenerated with updated info
```

### SCENARIO 12 — Hotel settings check (17:30)

```
Platform: PC
Flow: Configuración page
Test:
  ☐ Hotel name configurable
  ☐ SMTP settings visible (not testing actual email)
  ☐ "⏰ Horarios del Hotel" section → check-in/check-out times
  ☐ "🍽️ Plan de comidas" configuration
  ☐ "💱 Monedas" section → PYG (base), USD, BRL visible
  ☐ Can update exchange rate for USD
  ☐ Can add a new currency (e.g., ARS)
  ☐ Can remove the currency just added
```

### SCENARIO 13 — Close cash register (19:00)

```
Platform: PC
Flow: Caja → Close session
Test:
  ☐ Caja shows all today's transactions
  ☐ Total in base currency (PYG) is correct
  ☐ "💱 Desglose por moneda" shows USD + BRL + PYG breakdown
  ☐ Close session with declared amount
  ☐ Difference calculated (if declared ≠ system total)
  ☐ Session marked as closed
  ☐ Can open a new session for the night shift
```

### SCENARIO 14 — Inventory check (19:30)

```
Platform: PC
Flow: Inventario page
Test:
  ☐ Product list shows all items
  ☐ Stock levels are correct (Coca-Cola reduced by 3 from Scenario 5)
  ☐ Can add a new product
  ☐ Can edit product price
  ☐ Can adjust stock manually
  ☐ Categories filter works
```

### SCENARIO 15 — Documents (20:00)

```
Platform: PC
Flow: Documentos Hotel page
Test:
  ☐ "📄 Reservas" tab → shows reservation PDFs
  ☐ "📋 Cuentas" tab → shows folio PDFs (if any generated)
  ☐ "👤 Clientes" tab → shows client fichas
  ☐ PDFs downloadable and open correctly
```

### SCENARIO 16 — AI Assistant (20:30)

```
Platform: PC
Flow: Asistente IA
Test:
  ☐ Page loads, tools listed
  ☐ Ask: "¿Cuántas reservas hay para hoy?" → responds with data
  ☐ Ask: "¿De quién es el vehículo ABC-123?" → finds Familia Martínez
  ☐ Ask: "¿Cuántas veces se hospedó [guest name]?" → shows history
  ☐ All responses in Spanish
```

### SCENARIO 17 — Edge cases

```
Test:
  ☐ Try creating a reservation for a past date → hotel day logic:
    - If before check-out time (10:00): should allow "yesterday"
    - If after: should block
  ☐ Try booking a room that's already occupied → should show unavailable
  ☐ Try charging a product with stock=0 → should be blocked/disabled
  ☐ Try voiding a consumo as "recepcion" user → should get 403
  ☐ Try setting breakfast guests > room capacity → should cap/error
  ☐ Create two reservations for the same room same dates → conflict check
```

### SCENARIO 18 — Buildings and rooms admin (21:00)

```
Platform: PC
Flow: Admin Habitaciones
Test:
  ☐ Room list shows all rooms with building filter
  ☐ Building management expandable (Admin only)
  ☐ Room status changes work
  ☐ Category assignment works
```

---

## After all scenarios

### Compile results

For each scenario, rate:
- ✅ PASS — worked as expected
- ⚠️ WARNING — worked but UX could be better
- ❌ FAIL — broken or unexpected behavior

### Fix what you can

For each ❌ FAIL or significant ⚠️ WARNING:
1. Diagnose the root cause
2. Fix it if possible (< 30 min per fix)
3. Test the fix
4. Continue testing

### Commit fixes

If you made code changes:
```bash
cd backend && pytest --tb=short -q  # verify no regressions
git add -A
git commit -m "fix(e2e): [description of fixes from testing marathon]"
git push private dev
```

---

## Final Report

```
═══════════════════════════════════════════════════════════════
E2E Test Marathon — Full Day Simulation
═══════════════════════════════════════════════════════════════
Date: [date]
Duration: [time]
Platform versions: backend [HEAD], PC [HEAD], mobile [HEAD]

RESULTS SUMMARY:
  Total scenarios: 18
  ✅ PASS:    [N]
  ⚠️ WARNING: [N]
  ❌ FAIL:    [N]

DETAILED RESULTS:
  Scenario  1 (Open caja):          [✅/⚠️/❌] — [notes]
  Scenario  2 (Check reservations): [✅/⚠️/❌] — [notes]
  Scenario  3 (Walk-in PC):         [✅/⚠️/❌] — [notes]
  Scenario  4 (Walk-in Mobile):     [✅/⚠️/❌] — [notes]
  Scenario  5 (Charge products):    [✅/⚠️/❌] — [notes]
  Scenario  6 (Pay USD/BRL PC):     [✅/⚠️/❌] — [notes]
  Scenario  7 (Pay USD Mobile):     [✅/⚠️/❌] — [notes]
  Scenario  8 (Check-in/ficha):     [✅/⚠️/❌] — [notes]
  Scenario  9 (Guest management):   [✅/⚠️/❌] — [notes]
  Scenario 10 (Future reservation): [✅/⚠️/❌] — [notes]
  Scenario 11 (Edit reservation):   [✅/⚠️/❌] — [notes]
  Scenario 12 (Settings):           [✅/⚠️/❌] — [notes]
  Scenario 13 (Close caja):         [✅/⚠️/❌] — [notes]
  Scenario 14 (Inventory):          [✅/⚠️/❌] — [notes]
  Scenario 15 (Documents):          [✅/⚠️/❌] — [notes]
  Scenario 16 (AI Assistant):       [✅/⚠️/❌] — [notes]
  Scenario 17 (Edge cases):         [✅/⚠️/❌] — [notes]
  Scenario 18 (Buildings/rooms):    [✅/⚠️/❌] — [notes]

BUGS FOUND: [N]
  [severity] [scenario] [description] [fixed? Y/N]

FIXES APPLIED: [N]
  [commit hash] [description]

UX IMPROVEMENTS SUGGESTED: [N]
  [priority] [description]

OVERALL HEALTH: [HEALTHY / NEEDS FIXES / CRITICAL ISSUES]

Tests after fixes: [N] passed, 0 regressions
═══════════════════════════════════════════════════════════════
```

---

> This test marathon should take 2-3 hours. When complete, the developer 
> will have a comprehensive picture of what works and what needs fixing.
> The developer is working on something else — do NOT interrupt them.
> Complete the full marathon and report at the end.
