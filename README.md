# GLOW KPI Dashboard - v18 Summary KPI Fix

Fixes the KPI Overview issue where Summary values with thousands separators were parsed incorrectly.

Key fix:
- Summary sheet values like `1,017` now display as `1,017`, not `1`.
- KPI Overview remains locked to the Summary sheet `OVERALL TOTAL:` row.
- Charts and detailed tables can still use attendance/programme rows.

Upload the files inside this folder to GitHub. Do not upload the ZIP itself.
