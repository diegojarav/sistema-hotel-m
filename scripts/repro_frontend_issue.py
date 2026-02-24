
import sys
import os
from pathlib import Path

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

try:
    from services import PricingService
    from logging_config import get_logger
    
    logger = get_logger(__name__)

    print(f"Calling PricingService.get_client_types() with no arguments...")
    try:
        types = PricingService.get_client_types()
        print(f"Result: {types}")
        if not types:
            print("WARNING: Returned empty list!")
        else:
            print(f"SUCCESS: Found {len(types)} types.")
            for t in types:
                print(f" - {t['name']} (ID: {t['id']})")
                
    except Exception as e:
        print(f"ERROR calling get_client_types: {e}")
        import traceback
        traceback.print_exc()

except ImportError as e:
    print(f"Import Error: {e}")
except Exception as e:
    print(f"General Error: {e}")
