"""
Hotel PMS - KPI Evaluation Tests
==================================

Measures and reports Key Performance Indicators for the Hotel PMS.
Each test class targets one KPI, scores 0-100, and records results.

Run:  cd backend && python -m pytest tests/test_kpis.py -v -m kpi
"""

import pytest
import time
from datetime import date, timedelta

from services import ReservationService, PricingService, RoomService
from database import Reservation, CheckIn, Room


# ==========================================
# KPI 1: BOOKING INTEGRITY
# ==========================================

@pytest.mark.kpi
class TestBookingIntegrityKPI:
    """Verify reservations are created correctly with right data."""

    def test_single_reservation_roundtrip(self, db_session, make_reservation, kpi_report):
        """Create 1 reservation, verify all fields round-trip correctly."""
        checks_passed = 0
        checks_total = 5

        res = make_reservation(
            guest_name="Juan Perez",
            stay_days=3,
            price=450000.0,
            check_in_date=date.today() + timedelta(days=10),
        )

        fetched = ReservationService.get_reservation(db_session, res.id)
        if fetched is not None: checks_passed += 1
        if fetched and fetched.guest_name == "Juan Perez": checks_passed += 1
        if fetched and fetched.stay_days == 3: checks_passed += 1
        if fetched and fetched.check_in_date == date.today() + timedelta(days=10): checks_passed += 1
        if res.status == "Confirmada": checks_passed += 1

        score = (checks_passed / checks_total) * 100
        kpi_report.record("Booking Integrity - Roundtrip", score,
                          tests_passed=checks_passed, tests_total=checks_total)
        assert checks_passed == checks_total, f"Roundtrip: {checks_passed}/{checks_total}"

    def test_cancellation_restores_availability(self, db_session, seed_rooms, make_reservation, kpi_report):
        """Cancel a reservation, verify room becomes available."""
        checks_passed = 0
        checks_total = 2

        room = seed_rooms["rooms"][0]
        ci = date.today() + timedelta(days=5)
        res = make_reservation(room_id=room.id, check_in_date=ci, stay_days=2)

        result = ReservationService.cancel_reservation(db_session, res.id, "test", "test")
        if result: checks_passed += 1

        status_after = ReservationService.get_daily_status(db_session, ci)
        room_after = [r for r in status_after if r["room_id"] == room.id]
        if not room_after or room_after[0].get("status") in ("available", "free", "Libre", None):
            checks_passed += 1
        elif room_after and room_after[0].get("reservation_status") == "Cancelada":
            checks_passed += 1

        score = (checks_passed / checks_total) * 100
        kpi_report.record("Booking Integrity - Cancel", score,
                          tests_passed=checks_passed, tests_total=checks_total)
        assert checks_passed == checks_total, f"Cancel: {checks_passed}/{checks_total}"

    def test_batch_reservations_integrity(self, db_session, seed_rooms, make_reservation, kpi_report):
        """Create 10 reservations across rooms, verify all stored correctly."""
        rooms = seed_rooms["rooms"]
        checks_passed = 0
        total = 10

        for i in range(total):
            room = rooms[i % len(rooms)]
            res = make_reservation(
                room_id=room.id,
                guest_name=f"Guest {i}",
                check_in_date=date.today() + timedelta(days=30 + i * 3),
                stay_days=(i % 3) + 1,
            )
            fetched = ReservationService.get_reservation(db_session, res.id)
            if fetched and fetched.guest_name == f"Guest {i}":
                checks_passed += 1

        score = (checks_passed / total) * 100
        kpi_report.record("Booking Integrity - Batch", score,
                          tests_passed=checks_passed, tests_total=total)
        assert checks_passed == total


# ==========================================
# KPI 2: OCCUPANCY ACCURACY
# ==========================================

