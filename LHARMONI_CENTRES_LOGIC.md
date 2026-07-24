# L’Harmoni centre classification

The combined L’Harmoni view uses the uploaded row-level `Centres` field.

- `Centres` contains `Bukit Batok` → `GLOW Bukit Batok`
- `Centres` contains `Nanyang` → `GLOW Nanyang`
- Matching is case-insensitive and accepts additional text.
- Rows containing both terms or neither term are left unassigned and flagged.
- Participants are deduplicated using cleaned values from the `Name` field.

Verified with `L'harmoni1.xlsx`:

- Total unique participants: 3,601
- Bukit Batok unique participants: 2,134
- Nanyang unique participants: 1,550
- Unassigned rows: 0
