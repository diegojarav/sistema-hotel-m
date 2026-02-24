#!/usr/bin/env python3
"""
Hotel Munich PMS - Test Data Seed Script
==========================================

Generates realistic transactional data for pre-production testing:
- 80-100 reservations (past 90 days to future 30 days)
- 40-50 check-ins linked to past confirmed reservations
- 100+ session logs (admin + recepcion, PC + Mobile)
- 4-6 iCal feeds (Booking/Airbnb URLs for select rooms)

REQUIRES: seed_monges.py must be run first (creates property, rooms, categories, etc.)

USAGE:
    python scripts/seed_test_data.py              # Generate test data
    python scripts/seed_test_data.py --dry-run    # Show what would be generated
    python scripts/seed_test_data.py --reset      # Clear test data and re-generate

SAFETY:
    - Checks if seed_monges.py data exists before running
    - Safe to run multiple times (skips if reservations already exist)
    - Use --reset to clear and regenerate
"""

import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4

# ============================================
# CONFIGURATION
# ============================================

SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
DB_PATH = BACKEND_DIR / "hotel.db"

PROPERTY_ID = "los-monges"

# Seed for reproducibility (change to get different data)
RANDOM_SEED = 42

# ============================================
# DATA POOLS
# ============================================

FIRST_NAMES_M = [
    "Juan", "Carlos", "Pedro", "Diego", "Luis", "Jorge", "Miguel", "Fernando",
    "Roberto", "Eduardo", "Alberto", "Ricardo", "Gabriel", "Sebastian", "Matias",
    "Alejandro", "Daniel", "Rafael", "Oscar", "Gustavo", "Hugo", "Andres",
    "Marcos", "Pablo", "Victor", "Mario", "Julio", "Ramon", "Ignacio", "Tomas",
]
FIRST_NAMES_F = [
    "Maria", "Ana", "Lucia", "Carmen", "Rosa", "Patricia", "Laura", "Claudia",
    "Silvia", "Marta", "Elena", "Beatriz", "Adriana", "Monica", "Sandra",
    "Gabriela", "Valeria", "Camila", "Sofia", "Isabella", "Natalia", "Carolina",
    "Victoria", "Paula", "Andrea", "Lorena", "Veronica", "Marcela", "Liliana", "Diana",
]
LAST_NAMES = [
    "Gonzalez", "Rodriguez", "Fernandez", "Lopez", "Martinez", "Garcia", "Perez",
    "Sanchez", "Ramirez", "Torres", "Flores", "Rojas", "Mendoza", "Acosta",
    "Benitez", "Gimenez", "Villalba", "Cabrera", "Ortiz", "Romero",
    "Diaz", "Morales", "Alvarez", "Castro", "Vargas", "Medina", "Herrera",
    "Riquelme", "Lezcano", "Aquino", "Ayala", "Barrios", "Britez", "Cardozo",
    "Dominguez", "Espinola", "Franco", "Gauto", "Insaurralde", "Jara",
]

NATIONALITIES = [
    ("Paraguaya", "Paraguay", 50),
    ("Brasilera", "Brasil", 25),
    ("Argentina", "Argentina", 12),
    ("Uruguaya", "Uruguay", 3),
    ("Chilena", "Chile", 3),
    ("Colombiana", "Colombia", 2),
    ("Boliviana", "Bolivia", 2),
    ("Peruana", "Peru", 2),
    ("Estadounidense", "Estados Unidos", 1),
]

CITIES_ORIGIN = [
    "Ciudad del Este", "Asuncion", "Encarnacion", "Luque", "San Lorenzo",
    "Foz do Iguacu", "Curitiba", "Sao Paulo", "Buenos Aires", "Posadas",
    "Montevideo", "Santa Cruz", "Hernandarias", "Caaguazu", "Villarrica",
    "Coronel Oviedo", "Pedro Juan Caballero", "Concepcion",
]

CITIES_DESTINATION = [
    "Ciudad del Este", "Asuncion", "Foz do Iguacu", "Encarnacion",
    "Hernandarias", "San Lorenzo", "Luque", "Caaguazu",
]

CIVIL_STATUSES = ["Soltero/a", "Casado/a", "Divorciado/a", "Viudo/a", "Union Libre"]

SOURCES_WEIGHTED = [
    ("Direct", 40),
    ("Booking.com", 25),
    ("Airbnb", 15),
    ("Telefono", 8),
    ("Facebook", 5),
    ("Instagram", 4),
    ("Google", 3),
]

RECEIVED_BY = ["admin", "recepcion", "recepcion"]  # recepcion is more common