@pytest.mark.kpi
class TestOccupancyAccuracyKPI:
    """Verify occupancy calculations match expected values."""

    @pytest.mark.parametrize("occupied_count", [0, 1, 3, 6])
    def test_occupancy_percentage(self, db_session, seed_rooms, occupied_count, kpi_report):
        """Verify occupancy matches expected for known patterns."""
        rooms = seed_rooms["rooms"]
        total_rooms = len(rooms)
        target_date = date.today()

        for i in range(min(occupied_count, total_rooms)):
            room = rooms[i]
            res = Reservation(
                id=f"{5000 + occupied_count * 100 + i:07d}",
                check_in_date=target_date,
                stay_days=1,
                guest_name=f"Occ Guest {i}",
                room_id=room.id,
                status="Confirmada",
                price=150000.0,
                property_id="los-monges",
                source="Direct",
                reserved_by="test",
                received_by="test",
                contact_phone="",
            )
            db_session.add(res)
        db_session.commit()

        summary = ReservationService.get_today_summary(db_session)

        if hasattr(summary, "ocupadas"):
            actual_occupied = summary.ocupadas
        elif isinstance(summary, dict):
            actual_occupied = summary.get("ocupadas", summary.get("occupied", 0))
        else:
            actual_occupied = 0

        expected_occupied = min(occupied_count, total_rooms)
        passed = actual_occupied == expected_occupied

        score = 100.0 if passed else max(0, 100 - abs(actual_occupied - expected_occupied) * 20)
        kpi_report.record(
            f"Occupancy Accuracy - {occupied_count}/{total_rooms}",
            score, tests_passed=1 if passed else 0, tests_total=1,
            details={"expected": expected_occupied, "actual": actual_occupied}
        )
        assert passed, f"Expected {expected_occupied} occupied, got {actual_occupied}"


# ==========================================
# KPI 3: PRICING ACCURACY
# ==========================================

@pytest.mark.kpi
class TestPricingAccuracyKPI:
    """Verify price calculations against manually computed expected values."""

    @pytest.mark.parametrize("scenario", [
        {"name": "base_1n", "stay": 1, "client": None, "season": None, "expected_per_night": 150000},
        {"name": "base_3n", "stay": 3, "client": None, "season": None, "expected_per_night": 150000},
        {"name": "corp_1n", "stay": 1, "client": "empresa", "season": None, "expected_per_night": 127500},
        {"name": "high_1n", "stay": 1, "client": None, "season": "semana-santa", "expected_per_night": 195000},
    ])
    def test_price_scenario(self, db_session, seed_pricing_data, scenario, kpi_report):
        """Verify price calculation matches manual expectation."""
        data = seed_pricing_data

        kwargs = {
            "db": db_session,
            "property_id": data["prop_id"],
            "category_id": data["cat_std"].id,
            "check_in": date(2026, 4, 1) if scenario["season"] == "semana-santa" else date(2026, 5, 1),
            "stay_days": scenario["stay"],
            "client_type_id": data["c_corp"].id if scenario["client"] == "empresa" else data["c_std"].id,
        }
        if scenario["season"] == "semana-santa":
            kwargs["season_id"] = data["s_high"].id

        result = PricingService.calculate_price(**kwargs)
        expected_total = scenario["expected_per_night"] * scenario["stay"]
        actual_total = result.get("final_price", 0)

        diff = abs(actual_total - expected_total)
        tolerance = expected_total * 0.02
        passed = diff <= tolerance

        score = 100.0 if passed else max(0, 100 - (diff / max(expected_total, 1)) * 100)
        kpi_report.record(
            f"Pricing Accuracy - {scenario['name']}",
            score, tests_passed=1 if passed else 0, tests_total=1,
            details={"expected": expected_total, "actual": actual_total, "diff": diff}
        )
        assert passed, f"Price {scenario['name']}: expected {expected_total}, got {actual_total}"


# ==========================================
# KPI 4: API RESPONSE TIME
# ==========================================

