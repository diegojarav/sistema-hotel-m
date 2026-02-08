import sys
import os
import sqlite3
from datetime import date, datetime, timedelta

# Add backend to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))

from database import SessionLocal, RoomCategory, ClientType, PricingSeason
from services import PricingService

def verify_pricing():
    db = SessionLocal()
    print("running verification...")
    
    try:
        # 1. SETUP TEST DATA
        # Get IDs
        prop_id = "los-monges"
        cat_std_id = f"{prop_id}-estandar" # 150,000 Gs
        client_std_id = f"{prop_id}-particular" # 0%
        client_corp_id = f"{prop_id}-empresa" # 15%
        
        # 2. SCENARIO A: Standard Price (Normal Season, Particular)
        # 2026-06-01 is Normal Season (1.0)
        check_in_normal = date(2026, 6, 1)
        
        print(f"\n--- SCENARIO A: Standard Price ---")
        res_a = PricingService.calculate_price(
            db, prop_id, cat_std_id, check_in_normal, 1, client_std_id
        )
        price_a = res_a['final_price']
        print(f"Expected: 150,000 | Got: {price_a:,.0f}")
        assert price_a == 150000, f"Scenario A Failed: {price_a} != 150000"
        
        # 3. SCENARIO B: Client Discount (Normal Season, Empresa)
        # 150,000 - 15% (22,500) = 127,500
        print(f"\n--- SCENARIO B: Corporate Discount (-15%) ---")
        res_b = PricingService.calculate_price(
            db, prop_id, cat_std_id, check_in_normal, 1, client_corp_id
        )
        price_b = res_b['final_price']
        print(f"Expected: 127,500 | Got: {price_b:,.0f}")
        assert price_b == 127500, f"Scenario B Failed: {price_b} != 127500"
        
        # 4. SCENARIO C: System Season (Semana Santa +30%, Particular)
        # 2026-03-30 is inside Semana Santa (Mar 29 - Apr 05)
        # 150,000 + 30% (45,000) = 195,000
        check_in_high = date(2026, 3, 30)
        
        print(f"\n--- SCENARIO C: High Season (+30%) ---")
        res_c = PricingService.calculate_price(
            db, prop_id, cat_std_id, check_in_high, 1, client_std_id
        )
        price_c = res_c['final_price']
        print(f"Expected: 195,000 | Got: {price_c:,.0f}")
        assert price_c == 195000, f"Scenario C Failed: {price_c} != 195000"
        
        # 5. SCENARIO D: Combined (Semana Santa + Empresa)
        # Base: 150,000
        # Discount: -22,500 (15%) -> Subtotal 127,500
        # Season: +45,000 (30% of Base) -> Final 172,500
        # Logic in Service: "season_adjustment = total_base * (modifier - 1.0)"
        # "current_total += season_adjustment"
        # So: 150k - 22.5k + 45k = 172,500
        
        print(f"\n--- SCENARIO D: Combined (-15% + 30%) ---")
        res_d = PricingService.calculate_price(
            db, prop_id, cat_std_id, check_in_high, 1, client_corp_id
        )
        price_d = res_d['final_price']
        print(f"Expected: 172,500 | Got: {price_d:,.0f}")
        assert price_d == 172500, f"Scenario D Failed: {price_d} != 172500"
        
        print("\n✅ VERIFICATION SUCCESSFUL")
        
    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    verify_pricing()
