# GLOW KPI Dashboard - Summary KPI v8

This version fixes the KPI Overview by using the Excel `Summary` sheet as the source of truth.

## What changed
- KPI Overview reads the `OVERALL TOTAL:` row from `Summary`.
- Mandatory KPIs displayed: Programmes, Attendances, Unique Members, IB (%), OB (%), Male (%), Inactive (<=2AAP) (%), New IB, New OB.
- A Summary Sheet KPI Table is shown directly from Excel without recalculating values.
- Programme type filters only affect charts/tables, not the headline KPI Overview.
- Attendance sheets are still used for charts and activity insights, with duplicate records removed.
- Only aggregate KPI/chart values are stored; names and phone numbers are not stored.
