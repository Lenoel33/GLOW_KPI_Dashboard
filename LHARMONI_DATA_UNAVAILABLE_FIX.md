# L’Harmoni Data Unavailable Fix

This release fixes valid L’Harmoni data being displayed as Data unavailable.

Changes:
- Cumulative participation now counts all explicitly enrolled participants, rather than excluding valid enrolments outside the assessment-study window.
- The one-year denominator is restricted to seniors represented in tracked outcome evidence, so an ordinary enrolment register cannot inflate the denominator.
- Approved outcomes with valid follow-up dates calculate automatically; the custom timing-window checkbox no longer suppresses complete evidence.
- Explicit outcome-success fields are supported.
- Scrambled headers with harmless suffixes such as Extra, Field, Value, Column and Data are mapped more reliably.
- Three-year tracking supports both the configured project window and the latest completed three reporting years, using the better-supported source window.
- L’Harmoni control defaults are set to calculate approved timing and raw score evidence immediately.

Verification against AIC_Project_KPI_Mock_Scrambled_Fields_WITH_MISSING_DATA.xlsx:
- Participants: 1,000
- Bukit Batok: 500
- Nanyang: 500
- Tracked seniors due: 300
- Valid one-year outcomes: 300
- Improved or maintained: 180
- Official outcome rate: 60%
- One-year coverage: 100%
- Complete annual assessment sets: 100
- Unique seniors tracked over three years: 300

Automated tests: 11 passed.
