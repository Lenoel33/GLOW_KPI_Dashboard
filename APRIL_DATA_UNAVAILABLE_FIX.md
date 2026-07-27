# APRIL data-unavailable fix

This version fixes APRIL uploads that do not contain a separate Project column.

Changes:
- Detects APRIL tables from APRIL-specific fields such as APRIL Enrolled, Risk Flag and Risk Flag Validated.
- Recognises `APRIL Enrolled` and `Risk Flag Validated` headers.
- Accepts validated risk flags as official when the same senior has MMSE/GDS/SPPB assessment evidence.
- Preserves genuine missing-data handling: incomplete scores or missing assessment dates are excluded only from the affected assessment KPI.
