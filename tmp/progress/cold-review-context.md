# Cold Review — Phase 5a-0 CLI Contract Changes (PR #8)

You are a COLD REVIEWER. Your job is to independently review the implementation in PR #8 and report findings. You are NOT the developer. You must be critical and thorough.

## Repository

You are in `/root/obsidian-rm-bridge` on branch `opencode/phase-5a-0-cli-contract`.

## What was implemented

11 CLI contract changes from the ARB (docs/ARB-OBSIDIAN-PLUGIN.md, section "CLI Contract Changes (Phase 5a-0)"):

1. `--json` result envelope on `publish` and `pull` — JSON envelope with ok/code/message/data fields
2. `doctor --json` — new subcommand returning health schema
3. `pull --emit json` — returns annotation sections as JSON, no disk writes
4. `publish --on-exists=fail|content-only` — default fail with doc_exists code, content-only preserves annotations
5. `--vault <path>` flag — explicit vault root, takes precedence over config
6. `expandvars` removal on argv paths — expand_path should not apply expandvars to --md and --vault
7. rmapi resolution fallback — ORB_RMAPI_BIN env → config.rmapi.path → shutil.which → ~/.local/bin/rmapi
8. Mermaid security hardening — securityLevel: 'strict', htmlLabels: false, route interceptor
9. Config hardening — O_NOFOLLOW, fchmod 0600, S_ISREG/st_uid check
10. `config set-key` — stdin-based key entry, key never in argv
11. `--vault` containment on write paths — is_relative_to assertion before any open()

## Review checklist

For each item, verify:
- The implementation matches the ARB spec exactly
- Error codes use the exact standardized strings (not_paired, rmapi_missing, chromium_missing, key_missing, doc_exists, note_not_found, path_containment, rate_limited, vision_failed, cli_error)
- Backward compatibility: default mode (no --json, no --emit, no --vault) is unchanged
- Security: no shell=True, no expandvars on argv paths, no symlink bypass, path containment enforced
- Tests: each AC has dedicated tests, tests actually test the behavior (not just that a function exists)

## Specific things to check

1. **--json envelope**: Does it output to stdout (not stderr)? Does the error envelope have data: null? Are all error codes tested?
2. **doctor --json**: Does it return the exact schema from the ARB? Does it check rmapi/chromium/vault/paired/key?
3. **pull --emit json**: Does it write NOTHING to disk? Does it return sections/doc_id/total_pages/annotated_pages?
4. **--on-exists**: Is fail the default? Does content-only preserve annotations? Is the --force comment corrected?
5. **--vault flag**: Does it take precedence over config? Is containment enforced?
6. **expandvars**: Does expand_user_path (or equivalent) NOT apply expandvars? Does a filename with $ stay unchanged? Does config still get expandvars?
7. **rmapi resolution**: Are all 4 steps tested? Does doctor report which one resolved?
8. **Mermaid**: Is securityLevel 'strict' (not 'loose')? Is htmlLabels false? Does the route interceptor block non-allowlisted requests?
9. **Config hardening**: Is O_NOFOLLOW used? Is fchmod called? Is S_ISREG/st_uid checked? In both set() and init_config()?
10. **set-key**: Does it read from stdin? Is the key never in argv? Does legacy config set print deprecation?
11. **Containment**: Does path traversal return path_containment with NO file opened?

## How to review

1. Read the diff: `git diff main...HEAD`
2. Read each modified file in full
3. Read the ARB spec: `cat docs/ARB-OBSIDIAN-PLUGIN.md | sed -n '376,500p'`
4. Run the tests: `python3 -m pytest -q`
5. Check for any regressions or missing tests

## Output

Post your findings as a structured report. For each finding:
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Item: which of the 11 items it affects
- Description: what the issue is
- Recommendation: how to fix it

If no findings, state "APPROVED — no findings" explicitly.

Do NOT modify any code. Do NOT commit or push. Just review and report.