@pytest.mark.kpi
class TestAPIResponseTimeKPI:
    """Measure endpoint response times against thresholds."""

    ENDPOINTS = [
        ("GET", "/api/v1/calendar/summary", 500),
        ("GET", "/api/v1/calendar/events?year=2026&month=3", 500),
        ("GET", "/api/v1/calendar/occupancy?year=2026&month=3", 500),
    ]

    @pytest.mark.parametrize("method,url,threshold_ms", ENDPOINTS)
    def test_endpoint_response_time(self, client, seed_rooms,
                                     method, url, threshold_ms, kpi_report):
        """Measure response time for a single endpoint."""
        start = time.perf_counter()
        resp = client.get(url)
        elapsed_ms = (time.perf_counter() - start) * 1000

        passed = elapsed_ms < threshold_ms and resp.status_code == 200

        score = 100.0 if passed else max(0, 100 - ((elapsed_ms - threshold_ms) / threshold_ms) * 100)
        kpi_report.record(
            f"API Response - {url.split('?')[0]}",
            score, tests_passed=1 if passed else 0, tests_total=1,
            details={"elapsed_ms": round(elapsed_ms, 1), "threshold_ms": threshold_ms}
        )
        assert passed, f"{url}: {elapsed_ms:.0f}ms (threshold {threshold_ms}ms)"


# ==========================================
# KPI 5: DATA CONSISTENCY
# ==========================================

@pytest.mark.kpi
class TestDataConsistencyKPI:
    """Verify CRUD cycles produce consistent data with zero orphans."""

    def test_reservation_crud_cycle(self, db_session, make_reservation, kpi_report):
        """Create -> Read -> Cancel cycle."""
        checks_passed = 0
        checks_total = 3

        res = make_reservation(guest_name="CRUD Test", stay_days=2)
        if res.id: checks_passed += 1

        fetched = ReservationService.get_reservation(db_session, res.id)
        if fetched and fetched.guest_name == "CRUD Test": checks_passed += 1

        cancelled = ReservationService.cancel_reservation(db_session, res.id, "test", "test")
        if cancelled: checks_passed += 1

        score = (checks_passed / checks_total) * 100
        kpi_report.record("Data Consistency - CRUD Cycle", score,
                          tests_passed=checks_passed, tests_total=checks_total)
        assert checks_passed == checks_total

    def test_cancelled_reservation_persists(self, db_session, make_reservation, kpi_report):
        """After cancellation, reservation exists with Cancelada status."""
        res = make_reservation(guest_name="Persist Test")
        res_id = res.id

        ReservationService.cancel_reservation(db_session, res_id, "cleanup", "test")

        fetched = db_session.query(Reservation).get(res_id)
        passed = fetched is not None and fetched.status == "Cancelada"

        score = 100.0 if passed else 0.0
        kpi_report.record("Data Consistency - Cancelled Persists", score,
                          tests_passed=1 if passed else 0, tests_total=1)
        assert passed


# ==========================================
# KPI 6: CALENDAR SYNC ACCURACY
# ==========================================

@pytest.mark.kpi
class TestCalendarSyncKPI:
    """Verify calendar views agree with each other."""

    def test_events_vs_occupancy_agreement(self, db_session, seed_rooms, make_reservation, kpi_report):
        """Monthly events and occupancy map should both show data."""
        today = date.today()
        for i in range(3):
            ci = today.replace(day=min(10 + i * 5, 28))
            make_reservation(
                room_id=seed_rooms["rooms"][i].id,
                check_in_date=ci,
                stay_days=2,
                guest_name=f"Cal Guest {i}",
            )

        events = ReservationService.get_monthly_events(db_session, today.year, today.month)
        occ_map = ReservationService.get_occupancy_map(db_session, today.year, today.month)

        event_count = len(events) if isinstance(events, list) else 0
        occupied_days = sum(1 for v in occ_map.values()
                           if isinstance(v, dict) and v.get("count", 0) > 0)

        passed = event_count > 0 and occupied_days > 0
        score = 100.0 if passed else 50.0

        kpi_report.record("Calendar Sync - Events vs Occupancy", score,
                          tests_passed=1 if passed else 0, tests_total=1,
                          details={"events": event_count, "occupied_days": occupied_days})
        assert passed, f"Events: {event_count}, Occupied days: {occupied_days}"


# ==========================================
# KPI 7: REVENUE ACCURACY
# ==========================================

