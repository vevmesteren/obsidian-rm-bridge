# T-WSL Operator Test Playbook

> **Topology:** T-WSL — Obsidian on Windows, `ormb` CLI in WSL2 Ubuntu
> **Tester:** Valentin
> **Prerequisites:** reMarkable paired, `ormb` CLI installed in WSL, OpenRouter API key configured

---

## 0. Pre-flight (WSL terminal)

```bash
# Activate the venv first — ormb lives there
source .venv/bin/activate

# Verify CLI is alive and healthy
ormb doctor --json

# Expected: ok=true, version="0.1.0", rmapi.found=true, paired=true, key_present=true
# If key_present=false: ormb config set openrouter_api_key sk-...
# If paired=false: ormb pair  (one-time, needs a code from my.remarkable.com/device)
# If vault not reachable: ormb config set vault.path /mnt/c/dev/veviki
```

**Pass criteria:** doctor reports `ok=true`, `paired=true`, `key_present=true`, `vault: "reachable"`.

**Blocker:** If `paired=false`, stop here and run `ormb pair` before proceeding. Most test cases require a paired reMarkable.

---

## 0.5. Pair reMarkable (if not already paired)

If `ormb doctor --json` shows `paired: false`:

1. Go to [my.remarkable.com/device](https://my.remarkable.com/device) on your phone or browser
2. Get a one-time pairing code
3. In WSL terminal (venv active):
   ```bash
   ormb pair
   ```
4. Enter the code when prompted
5. Re-run `ormb doctor --json` — verify `paired: true`

**Pass criteria:** `paired: true` in doctor output.

---

## 1. Plugin install (Windows)

1. Open WSL terminal at the repo:
   ```bash
   cd /home/hermes/obsidian-rm-bridge/plugin
   npm install && npm run build
   ```
   Verify `main.js` is produced (no errors in esbuild output).

2. Copy plugin files to your Obsidian vault's plugins folder:
   ```powershell
   # In Windows PowerShell — adjust $vault to your vault path
   $vault = "C:\dev\veviki"
   $dest = "$vault\.obsidian\plugins\obsidian-rm-bridge"
   New-Item -ItemType Directory -Force -Path $dest
   Copy-Item "C:\dev\obsidian-rm-bridge\plugin\main.js" $dest
   Copy-Item "C:\dev\obsidian-rm-bridge\plugin\manifest.json" $dest
   ```
   If `styles.css` exists, copy it too.

   > **Note:** The repo lives on the Windows filesystem (`C:\dev\obsidian-rm-bridge\`), not in WSL home. Build from WSL via `/mnt/c/dev/obsidian-rm-bridge/plugin/`, but copy the built `main.js` from the Windows path.

3. In Obsidian: Settings → Community plugins → reload list → enable "Obsidian reMarkable Bridge"

**Pass criteria:** Plugin appears in the community plugins list and enables without errors.

---

## 2. Plugin settings (Obsidian)

1. Settings → "Obsidian reMarkable Bridge" tab
2. Verify defaults match your environment:

   | Field | Expected value |
   |-------|---------------|
   | Launcher | `python -m obsidian_rm_bridge` |
   | WSL distro | `Ubuntu` (or your distro name) |
   | Python bin | `/home/u/.venvs/ormb/bin/python` (adjust to your venv) |
   | rm folder | `/Obsidian` (or your reMarkable folder) |
   | Vision model | `z-ai/glm-4.5v` (or your model) |
   | Automount root | `/mnt` |

3. Click "Test connection" — should show doctor result inline
   - **Pass:** Shows `ok: true`, version, rmapi found, paired
   - **Fail:** If "wsl.exe not found" — check `SystemRoot` env, check WSL is running

4. Check the copyable commands section:
   - "Pair reMarkable" → `ormb pair`
   - "Set OpenRouter API key (stdin)" → `ormb config set-key`

**Pass criteria:** Test connection shows healthy doctor. Copyable commands visible.

---

## 3. Happy path — Publish

1. Open a markdown note in Obsidian (e.g. `Test Note.md`)
2. Open command palette (Ctrl+P) → search "Publish to reMarkable"
   - **Also test:** Right-click the file in the file explorer → "Publish to reMarkable"
   - **Also test:** Click the ribbon icon (if present) with the note open
3. Observe the Notice toast: should say "Published ✓ <page name>"
4. Check your reMarkable tablet → the document should appear in the configured folder

**Pass criteria:** Notice shows success. Document appears on reMarkable within sync time.

---

## 4. Happy path — Pull (first run, with consent)

1. On the reMarkable: open the published document, annotate with the pen
2. Let the reMarkable sync (wait for sync icon to settle)
3. Back in Obsidian: open the same note
4. Command palette → "Pull annotations from reMarkable"
   - **Also test:** Right-click file in explorer → "Pull annotations from reMarkable"
5. **Consent modal appears** (first run only):
   - Modal title: "Pull annotations from reMarkable"
   - Body mentions the file name, vision model, and OpenRouter data egress
   - Buttons: "Pull annotations" (cta) / "Cancel"
   - Click "Pull annotations"
6. Observe the Notice: should say "Pulled N annotation(s) ✓"
7. Check the note content:
   - Marker block present: `<!-- ormb:annotations doc="..." rev="..." -->`
   - Sections formatted as `## Page N` with transcribed text
   - No duplication of existing content

**Pass criteria:** Consent modal shown. Annotations appear in note with page headers. Marker block present.

---

## 5. Happy path — Pull again (idempotent)

1. Without changing annotations on reMarkable, run "Pull annotations from reMarkable" again on the same note
2. No consent modal (already given)
3. Notice: "Pulled N annotation(s) ✓" (same count)
4. Check the note: **marker block replaced, not duplicated**
   - Only one `<!-- ormb:annotations ... -->` block
   - Same content (rev hash should be the same since content hasn't changed)

**Pass criteria:** No duplicate marker blocks or annotations. Idempotent re-pull works.

---

## 6. Happy path — Republish content-only

1. In WSL terminal, republish the same note with content-only:
   ```bash
   ormb publish "Test Note.md" --on-exists content-only --vault /mnt/c/dev/veviki
   ```
2. On reMarkable: annotate again (different marks)
3. Sync
4. Pull again from the plugin
5. Verify: new annotations replace old ones (not appended), marker block updated

**Pass criteria:** Republish + re-pull replaces annotations cleanly.

---

## 7. Unhappy path — Publish already exists (doc_exists)

1. Try to publish the same note again from the plugin (without content-only)
2. Expected: Notice shows a tip:
   > "Document already on reMarkable. Use 'ormb publish --on-exists content-only' in terminal to update."

**Pass criteria:** Shows the doc_exists tip, not a generic error. No document overwritten.

---

## 8. Unhappy path — Cancel consent modal

1. In settings, revoke pull consent (toggle "Pull annotation consent" off)
2. Run "Pull annotations from reMarkable" on a note
3. Consent modal appears → click "Cancel" (or press Escape)
4. Verify: no pull happens, no annotations written, no spinner

**Pass criteria:** Cancel/Escape dismisses modal without hanging. No vault write.

---

## 9. Unhappy path — Pull with no annotations

1. Publish a note to reMarkable (do NOT annotate it)
2. Run "Pull annotations from reMarkable"
3. Expected: Notice "No annotations found — existing annotations preserved."
4. Verify: existing note content is **not wiped** — prior annotations (if any) preserved

**Pass criteria:** Empty pull doesn't destroy existing annotations.

---

## 10. Unhappy path — Concurrent publish/pull (single-flight)

1. Open a note
2. Trigger "Publish to reMarkable"
3. While it's still running, trigger it again (or trigger "Pull")
4. Expected: Notice "Publish to reMarkable already in progress — please wait." (or "Pull already in progress")
5. Verify: no double spawn, no race condition

**Pass criteria:** Second operation is rejected, not queued or double-spawned.

---

## 11. Unhappy path — No OpenRouter API key

1. In WSL: `ormb config set openrouter_api_key ""`
2. Try to pull from the plugin
3. Expected: error Notice with a meaningful message (not a crash)
4. Restore: `ormb config set openrouter_api_key sk-...`

**Pass criteria:** Graceful error, no crash, no unhandled promise rejection.

---

## 12. Unhappy path — rmapi not paired

1. (If you can unpair without breaking things) — or just verify the doctor output:
   `ormb doctor --json` shows `paired=false`
2. The plugin "Test connection" should show this in settings
3. Publish should show a doctor warning Notice before attempting

**Pass criteria:** Doctor warnings are surfaced. No silent failure.

---

## 13. Marker block strip on republish

1. After pulling annotations (marker block present in note), republish with content-only
2. Check the PDF on reMarkable: the `<!-- ormb:annotations -->` block and `## Page N` sections should **NOT** appear in the PDF
3. They're stripped by `strip_marker_blocks()` in the CLI before rendering

**Pass criteria:** Marker blocks don't round-trip as content in the published PDF.

---

## 14. Undo after pull

1. Pull annotations into a note
2. Press Ctrl+Z (Undo) in Obsidian
3. Verify: the pull is reversible — note returns to pre-pull state

**Pass criteria:** `vault.process` preserves undo history. Pull is undoable.

---

## Results log

| # | Test | Pass/Fail | Notes |
|---|------|-----------|-------|
| 0 | Pre-flight | | |
| 0.5 | Pair reMarkable | | |
| 1 | Plugin install | | |
| 2 | Plugin settings | | |
| 3 | Happy publish | | |
| 4 | Happy pull + consent | | |
| 5 | Pull idempotent | | |
| 6 | Republish content-only | | |
| 7 | doc_exists | | |
| 8 | Cancel consent | | |
| 9 | Empty pull | | |
| 10 | Concurrent single-flight | | |
| 11 | No API key | | |
| 12 | rmapi not paired | | |
| 13 | Marker strip | | |
| 14 | Undo after pull | | |

---

> Fill in the results table, file any bugs as GitHub issues, and post the results as a comment on the epic issue.