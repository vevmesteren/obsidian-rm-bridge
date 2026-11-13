# SDD ledger — plan: phase-5b-pull-marker-blocks (context package)

## Pre-flight interface scan
- INC-002 changes `retrieve_to_json` sections shape from `format_annotations(...)` header-wrapped to `{"page","text"}` raw. Existing test `test_retrieve_to_json_returns_sections` asserts `"Note on page 1" in sections[0]["text"]` and `page==1` — both still hold with raw text. Ruling: no test change needed, existing test remains valid. Cost if wrong: test fails, fix test.
- INC-001 publisher.py calls `strip_marker_blocks` before `render_mermaid_blocks`. Import must be added. No conflict.
- INC-003 types.ts `OrmbResult.data` union widen to include `OrmbPullData`. Existing tests access `res.data?.pages` (publish) — union member still has pages. Ruling: keep OrmbPublishData accessible; pull data is separate. Cost: TS compile error if narrowing wrong.

## Tasks

Task INC-001: complete (commits 8a0e6a3..07e2eef, tests: python3 -m pytest tests/ -q → 151 passed, 6 skipped)

Task INC-002: complete (commits 07e2eef..02ec3e2, tests: python3 -m pytest tests/ -q → 153 passed, 6 skipped)

Task INC-003/004/005: complete (commits 02ec3e2..8ae491c, tests: npm test → 27 passed; npm run build → main.js 21.5kb)

## Rulings
- R1: Extracted marker-block logic (buildMarkerBlock, stripExistingAnnotations, applyMarkerBlock, buildConsentBody) into pure module plugin/src/marker-block.ts instead of private methods on the plugin class. Why: the plugin class imports `obsidian` (Electron/browser API) which cannot be imported in node:test; the existing test suite never instantiates the plugin. Pure module = unit-testable without an obsidian mock harness not present in the repo. Cost if wrong: methods that should be on the class per spec are module functions; behavior identical, main.ts composes them.
- R2: stripExistingAnnotations uses slice-to-first-marker + trimEnd instead of regex `<!-- ... -->[\s\S]*$` replace + trimEnd. Why: the spec's regex+trimEnd would trim trailing whitespace even when no marker is present (altering clean content). The slice approach preserves no-marker content verbatim and is equivalent for the marker-present case. Cost if wrong: none observable; identical output for all test cases.
- R3: showPullConsentModal is not given a full Modal-interaction unit test (only its body text is tested via buildConsentBody). Why: testing the Modal button wiring requires an obsidian mock harness not present in the repo. The disclosure wording (the consent-relevant content) is tested. Cost if wrong: a button-wiring regression could ship uncaught.
- R4: noticeForResult reused for pull error codes. Why: pull shares error codes (not_paired, key_missing, etc.) with publish. Success code "transcribed" handled inline. Cost if wrong: a pull-specific error code would get the generic "ormb error: <msg>" fallback — acceptable.