@pytest.mark.kpi
class TestRevenueAccuracyKPI:
    """Verify revenue calculations match manual sums."""

    def test_room_report_revenue(self, db_session, seed_rooms, make_reservation, kpi_report):
        """Verify get_room_report() total_revenue matches sum of prices."""
        room = seed_rooms["rooms"][0]
        prices = [150000.0, 200000.0, 300000.0]
        expected_total = sum(prices)

        for i, price in enumerate(prices):
            make_reservation(
                room_id=room.id,
                guest_name=f"Revenue Guest {i}",
                check_in_date=date.today() + timedelta(days=5 + i * 5),
                stay_days=2,
                price=price,
                final_price=price,
            )

        start = date.today()
        end = date.today() + timedelta(days=60)
        report = ReservationService.get_room_report(db_session, start, end, room.internal_code)

        actual_total = 0
        if isinstance(report, dict):
            rooms_data = report.get("rooms", [])
            if rooms_data:
                actual_total = rooms_data[0].get("summary", {}).get("total_revenue", 0)

        diff = abs(actual_total - expected_total)
        tolerance = expected_total * 0.02
        passed = diff <= tolerance

        score = 100.0 if passed else max(0, 100 - (diff / max(expected_total, 1)) * 100)
        kpi_report.record("Revenue Accuracy - Room Report", score,
                          tests_passed=1 if passed else 0, tests_total=1,
                          details={"expected": expected_total, "actual": actual_total})
        assert passed, f"Revenue: expected {expected_total}, got {actual_total}"


# ==========================================
# KPI 8: SECURITY COMPLIANCE
# ==========================================

@pytest.mark.kpi
class TestSecurityComplianceKPI:
    """Verify all protected endpoints reject unauthenticated requests."""

    PROTECTED_ENDPOINTS = [
        ("GET", "/api/v1/reservations"),
        ("POST", "/api/v1/reservations"),
        ("GET", "/api/v1/reservations/weekly"),
        ("GET", "/api/v1/guests"),
        ("POST", "/api/v1/guests"),
        ("GET", "/api/v1/users"),
        ("POST", "/api/v1/users"),
    ]

    @pytest.mark.parametrize("method,url", PROTECTED_ENDPOINTS)
    def test_rejects_unauthenticated(self, client, seed_rooms, method, url, kpi_report):
        """Endpoint should return 401/403 without auth token."""
        if method == "GET":
            resp = client.get(url)
        elif method == "POST":
            resp = client.post(url, json={})

        passed = resp.status_code in (401, 403, 422)

        score = 100.0 if passed else 0.0
        kpi_report.record(
            f"Security - {method} {url}",
            score, tests_passed=1 if passed else 0, tests_total=1,
            details={"status": resp.status_code}
        )
        assert passed, f"{method} {url}: got {resp.status_code}, expected 401/403"


# ==========================================
# KPI 9: AGENT TOOL RELIABILITY
# ==========================================

