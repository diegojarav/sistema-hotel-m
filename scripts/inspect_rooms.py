import sys
import os
import pandas as pd
from sqlalchemy import create_engine, text

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))
from database import DB_NAME

def inspect_data():
    if not os.path.exists(DB_NAME):
        print(f"Database not found at {DB_NAME}")
        return

    engine = create_engine(f"sqlite:///{DB_NAME}")
    
    print("\n--- ROOM CATEGORIES ---")
    with engine.connect() as conn:
        try:
            df_cats = pd.read_sql("SELECT * FROM room_categories", conn)
            if df_cats.empty:
                print("No categories found.")
            else:
                print(df_cats[['id', 'name', 'base_price', 'bed_configuration']].to_string())
        except Exception as e:
            print(f"Error querying categories: {e}")

    print("\n--- ROOMS ---")
    with engine.connect() as conn:
        try:
            df_rooms = pd.read_sql("SELECT * FROM rooms", conn)
            if df_rooms.empty:
                print("No rooms found.")
            else:
                print(df_rooms[['id', 'room_number', 'category_id', 'status']].to_string())
        except Exception as e:
            print(f"Error querying rooms: {e}")

if __name__ == "__main__":
    inspect_data()
