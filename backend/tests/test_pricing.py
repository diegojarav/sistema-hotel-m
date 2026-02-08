
import pytest
from datetime import date
from services import PricingService

def test_scenario_a_standard_price(db_session, seed_pricing_data):
    """
    SCENARIO A: Standard Price (Normal Season, Particular)
    Base: 150,000
    Modifier: 0%
    Expected: 150,000
    """
    data = seed_pricing_data
    check_in_normal = date(2026, 6, 1)

    res = PricingService.calculate_price(
        db_session, 
        data["prop_id"], 
        data["cat_std"].id, 
        check_in_normal, 
        1, 
        data["c_std"].id
    )
    
    assert res['final_price'] == 150000.0
    assert res['breakdown']['base_unit_price'] == 150000.0

def test_scenario_b_corporate_discount(db_session, seed_pricing_data):
    """
    SCENARIO B: Client Discount (Normal Season, Empresa)
    Base: 150,000
    Discount: -15% (22,500)
    Expected: 127,500
    """
    data = seed_pricing_data
    check_in_normal = date(2026, 6, 1)

    res = PricingService.calculate_price(
        db_session, 
        data["prop_id"], 
        data["cat_std"].id, 
        check_in_normal, 
        1, 
        data["c_corp"].id
    )
    
    assert res['final_price'] == 127500.0
    
def test_scenario_c_high_season(db_session, seed_pricing_data):
    """
    SCENARIO C: High Season (+30%)
    Base: 150,000
    Season: +30% (45,000)
    Expected: 195,000
    """
    data = seed_pricing_data
    # March 30th is in Semana Santa (March 29 - April 5)
    check_in_high = date(2026, 3, 30)

    res = PricingService.calculate_price(
        db_session, 
        data["prop_id"], 
        data["cat_std"].id, 
        check_in_high, 
        1, 
        data["c_std"].id
    )
    
    assert res['final_price'] == 195000.0

def test_scenario_d_combined(db_session, seed_pricing_data):
    """
    SCENARIO D: Combined (-15% + 30%)
    Base: 150,000
    Discount: -22,500
    Season Adjustment: +45,000
    Expected: 172,500
    """
    data = seed_pricing_data
    check_in_high = date(2026, 3, 30)

    res = PricingService.calculate_price(
        db_session, 
        data["prop_id"], 
        data["cat_std"].id, 
        check_in_high, 
        1, 
        data["c_corp"].id
    )
    
    assert res['final_price'] == 172500.0
