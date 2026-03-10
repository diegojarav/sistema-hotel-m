---
name: hotel-health-check
description: Run KPI evaluation tests, analyze scores, and flag any regressions in the Hotel PMS.
---

# Hotel Health Check

Run the KPI evaluation suite and present a scored report.

## Steps

1. Navigate to the backend directory:
   ```
   cd backend
   ```

2. Run KPI evaluation tests:
   ```
   python -m pytest tests/test_kpis.py -v -m kpi
   ```

3. Find and read the latest KPI JSON report:
   ```
   ls -t backend/tests/reports/kpi_*.json | head -1
   ```
   Then read the file contents.

4. Present results as a scored table:
   - Show each KPI name, score (out of 100), and pass/fail
   - Calculate overall average score
   - Flag any KPI scoring below 90/100 with a warning
   - Flag any KPI scoring below 70/100 as critical

5. Run the full test suite to confirm nothing is broken:
   ```
   python -m pytest tests/ -v -k "not perf"
   ```

6. Summarize: total tests, pass rate, KPI overall score, and any action items.

## Thresholds

- **Overall KPI Score >= 95**: Excellent health
- **Overall KPI Score 90-94**: Good, minor attention needed
- **Overall KPI Score 80-89**: Warning, investigate flagged KPIs
- **Overall KPI Score < 80**: Critical, immediate attention required

## KPIs Measured

| KPI | What It Measures |
|-----|-----------------|
| Booking Integrity | Reservation create/cancel roundtrips |
| Occupancy Accuracy | Occupancy calculations vs expected |
| Pricing Accuracy | Price calculations vs manual expectations |
| API Response Time | Endpoint response times under threshold |
| Data Consistency | CRUD cycles with zero orphans |
| Calendar Sync | Calendar views agree with each other |
| Revenue Accuracy | Revenue calculations match manual sums |
| Security Compliance | Protected endpoints reject unauthenticated |
