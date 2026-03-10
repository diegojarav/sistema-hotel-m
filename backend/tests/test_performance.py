"""
Hotel PMS - Performance Benchmark Tests
==========================================

Measures critical code path performance under increasing data sizes.
Establishes baseline thresholds for monthly regression monitoring.

Run:  cd backend && python -m pytest tests/test_performance.py -v -m perf
"""

import pytest
import time
from datetime import date, timedelta

from services import ReservationService, PricingService


# ==========================================
# SERVICE-LAYER BENCHMARKS
# ==========================================

@pytest.mark.perf
class TestOccupancyMapPerformance:
    """Benchmark get_occupancy_map() with increasing reservation counts."""

    @pytest.mark.parametrize("n,threshold_ms", [(10, 200), (100, 500), (500, 1500)])
    def test_occupancy_map_speed(self, db_session, seed_n_reservations, n, threshold_ms, perf_report):
        seed_n_reservations(n)

        today = date.today()
        start = time.perf_counter()
        result = ReservationService.get_occupancy_map(db_session, today.year, today.month)
        elapsed_ms = (time.perf_counter() - start) * 1000

        perf_report.record("get_occupancy_map", n, elapsed_ms, threshold_ms)
        assert elapsed_ms < threshold_ms, (
            f"get_occupancy_map({n} reservations): {elapsed_ms:.0f}ms > {threshold_ms}ms"
        )


@pytest.mark.perf
class TestTodaySummaryPerformance:
    """Benchmark get_today_summary() with increasing reservation counts."""

    @pytest.mark.parametrize("n,threshold_ms", [(10, 200), (100, 500), (500, 1500)])
    def test_today_summary_speed(self, db_session, seed_n_reservations, n, threshold_ms, perf_report):
        seed_n_reservations(n)

        start = time.perf_counter()
        result = ReservationService.get_today_summary(db_session)
        elapsed_ms = (time.perf_counter() - start) * 1000

        perf_report.record("get_today_summary", n, elapsed_ms, threshold_ms)
        assert elapsed_ms < threshold_ms, (
            f"get_today_summary({n} reservations): {elapsed_ms:.0f}ms > {threshold_ms}ms"
        )


@pytest.mark.perf
class TestMonthlyRoomViewPerformance:
    """Benchmark get_monthly_room_view() with increasing reservation counts."""

    @pytest.mark.parametrize("n,threshold_ms", [(10, 200), (100, 500), (500, 1500)])
    def test_monthly_room_view_speed(self, db_session, seed_n_reservations, n, threshold_ms, perf_report):
        seed_n_reservations(n)

        today = date.today()
        start = time.perf_counter()
        result = ReservationService.get_monthly_room_view(db_session, today.year, today.month)
        elapsed_ms = (time.perf_counter() - start) * 1000

        perf_report.record("get_monthly_room_view", n, elapsed_ms, threshold_ms)
        assert elapsed_ms < threshold_ms, (
            f"get_monthly_room_view({n} reservations): {elapsed_ms:.0f}ms > {threshold_ms}ms"
        )


@pytest.mark.perf
class TestRevenueMatrixPerformance:
    """Benchmark get_revenue_by_room_month() with increasing reservation counts."""

    @pytest.mark.parametrize("n,threshold_ms", [(10, 200), (100, 1000), (500, 3000)])
    def test_revenue_matrix_speed(self, db_session, seed_n_reservations, n, threshold_ms, perf_report):
        seed_n_reservations(n)

        start = time.perf_counter()
        result = ReservationService.get_revenue_by_room_month(db_session, date.today().year)
        elapsed_ms = (time.perf_counter() - start) * 1000

        perf_report.record("get_revenue_by_room_month", n, elapsed_ms, threshold_ms)
        assert elapsed_ms < threshold_ms, (
            f"get_revenue_by_room_month({n} reservations): {elapsed_ms:.0f}ms > {threshold_ms}ms"
        )


@pytest.mark.perf
class TestRoomReportPerformance:
    """Benchmark get_room_report() with increasing reservation counts."""

    @pytest.mark.parametrize("n,threshold_ms", [(10, 200), (100, 500), (500, 2000)])
    def test_room_report_speed(self, db_session, seed_n_reservations, n, threshold_ms, perf_report):
        seed_n_reservations(n)

        start = time.perf_counter()
        result = ReservationService.get_room_report(
            db_session, date.today(), date.today() + timedelta(days=365)
        )
        elapsed_ms = (time.perf_counter() - start) * 1000

        perf_report.record("get_room_report", n, elapsed_ms, threshold_ms)
        assert elapsed_ms < threshold_ms, (
            f"get_room_report({n} reservations): {elapsed_ms:.0f}ms > {threshold_ms}ms"
        )


@pytest.mark.perf
class TestPriceCalculationPerformance:
    """Benchmark calculate_price() with 100 sequential calls."""

    def test_price_calculation_throughput(self, db_session, seed_pricing_data, perf_report):
        """100 price calculations should average under 50ms each."""
        data = seed_pricing_data
        iterations = 100

        start = time.perf_counter()
        for i in range(iterations):
            PricingService.calculate_price(
                db=db_session,
                property_id=data["prop_id"],
                category_id=data["cat_std"].id,
                check_in=date(2026, 5, 1) + timedelta(days=i),
                stay_days=(i % 5) + 1,
                client_type_id=data["c_std"].id,
            )
        total_ms = (time.perf_counter() - start) * 1000
        avg_ms = total_ms / iterations

        perf_report.record("calculate_price (avg)", iterations, avg_ms, 50)
        assert avg_ms < 50, f"calculate_price avg: {avg_ms:.1f}ms > 50ms ({iterations} calls in {total_ms:.0f}ms)"


# ==========================================
# API-LAYER BENCHMARKS
# ==========================================

@pytest.mark.perf
class TestAPIEndpointPerformance:
    """Benchmark API endpoints with seeded data via TestClient."""

    ENDPOINTS = [
        ("/api/v1/calendar/summary", 500),
        ("/api/v1/calendar/events?year=2026&month=3", 500),
        ("/api/v1/calendar/occupancy?year=2026&month=3", 500),
    ]

    @pytest.mark.parametrize("url,threshold_ms", ENDPOINTS)
    def test_api_speed(self, client, seed_rooms, seed_n_reservations, url, threshold_ms, perf_report):
        """Measure API response time with 100 seeded reservations."""
        seed_n_reservations(100)

        start = time.perf_counter()
        resp = client.get(url)
        elapsed_ms = (time.perf_counter() - start) * 1000

        perf_report.record(f"API {url.split('?')[0]}", 100, elapsed_ms, threshold_ms)
        assert resp.status_code == 200, f"{url}: status {resp.status_code}"
        assert elapsed_ms < threshold_ms, f"{url}: {elapsed_ms:.0f}ms > {threshold_ms}ms"
