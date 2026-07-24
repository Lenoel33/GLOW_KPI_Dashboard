# L’Harmoni Source Audit Fix

Fixed a `NameError` in the **Source and field audit** section of the L’Harmoni dashboard.

The page now retrieves these matched fields before building the audit table:

- Attendance status
- Senior name
- Senior identifier

Validation completed:

- Python syntax checks passed
- 11 automated tests passed
