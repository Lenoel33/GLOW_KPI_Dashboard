# GLOW KPI Dashboard - v18 Summary KPI Fix

Fixes the KPI Overview issue where Summary values with thousands separators were parsed incorrectly.

Key fix:
- Summary sheet values like `1,017` now display as `1,017`, not `1`.
- KPI Overview remains locked to the Summary sheet `OVERALL TOTAL:` row.
- Charts and detailed tables can still use attendance/programme rows.

Upload the files inside this folder to GitHub. Do not upload the ZIP itself.

## v24 consistency fix
- KPI Overview IB/OB/Unique Member counts now use the same cleaned `Attended` rows as the Senior Attendance Frequency tables.
- IB/OB attendance-frequency rows are grouped by senior name so tab counts tally with KPI cards.
- Inactive KPI uses the highest recorded AAP count per senior and the same member-level logic as the inactive list.

## v31 Accuracy Cleanup
- Removed unsupported or inferred analytics that cannot be verified from the KPI Excel, including programme category charts, living-alone analysis, and recommendation sections.
- Programme preferences now use only real attendance rows from valid attendance sheets.
- IB/OB and gender views are separated clearly into tabs.
- One-time vs recurring is derived only from workbook attendance dates/sessions.
- Individual senior profile cards show only workbook-supported fields.


## v35 Automatic Centre Assignment
- Reads Centre/Center/Centre Name/Location/Site fields and automatically separates rows into the correct centre dashboard.
- Recognises GLOW Bukit Batok, SEEN Bukit Batok, GLOW Nanyang, and SEEN Nanyang aliases.
- Uses the uploaded filename/fallback centre only when a row has no centre, or to resolve the GLOW/SEEN label at the same location.
- A mixed-centre workbook is split by row so Bukit Batok and Nanyang data cannot mix.
- Multiple files for the same centre are appended rather than overwriting each other.
- Summary totals are assigned only when a workbook contains one detected centre, preventing a combined Summary row from being copied into multiple centre dashboards.
