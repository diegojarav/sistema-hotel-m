import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "hotel.db")

def list_users():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check schema
        cursor.execute("PRAGMA table_info(users)")
        columns = cursor.fetchall()
        print("Schema:", [col[1] for col in columns])

        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        
        print(f"Found {len(users)} users:")
        for user in users:
            print(user)
            
    except Exception as e:
        print(f"Error querying users: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    list_users()
