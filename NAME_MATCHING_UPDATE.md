# Name-based participant matching

This version identifies participants by the Name field rather than an ID field.

Matching rules:
- converts names to lowercase
- trims leading and trailing spaces
- collapses repeated spaces
- removes punctuation
- treats the normalized name as the participant key

ID fields are used only as a legacy fallback when no usable Name column exists.
APRIL audit rows now report "Missing Name" and display the normalized Name Key.
