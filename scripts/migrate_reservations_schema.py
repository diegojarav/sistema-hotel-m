import sqlite3
import os
from pathlib import Path

# Paths
SCRIPT_DIR = Path(os.path.abspath(os.path.dirname(__file__)))
PROJECT_ROOT = SCRIPT_DIR.parent
DB_PATH = PROJECT_ROOT / "backend" / "hotel.db"

def migrate_reservations():
    print("Migrating reservations table schema...")
    
    if not DB_PATH.exists():
        print(f"Error: Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    try:
        # Get existing columns
        cursor.execute("PRAGMA table_info(reservations)")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"Existing columns: {columns}")
        
        # Define new columns
        new_columns = [
            ("parking_needed", "BOOLEAN DEFAULT 0"),
            ("vehicle_model", "TEXT"),
            ("vehicle_plate", "TEXT"),
            ("source", "TEXT DEFAULT 'Direct'"),
            ("external_id", "TEXT")
        ]
        
        for col_name, col_def in new_columns:
            if col_name not in columns:
                print(f"Adding column: {col_name}")
                try:
                    cursor.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {col_def}")
                    print(f"  ✅ Added {col_name}")
                except Exception as e:
                    print(f"  ❌ Failed to add {col_name}: {e}")
            else:
                print(f"Column {col_name} already exists.")
                
        conn.commit()
        print("Migration complete.")
        
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_reservations()
