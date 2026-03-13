#!/usr/bin/env python3
"""Quick DB diagnostic for staging."""
import sqlite3, os
db = os.path.join(os.path.dirname(__file__), "..", "backend", "hotel.db")
db = os.path.abspath(db)
c = sqlite3.connect(db)
print("=== client_types ===")
for r in c.execute("SELECT id, property_id, name, active, sort_order FROM client_types"):
    print(r)
print("\n=== properties ===")
for r in c.execute("SELECT id, name FROM properties"):
    print(r)
print("\n=== room_categories ===")
for r in c.execute("SELECT id, property_id, name, active FROM room_categories"):
    print(r)
c.close()