@pytest.mark.kpi
class TestAgentToolsKPI:
    """Verify all AI agent tools are callable, return strings, and handle errors gracefully."""

    def test_all_tools_callable_and_documented(self, kpi_report):
        """Every tool in TOOLS_LIST must be callable and have a proper docstring."""
        from api.v1.endpoints.ai_tools import TOOLS_LIST

        checks_passed = 0
        checks_total = len(TOOLS_LIST) * 3  # callable + has docstring + has Args section

        for func in TOOLS_LIST:
            if callable(func):
                checks_passed += 1
            if func.__doc__:
                checks_passed += 1
                if "Args:" in func.__doc__ or "Returns:" in func.__doc__:
                    checks_passed += 1

        score = (checks_passed / checks_total) * 100
        kpi_report.record("Agent Tools - Callable & Documented", score,
                          tests_passed=checks_passed, tests_total=checks_total,
                          details={"tool_count": len(TOOLS_LIST)})
        assert checks_passed == checks_total, f"Tool docs: {checks_passed}/{checks_total}"

    def test_tools_return_strings(self, db_session, seed_rooms, make_reservation, kpi_report):
        """Each tool must return a non-empty string when called with valid inputs."""
        from api.v1.endpoints.ai_tools import TOOLS_LIST

        # Seed some data so tools have something to query
        room = seed_rooms["rooms"][0]
        today = date.today()
        make_reservation(
            room_id=room.id,
            guest_name="Agent Test Guest",
            check_in_date=today + timedelta(days=5),
            stay_days=2,
            price=200000.0,
            final_price=200000.0,
        )

        # Define valid inputs for each tool
        tomorrow = (today + timedelta(days=5)).strftime("%Y-%m-%d")
        month_start = today.replace(day=1).strftime("%Y-%m-%d")
        month_end = (today.replace(day=28) + timedelta(days=4)).replace(day=1).strftime("%Y-%m-%d")

        tool_inputs = {
            "check_availability": (tomorrow, 1),
            "get_hotel_rates": (),
            "get_today_summary": (),
            "search_guest": ("Agent",),
            "search_reservation": ("Agent Test",),
            "get_reservations_report": (month_start, month_end),
            "calculate_price": ("Estandar", tomorrow, 2),
            "get_occupancy_for_month": (today.year, today.month),
            "get_room_performance": (month_start, month_end),
            "get_booking_sources": (month_start, month_end),
            "get_parking_status": (tomorrow, tomorrow),
        }

        checks_passed = 0
        checks_total = len(TOOLS_LIST)
        failures = []

        for func in TOOLS_LIST:
            args = tool_inputs.get(func.__name__, ())
            try:
                result = func(*args)
                if isinstance(result, str) and len(result) > 0:
                    checks_passed += 1
                else:
                    failures.append(f"{func.__name__}: returned {type(result).__name__}")
            except Exception as e:
                failures.append(f"{func.__name__}: raised {type(e).__name__}: {e}")

        score = (checks_passed / checks_total) * 100
        kpi_report.record("Agent Tools - Return Strings", score,
                          tests_passed=checks_passed, tests_total=checks_total,
                          details={"failures": failures})
        assert checks_passed == checks_total, f"String returns: {checks_passed}/{checks_total}. Failures: {failures}"

    def test_tools_handle_invalid_input(self, kpi_report):
        """Tools must return error messages gracefully for invalid inputs (not raise exceptions)."""
        from api.v1.endpoints.ai_tools import TOOLS_LIST

        # Invalid inputs for tools that accept parameters
        invalid_tests = [
            ("check_availability", ("not-a-date",)),
            ("check_availability", ("2020-01-01",)),  # past date
            ("get_reservations_report", ("2026-03-31", "2026-03-01")),  # end before start
            ("calculate_price", ("NonExistentCategory", "2026-03-15", 2)),
            ("get_occupancy_for_month", (2026, 13)),  # month 13
            ("get_room_performance", ("invalid", "2026-03-31")),
            ("get_booking_sources", ("2026-03-31", "2026-03-01")),  # end before start
            ("get_parking_status", ("bad-date", "2026-03-31")),
        ]

        tool_map = {f.__name__: f for f in TOOLS_LIST}
        checks_passed = 0
        checks_total = len(invalid_tests)
        failures = []

        for func_name, args in invalid_tests:
            func = tool_map.get(func_name)
            if not func:
                failures.append(f"{func_name}: not found in TOOLS_LIST")
                continue
            try:
                result = func(*args)
                if isinstance(result, str) and len(result) > 0:
                    checks_passed += 1  # Graceful error message
                else:
                    failures.append(f"{func_name}: returned non-string for invalid input")
            except Exception as e:
                failures.append(f"{func_name}: raised {type(e).__name__} instead of error message")

        score = (checks_passed / checks_total) * 100
        kpi_report.record("Agent Tools - Error Handling", score,
                          tests_passed=checks_passed, tests_total=checks_total,
                          details={"failures": failures})
        assert checks_passed == checks_total, f"Error handling: {checks_passed}/{checks_total}. Failures: {failures}"
