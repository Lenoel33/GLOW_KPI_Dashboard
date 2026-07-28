# APRIL Missing-Data Audit Fix

## Changes

- APRIL KPIs now continue calculating from usable evidence even when other rows are incomplete.
- Added a row-level missing-data audit for recognised APRIL fields.
- Incomplete rows are separated from rows accepted by the audit.
- Each excluded row shows its source file, source sheet, source row, participant, centre, issue count and exact missing/invalid fields.
- Added an audit issue summary and a CSV download button.
- Added support for Outcome Monitoring, Caregiver Engaged and Follow-up Completed headers.
- Missing values affect only the relevant KPI or workflow field; they do not make the full dashboard unavailable.

## Verification

Tested with `Project_APRIL_Mock_Data_With_Missing_Fields.xlsx`:

- Seniors onboarded: 1,000
- Risk flags detected: 800
- Validations recorded: 800
- Complete annual assessment sets: 789
- Seniors with assessment evidence: 924
- Rows accepted by audit: 609
- Rows requiring correction: 392

Automated tests: 11 passed.
