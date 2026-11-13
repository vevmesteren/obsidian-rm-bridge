# SDD ledger — plan: phase-5b-pull-marker-blocks (context package)

## Pre-flight interface scan
- INC-002 changes `retrieve_to_json` sections shape from `format_annotations(...)` header-wrapped to `{"page","text"}` raw. Existing test `test_retrieve_to_json_returns_sections` asserts `"Note on page 1" in sections[0]["text"]` and `page==1` — both still hold with raw text. Ruling: no test change needed, existing test remains valid. Cost if wrong: test fails, fix test.
- INC-001 publisher.py calls `strip_marker_blocks` before `render_mermaid_blocks`. Import must be added. No conflict.
- INC-003 types.ts `OrmbResult.data` union widen to include `OrmbPullData`. Existing tests access `res.data?.pages` (publish) — union member still has pages. Ruling: keep OrmbPublishData accessible; pull data is separate. Cost: TS compile error if narrowing wrong.

## Tasks
