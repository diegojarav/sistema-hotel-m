
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup path to backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from database import Base, ClientType, PricingSeason, RoomCategory, engine

SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

def check_data():
    print("--- CHECKING PRICING DATA ---")
    
    # 1. Client Types
    clients = session.query(ClientType).all()
    print(f"\n[Client Types] Found: {len(clients)}")
    for c in clients:
        print(f" - {c.name} (ID: {c.id}, Discount: {c.default_discount_percent}%)")
        
    required_clients = ["Particular", "Empresa", "Agencia"]
    missing_clients = [rc for rc in required_clients if not any(c.name == rc for c in clients)]
    
    if missing_clients:
        print(f"⚠️  MISSING CLIENT TYPES: {missing_clients}")
    else:
        print("✅ All required Client Types present.")

    # 2. Seasons
    seasons = session.query(PricingSeason).all()
    print(f"\n[Pricing Seasons] Found: {len(seasons)}")
    for s in seasons:
        print(f" - {s.name} ({s.start_date} to {s.end_date}, Mod: {s.price_modifier})")
        
    if not seasons:
        print("⚠️  NO SEASONS DEFINED. Dynamic pricing will be flat.")

    # 3. Room Categories
    cats = session.query(RoomCategory).all()
    print(f"\n[Room Categories] Found: {len(cats)}")
    for c in cats:
        print(f" - {c.name} (ID: {c.id}, Base: {c.base_price})")

    if not cats:
        print("⚠️  NO ROOM CATEGORIES. Base price will be 0.")

if __name__ == "__main__":
    check_data()
