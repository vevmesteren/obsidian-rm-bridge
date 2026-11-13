# Fix Worker — Phase 5a-0 CLI Contract Changes (Cold Review Findings)

You are on branch `opencode/phase-5a-0-cli-contract` in `/root/obsidian-rm-bridge`.

A cold review (deepseek/deepseek-v4-pro) found 12 issues in the implementation. You must fix ALL of them and add/fix tests. Then run pytest, commit, and push.

## CRITICAL — Must fix

### 1. Mermaid route handler disabled when vault_root=None (Item 8)

**Problem:** `render_mermaid_to_png` only installs the route interceptor when `vault_root` is provided. When `vault_root=None` (the default path used by `render_mermaid_blocks`), NO route interceptor is installed, leaving all URLs unfiltered. This is a security gap — the ARB requires the route interceptor to always be active.

**Fix:** Always install the route interceptor in `render_mermaid_to_png`, even when `vault_root=None`. When `vault_root=None`, the handler should:
- Allow `data:` URIs
- Allow the mermaid CDN URL (`MERMAID_JS_URL`)
- Block ALL `file://` URIs (since no vault to contain against)
- Block all other external URLs

When `vault_root` is provided:
- Allow `data:` URIs
- Allow the mermaid CDN URL
- Allow `file://` URIs that resolve inside `vault_root` (containment-checked)
- Block out-of-vault `file://` URIs
- Block all other external URLs

**Test:** Add a test that `render_mermaid_to_png` (without vault_root) installs the route handler and blocks file:// URIs.

## HIGH — Must fix

### 2. pull --all containment gap (Item 11)

**Problem:** In `cmd_pull`, when `args.pull_all` is True, the `--vault` containment check is NOT applied to the resolved md paths. The containment check only runs in the single-page path (after line 245).

**Fix:** In the `pull_all` branch of `cmd_pull`, when `vault_root` is not None, check that each resolved md path is `is_relative_to(vault_root)` before calling `retrieve()`. If any path is outside the vault, emit `path_containment` error (with `--json`) or stderr message (without `--json`) and return 1.

### 3. pull --all ignores --json (Item 1)

**Problem:** The `pull_all` path in `cmd_pull` doesn't emit a JSON envelope. It calls `retrieve()` for each file and returns 0 without any JSON output.

**Fix:** When `args.json` is True and `args.pull_all` is True, collect results from all retrieved files and emit a single JSON envelope with the combined results. Or at minimum, emit a success envelope `{"ok": true, "code": "transcribed", ...}` after all files are retrieved.

### 4. doc_exists skipped without --json (Item 4)

**Problem:** The doc_exists check (publish --on-exists=fail) only runs in the `--json` path. Without `--json`, the publish proceeds without checking if the doc exists.

**Fix:** The doc_exists check should run regardless of `--json`. When `--on-exists=fail` (default) and the doc exists:
- With `--json`: emit `{"ok": false, "code": "doc_exists", ...}` and return 1
- Without `--json`: print an error message to stderr and return 1

### 5. Incomplete error classification (Item 1)

**Problem:** The `_classify_error` function doesn't classify `chromium_missing`, `key_missing`, `rate_limited`, and `vision_failed` error codes. These are in the ARB spec but not handled.

**Fix:** Update `_classify_error` to handle:
- `chromium_missing` — detect Playwright/chromium-related errors
- `key_missing` — detect missing API key errors
- `rate_limited` — detect 429/rate limit errors (check for "429" or "rate" in error message)
- `vision_failed` — detect vision transcription failures (all pages failed)

## MEDIUM — Fix if feasible

### 6. Publish --json data missing pages and doc_id (Item 1)

**Fix:** Add `pages` (page count) to the publish --json success data. For `doc_id`, if rmapi doesn't return a UUID, use the destination name/path as a reasonable proxy (document this in the code).

### 7. Inconsistent vault path expansion (Item 5)

**Fix:** Use `expand_user_path` (the no-expandvars variant) consistently in `cmd_pull` wherever `--vault` or `args.vault` is consumed, instead of mixing `expand_user_path` with raw `os.path.expanduser`.

### 8. retrieve_to_json uses page_name as doc_id (Item 3)

**Fix:** If rmapi doesn't expose the reMarkable UUID through the current API, keep `page_name` as `doc_id` but add a comment explaining that `page_name` is the best available identifier through the current rmapi interface, and that a future `rmapi stat` call could provide the actual UUID. This is acceptable — the ARB example uses `abc123` but the plugin can work with the page name.

## LOW — Fix if quick

### 9. No integration test for route handler installation

**Fix:** Add a test (using mock) that verifies `page.route` is called when `render_mermaid_to_png` is invoked (both with and without vault_root).

### 10. config set-key with empty stdin succeeds silently

**Fix:** In `cmd_config`, when `config_cmd == "set-key"`, check if the key is empty after reading from stdin. If empty, print an error and return 1.

### 11. Containment tests don't cover pull_all path

**Fix:** Add a test that `pull --all --vault` with a path outside the vault returns `path_containment` and no files are opened.

### 12. doctor --json stdout vs stderr untested

**Fix:** Add a test that `doctor --json` output goes to stdout (not stderr).

## After fixing

1. Run `python3 -m pytest -q` — all tests (existing + new + fixed) must pass.
2. Commit: `git add -A && git commit -m "Phase 5a-0: fix cold review findings (1 CRITICAL, 4 HIGH, 3 MEDIUM, 4 LOW)"`
3. Push: `git push origin opencode/phase-5a-0-cli-contract`
4. Post a summary of what was fixed as a comment on issue #7.

## Constraints

- Do NOT break any existing test.
- Do NOT use shell=True.
- Do NOT merge the PR.
- Keep all changes focused on the findings above.