CANCELLATION_REASONS = [
    "Cambio de planes del huesped",
    "Encontro mejor precio en otro lugar",
    "Problema personal / familiar",
    "Error en la reserva",
    "No se presento (No-show)",
    "Viaje cancelado",
    "Enfermedad",
]

VEHICLE_MODELS = [
    "Toyota Hilux", "Toyota Corolla", "Hyundai Tucson", "Chevrolet Onix",
    "Fiat Cronos", "Volkswagen Gol", "Nissan Kicks", "Honda HR-V",
    "Kia Sportage", "Mitsubishi L200", "Ford Ranger", "Renault Duster",
]

USER_AGENTS_PC = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/120.0",
]
USER_AGENTS_MOBILE = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/605.1.15",
    "Mozilla/5.0 (Linux; Android 14) Chrome/120.0 Mobile",
]


# ============================================
# HELPERS
# ============================================

def weighted_choice(items_with_weights):
    """Pick a random item based on weights. items_with_weights = [(item, weight), ...]"""
    items, weights = zip(*items_with_weights)
    return random.choices(items, weights=weights, k=1)[0]


def random_phone():
    """Generate a Paraguayan-style phone number."""
    prefix = random.choice(["0971", "0981", "0982", "0983", "0991", "0961", "0972"])
    return f"{prefix} {random.randint(100, 999)} {random.randint(100, 999)}"


def random_document():
    """Generate a random CI (cedula de identidad) number."""
    return str(random.randint(1000000, 9999999))


def random_ruc():
    """Generate a random RUC number."""
    ci = random.randint(1000000, 9999999)
    dv = random.randint(0, 9)
    return f"{ci}-{dv}"


