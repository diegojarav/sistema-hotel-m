#!/usr/bin/env python3
"""Seed client_types table if empty. Safe to run multiple times."""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "..", "backend", "hotel.db")
db_path = os.path.abspath(db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

count = cur.execute("SELECT count(*) FROM client_types").fetchone()[0]
if count > 0:
    print(f"client_types already has {count} rows, skipping.")
else:
    rows = [
        ("los-monges-particular", "los-monges", "Particular", 0.0, 1, 1),
        ("los-monges-empresa", "los-monges", "Empresa", 15.0, 2, 1),
        ("los-monges-grupo", "los-monges", "Grupo", 10.0, 3, 1),
        ("los-monges-agencia", "los-monges", "Agencia", 20.0, 4, 1),
        ("los-monges-booking", "los-monges", "Booking.com", 0.0, 5, 1),
        ("los-monges-airbnb", "los-monges", "Airbnb", 0.0, 6, 1),
        ("los-monges-vip", "los-monges", "VIP / Frecuente", 10.0, 7, 1),
    ]
    cur.executemany(
        "INSERT INTO client_types (id, property_id, name, default_discount_percent, sort_order, active) VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    print(f"Inserted {len(rows)} client types.")

# Verify
for row in cur.execute("SELECT id, name FROM client_types ORDER BY sort_order"):
    print(f"  {row[0]}: {row[1]}")

conn.close()
