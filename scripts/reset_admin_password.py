import sqlite3
import os
import bcrypt

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "hotel.db")

def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt()
    ).decode('utf-8')

def reset_admin_password():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    new_password = "admin_password"
    hashed_password = get_password_hash(new_password)
    
    try:
        cursor.execute("UPDATE users SET password = ? WHERE username = 'admin'", (hashed_password,))
        conn.commit()
        
        if cursor.rowcount > 0:
            print(f"✅ Password for 'admin' reset to '{new_password}'")
        else:
            print("❌ User 'admin' not found.")
            
    except Exception as e:
        print(f"Error updating password: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    reset_admin_password()