def random_time_between(start_h, start_m, end_h, end_m):
    """Generate a random time between two hour:minute pairs."""
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m
    rand_min = random.randint(start_min, end_min)
    return time(rand_min // 60, rand_min % 60)


def log(msg, level="INFO"):
    prefix = {"INFO": "[INFO]", "OK": "[ OK ]", "WARN": "[WARN]", "ERR": "[ERR ]"}
    print(f"  {prefix.get(level, '[????]')} {msg}")


# ============================================
# DATA GENERATORS
# ============================================

def generate_reservations(conn, rooms, categories, client_types, dry_run=False):
    """Generate 80-100 reservations spread across past 90 days to future 30 days."""
    today = date.today()
    start_date = today - timedelta(days=90)
    end_date = today + timedelta(days=30)

    num_reservations = random.randint(85, 100)
    log(f"Generating {num_reservations} reservations ({start_date} to {end_date})...")

    # Build room -> category price map
    room_prices = {}
    for room in rooms:
        cat = next((c for c in categories if c["id"] == room["category_id"]), None)
        room_prices[room["id"]] = cat["base_price"] if cat else 200000

    # Build category name map
    cat_names = {c["id"]: c["name"] for c in categories}

    # Get next reservation ID
    cursor = conn.execute("SELECT id FROM reservations ORDER BY id DESC LIMIT 1")
    last = cursor.fetchone()
    if last:
        try:
            next_num = int(last[0]) + 1
        except ValueError:
            next_num = 1001
    else:
        next_num = 1001

    reservations = []
    for i in range(num_reservations):
        res_id = f"{next_num + i:07d}"

        # Random check-in date, weighted toward recent past and near future
        days_offset = random.triangular(-90, 30, -10)
        check_in = today + timedelta(days=int(days_offset))
        if check_in < start_date:
            check_in = start_date
        if check_in > end_date:
            check_in = end_date

        stay_days = random.choices([1, 2, 3, 4, 5, 6, 7], weights=[25, 30, 20, 10, 7, 5, 3], k=1)[0]
        checkout_date = check_in + timedelta(days=stay_days)

        room = random.choice(rooms)
        room_id = room["id"]
        category_id = room["category_id"]
        base_price = room_prices.get(room_id, 200000)
        price = base_price * stay_days

        source = weighted_choice(SOURCES_WEIGHTED)

        # Client type based on source
        if source == "Booking.com":
            client_type_id = f"{PROPERTY_ID}-booking"
        elif source == "Airbnb":
            client_type_id = f"{PROPERTY_ID}-airbnb"
        else:
            ct_weights = [
                (f"{PROPERTY_ID}-particular", 60),
                (f"{PROPERTY_ID}-empresa", 15),
                (f"{PROPERTY_ID}-vip", 10),
                (f"{PROPERTY_ID}-grupo", 10),
                (f"{PROPERTY_ID}-agencia", 5),
            ]
            client_type_id = weighted_choice(ct_weights)

        # Status based on dates
        if checkout_date < today:
            status = random.choices(
                ["Completada", "Cancelada", "Confirmada"],
                weights=[70, 20, 10], k=1
            )[0]
        elif check_in <= today:
            status = random.choices(
                ["Confirmada", "Cancelada"],
                weights=[85, 15], k=1
            )[0]
        else:
            status = random.choices(
                ["Confirmada", "Pendiente", "Cancelada"],
                weights=[65, 25, 10], k=1
            )[0]

        # Guest name
        is_female = random.random() < 0.4
        first = random.choice(FIRST_NAMES_F if is_female else FIRST_NAMES_M)
        last = random.choice(LAST_NAMES)
        guest_name = f"{first} {last}"

        # Arrival time
        arrival_time = random_time_between(7, 0, 22, 0) if status != "Cancelada" else None

        # Parking
        parking_needed = random.random() < 0.3
        vehicle_model = random.choice(VEHICLE_MODELS) if parking_needed else None
        vehicle_plate = f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')} {random.randint(100, 999)}" if parking_needed else None

        # Cancellation
        cancellation_reason = random.choice(CANCELLATION_REASONS) if status == "Cancelada" else None
        cancelled_by = random.choice(["admin", "recepcion", "huesped"]) if status == "Cancelada" else None

        # External ID for OTA
        external_id = str(uuid4())[:8].upper() if source in ("Booking.com", "Airbnb") else None

        # Created at (slightly before check-in, 1-30 days)
        days_before = random.randint(1, 30)
        created_at = datetime.combine(check_in - timedelta(days=days_before), random_time_between(8, 0, 20, 0))
        if created_at.date() < start_date - timedelta(days=30):
            created_at = datetime.combine(start_date - timedelta(days=5), time(10, 0))

        reservation = {
            "id": res_id,
            "created_at": created_at.isoformat(),
            "check_in_date": check_in.isoformat(),
            "stay_days": stay_days,
            "guest_name": guest_name,
            "room_id": room_id,
            "room_type": cat_names.get(category_id, "Standard"),
            "price": price,
            "arrival_time": arrival_time.isoformat() if arrival_time else None,
            "reserved_by": guest_name if source in ("Booking.com", "Airbnb") else random.choice([guest_name, "Telefono", "Facebook"]),
            "contact_phone": random_phone(),
            "received_by": random.choice(RECEIVED_BY),
            "status": status,
            "cancellation_reason": cancellation_reason,
            "cancelled_by": cancelled_by,
            "property_id": PROPERTY_ID,
            "category_id": category_id,
            "client_type_id": client_type_id,
            "original_price": price,
            "final_price": price,
            "parking_needed": 1 if parking_needed else 0,
            "vehicle_model": vehicle_model,
            "vehicle_plate": vehicle_plate,
            "source": source,
            "external_id": external_id,
        }
        reservations.append(reservation)

    if dry_run:
        log(f"[DRY RUN] Would insert {len(reservations)} reservations")
        # Show distribution
        statuses = {}
        sources_count = {}
        for r in reservations:
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
            sources_count[r["source"]] = sources_count.get(r["source"], 0) + 1
        log(f"  Status distribution: {statuses}")
        log(f"  Source distribution: {sources_count}")
        return reservations

    for r in reservations:
        columns = ", ".join(r.keys())
        placeholders = ", ".join(["?" for _ in r])
        conn.execute(f"INSERT INTO reservations ({columns}) VALUES ({placeholders})", tuple(r.values()))

    log(f"{len(reservations)} reservations inserted", "OK")
    return reservations


def generate_checkins(conn, reservations, rooms, dry_run=False):
    """Generate 40-50 check-ins linked to past confirmed/completed reservations."""
    today = date.today()

    # Filter eligible reservations (past, not cancelled)
    eligible = [
        r for r in reservations
        if r["status"] in ("Confirmada", "Completada")
        and date.fromisoformat(r["check_in_date"]) <= today
    ]
    random.shuffle(eligible)

    num_checkins = min(random.randint(40, 50), len(eligible))
    log(f"Generating {num_checkins} check-ins from {len(eligible)} eligible reservations...")

    checkins = []
    for i in range(num_checkins):
        res = eligible[i]
        check_in_date = date.fromisoformat(res["check_in_date"])

        # Parse guest name
        parts = res["guest_name"].split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else "N/A"

        # Nationality — pick using weights, then extract nat + country
        nat_entry = weighted_choice([((n, c), w) for n, c, w in NATIONALITIES])
        nat, country = nat_entry

        checkin = {
            "room_id": res["room_id"],
            "reservation_id": res["id"],
            "created_at": check_in_date.isoformat(),
            "check_in_time": random_time_between(7, 0, 22, 0).isoformat(),
            "last_name": last_name,
            "first_name": first_name,
            "nationality": nat,
            "birth_date": (date.today() - timedelta(days=random.randint(20*365, 65*365))).isoformat(),
            "origin": random.choice(CITIES_ORIGIN),
            "destination": random.choice(CITIES_DESTINATION),
            "civil_status": random.choice(CIVIL_STATUSES),
            "document_number": random_document(),
            "country": country,
            "billing_name": f"{first_name} {last_name}" if random.random() < 0.4 else "",
            "billing_ruc": random_ruc() if random.random() < 0.3 else "",
            "vehicle_model": res.get("vehicle_model") or "",
            "vehicle_plate": res.get("vehicle_plate") or "",
            "digital_signature": "Pendiente",
        }
        checkins.append(checkin)

    if dry_run:
        log(f"[DRY RUN] Would insert {len(checkins)} check-ins")
        return checkins

    for c in checkins:
        columns = ", ".join(c.keys())
        placeholders = ", ".join(["?" for _ in c])
        conn.execute(f"INSERT INTO checkins ({columns}) VALUES ({placeholders})", tuple(c.values()))

    log(f"{len(checkins)} check-ins inserted", "OK")
    return checkins


def generate_session_logs(conn, dry_run=False):
    """Generate 100+ session logs spread across past 90 days."""
    today = datetime.now()
    start = today - timedelta(days=90)

    num_sessions = random.randint(110, 140)
    log(f"Generating {num_sessions} session logs...")

    sessions = []
    for _ in range(num_sessions):
        username = random.choices(["admin", "recepcion"], weights=[30, 70], k=1)[0]
        device_type = random.choices(["PC", "Mobile"], weights=[65, 35], k=1)[0]

        # Random login time
        days_ago = random.randint(0, 90)
        login_dt = today - timedelta(days=days_ago, hours=random.randint(0, 23), minutes=random.randint(0, 59))

        # Session duration: 10 min to 10 hours
        duration_min = random.randint(10, 600)
        logout_dt = login_dt + timedelta(minutes=duration_min)

        # 80% closed, 20% still active (only recent ones)
        if days_ago <= 1 and random.random() < 0.2:
            status = "active"
            logout_time = None
            closed_reason = None
        else:
            status = "closed"
            logout_time = logout_dt.isoformat()
            closed_reason = random.choices(
                ["manual_logout", "tab_closed", "session_expired", "server_restart"],
                weights=[50, 30, 15, 5], k=1
            )[0]

        ua = random.choice(USER_AGENTS_PC if device_type == "PC" else USER_AGENTS_MOBILE)
        ip = f"192.168.1.{random.randint(10, 254)}" if device_type == "PC" else f"10.0.0.{random.randint(10, 254)}"

        session = {
            "session_id": str(uuid4()),
            "username": username,
            "login_time": login_dt.isoformat(),
            "logout_time": logout_time,
            "ip_address": ip,
            "user_agent": ua,
            "device_type": device_type,
            "status": status,
            "closed_reason": closed_reason,
        }
        sessions.append(session)

    if dry_run:
        log(f"[DRY RUN] Would insert {num_sessions} session logs")
        pc = sum(1 for s in sessions if s["device_type"] == "PC")
        log(f"  Device distribution: PC={pc}, Mobile={num_sessions - pc}")
        return sessions

    for s in sessions:
        columns = ", ".join(s.keys())
        placeholders = ", ".join(["?" for _ in s])
        conn.execute(f"INSERT INTO session_logs ({columns}) VALUES ({placeholders})", tuple(s.values()))

    log(f"{len(sessions)} session logs inserted", "OK")
    return sessions


def generate_ical_feeds(conn, rooms, dry_run=False):
    """Generate 4-6 fake iCal feed entries for select rooms."""
    # Pick 3 rooms for Booking, 2 for Airbnb
    sample_rooms = random.sample(rooms, min(5, len(rooms)))

    feeds = []
    for i, room in enumerate(sample_rooms):
        source = "Booking.com" if i < 3 else "Airbnb"
        if source == "Booking.com":
            url = f"https://admin.booking.com/hotel/hoteladmin/ical.html?t=fake-{uuid4().hex[:12]}"
        else:
            url = f"https://www.airbnb.com/calendar/ical/fake-{uuid4().hex[:12]}.ics"

        feeds.append({
            "room_id": room["id"],
            "source": source,
            "ical_url": url,
            "sync_enabled": 1,
            "created_at": datetime.now().isoformat(),
        })

    if dry_run:
        log(f"[DRY RUN] Would insert {len(feeds)} iCal feeds")
        return feeds

    for f in feeds:
        columns = ", ".join(f.keys())
        placeholders = ", ".join(["?" for _ in f])
        conn.execute(f"INSERT INTO ical_feeds ({columns}) VALUES ({placeholders})", tuple(f.values()))

    log(f"{len(feeds)} iCal feeds inserted", "OK")
    return feeds


# ============================================
# RESET
# ============================================

def reset_test_data(conn, dry_run=False):
    """Remove generated test data (reservations, checkins, sessions, ical_feeds)."""
    tables = ["checkins", "reservations", "session_logs", "ical_feeds"]
    for table in tables:
        if dry_run:
            cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            log(f"[DRY RUN] Would delete {count} rows from {table}")
        else:
            cursor = conn.execute(f"DELETE FROM {table}")
            log(f"Deleted {cursor.rowcount} rows from {table}", "OK")


# ============================================
# MAIN
# ============================================

def main():
    parser = argparse.ArgumentParser(description="Generate test data for pre-production testing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated")
    parser.add_argument("--reset", action="store_true", help="Clear test data before generating")
    parser.add_argument("--db-path", type=str, help="Custom database path")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED, help="Random seed for reproducibility")
    args = parser.parse_args()

    random.seed(args.seed)
    db_path = Path(args.db_path) if args.db_path else DB_PATH

    print()
    print("  HOTEL MUNICH - TEST DATA GENERATOR")
    print()

    if not db_path.exists():
        log(f"Database not found: {db_path}", "ERR")
        log("Run seed_monges.py first to create the base data.", "ERR")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    # Verify base seed exists
    cursor = conn.execute("SELECT COUNT(*) FROM rooms WHERE property_id = ?", (PROPERTY_ID,))
    room_count = cursor.fetchone()[0]
    if room_count == 0:
        log("No rooms found for Los Monges. Run seed_monges.py first.", "ERR")
        conn.close()
        sys.exit(1)

    # Check if test data already exists
    cursor = conn.execute("SELECT COUNT(*) FROM reservations WHERE property_id = ?", (PROPERTY_ID,))
    existing_reservations = cursor.fetchone()[0]

    if existing_reservations > 0 and not args.reset:
        log(f"Found {existing_reservations} existing reservations.", "WARN")
        log("Use --reset to clear and regenerate test data.", "WARN")
        conn.close()
        sys.exit(0)

    # Load rooms and categories
    rooms = [dict(r) for r in conn.execute(
        "SELECT id, category_id, property_id FROM rooms WHERE property_id = ? AND active = 1",
        (PROPERTY_ID,)
    ).fetchall()]

    categories = [dict(r) for r in conn.execute(
        "SELECT id, name, base_price FROM room_categories WHERE property_id = ?",
        (PROPERTY_ID,)
    ).fetchall()]

    client_types = [dict(r) for r in conn.execute(
        "SELECT id, name FROM client_types WHERE property_id = ?",
        (PROPERTY_ID,)
    ).fetchall()]

    log(f"Found {len(rooms)} rooms, {len(categories)} categories, {len(client_types)} client types")

    try:
        if not args.dry_run:
            conn.execute("BEGIN TRANSACTION")

        # Reset if requested
        if args.reset:
            log("Resetting existing test data...")
            reset_test_data(conn, args.dry_run)
            print()

        # Generate data
        print()
        reservations = generate_reservations(conn, rooms, categories, client_types, args.dry_run)
        print()
        checkins = generate_checkins(conn, reservations, rooms, args.dry_run)
        print()
        sessions = generate_session_logs(conn, args.dry_run)
        print()
        feeds = generate_ical_feeds(conn, rooms, args.dry_run)

        if not args.dry_run:
            conn.commit()

        # Summary
        print()
        print("  " + "=" * 50)
        print("  TEST DATA GENERATION COMPLETE")
        print("  " + "=" * 50)
        print()
        log(f"Reservations: {len(reservations)}")
        log(f"Check-ins:    {len(checkins)}")
        log(f"Sessions:     {len(sessions)}")
        log(f"iCal feeds:   {len(feeds)}")

        if args.dry_run:
            print()
            log("This was a DRY RUN. No data was written.", "WARN")

        print()

    except Exception as e:
        if not args.dry_run:
            conn.rollback()
        log(f"Error: {e}", "ERR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
