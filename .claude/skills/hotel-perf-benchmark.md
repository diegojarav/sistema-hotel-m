---
name: hotel-perf-benchmark
description: Run performance benchmarks on critical Hotel PMS code paths and report timing results.
---

# Hotel Performance Benchmark

Run performance benchmarks and present timing results.

## Steps

1. Navigate to the backend directory:
   ```
   cd backend
   ```

2. Run performance benchmark tests:
   ```
   python -m pytest tests/test_performance.py -v -m perf
   ```

3. Find and read the latest performance JSON report:
   ```
   ls -t backend/tests/reports/perf_*.json | head -1
   ```
   Then read the file contents.

4. Present results as a timing table:
   - Show each benchmark name, data size, duration (ms), threshold (ms), and pass/fail
   - Calculate overall pass rate
   - Flag any benchmark exceeding its threshold

5. If any benchmarks fail:
   - Read the relevant service source code
   - Identify potential bottlenecks (N+1 queries, missing indexes, unnecessary loops)
   - Suggest specific optimizations

6. Compare against previous runs if reports exist:
   ```
   ls -t backend/tests/reports/perf_*.json | head -5
   ```
   If multiple reports exist, compare timings and flag regressions (>20% slower).

## Benchmarks Measured

| Benchmark | Data Sizes | Method |
|-----------|------------|--------|
| Occupancy Map | 10, 100, 500 | get_occupancy_map() |
| Today Summary | 10, 100, 500 | get_today_summary() |
| Monthly Room View | 10, 100, 500 | get_monthly_room_view() |
| Revenue Matrix | 10, 100, 500 | get_revenue_by_room_month() |
| Room Report | 10, 100, 500 | get_room_report() |
| Price Calculation | 100 calls | calculate_price() avg |
| API Endpoints | 100 reservations | TestClient response time |

## Thresholds

- All service methods: Scale sub-linearly with data size
- Price calculation: < 50ms average per call
- API endpoints: < 500ms with 100 reservations
- Pass rate >= 90%: Performance is healthy
- Pass rate < 90%: Investigate slowest benchmarks
