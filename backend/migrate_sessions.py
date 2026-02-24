"""
Migration script to add session tracking columns to session_logs table.
Run once to update existing database schema.
"""
import sqlite3
import os

# Get database path
DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(DB_DIR, "hotel.db")

def migrate():
    print(f"Connecting to database: {DB_NAME}")
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Check which columns already exist
    cursor.execute("PRAGMA table_info(session_logs)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns: {existing_columns}")
    
    migrations = []
    
    if "device_type" not in existing_columns:
        migrations.append("ALTER TABLE session_logs ADD COLUMN device_type TEXT DEFAULT 'PC' NOT NULL")
    
    if "status" not in existing_columns:
        migrations.append("ALTER TABLE session_logs ADD COLUMN status TEXT DEFAULT 'active' NOT NULL")
    
    if "closed_reason" not in existing_columns:
        migrations.append("ALTER TABLE session_logs ADD COLUMN closed_reason TEXT")
    
    if not migrations:
        print("No migrations needed - all columns exist.")
    else:
        for sql in migrations:
            print(f"Running: {sql}")
            cursor.execute(sql)
        
        conn.commit()
        print(f"Successfully added {len(migrations)} column(s)")
    
    conn.close()

if __name__ == "__main__":
    migrate()
