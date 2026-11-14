# Community Store Submission

Checklist and process for submitting the **Obsidian reMarkable Bridge** plugin
to the [Obsidian community plugin store](https://obsidian.md/plugins).

This document is for the **operator** (repo maintainer). The worker does not
submit the PR — that is an explicit human action.

## Submission checklist

### manifest.json — required fields

Verified against `plugin/manifest.json`:

- [x] `id`: `"obsidian-rm-bridge"` (unique, lowercase, kebab-case, matches
  the plugin folder name and the `community-plugins.json` entry)
- [x] `name`: `"Obsidian reMarkable Bridge"` (human-readable)
- [x] `version`: `"0.1.0"` (matches `plugin/versions.json` key)
- [x] `minAppVersion`: `"1.5.0"` (matches `plugin/versions.json` value)
- [x] `author`: `"vevmesteren"` (GitHub username, matches repo owner)
- [x] `description`: present
- [x] `isDesktopOnly`: `true` — confirmed. The plugin spawns a local CLI
  (`ormb`) via `child_process`, which is a desktop-only capability. The
  `plugin-ci.yml` workflow enforces this with a runtime check.
- [x] No `authorUrl` / `community` fields required for initial submission.

### versions.json — valid

`plugin/versions.json` is valid JSON and maps the released plugin version to
its minimum Obsidian app version:

```json
{
  "0.1.0": "1.5.0"
}
```

The `version` in `manifest.json` (`0.1.0`) has a matching key here.

### No default hotkeys

The plugin registers **no hotkeys**. Verified by inspecting
`plugin/src/main.ts`: the plugin adds commands via
`this.addCommand(...)`, none of which include a `hotkeys` assignment, and the
plugin adds no `app.hotkeyManager` calls. Obsidian only assigns default
hotkeys when the manifest or code declares them; users can bind their own.

### Disclosures present in README

The root `README.md` includes a **Security & Data Egress Disclosures**
section covering:

- reMarkable Cloud egress (publish + pull via rmapi)
- OpenRouter egress (pull only, vision transcription, first-run consent)
- External binary execution (plugin → `ormb` → Chromium + rmapi)
- HTML sanitisation (bleach, default on)
- Local pull cache (transcribed text only, no images)

### Screenshot placeholders in README

`README.md` references two screenshots:

- `docs/screenshots/publish.png` — Publish command
- `docs/screenshots/pull.png` — Pull command

> **Operator action:** capture these during the E2E test pass and commit the
> PNGs before the community-store PR. The placeholders render as broken
> images until then, which is expected at this stage.

### Banned patterns enforced by CI

`plugin-ci.yml` runs a grep that fails the build if any of these patterns
appear in `plugin/src/`:

- `exec(`, `execSync(`
- `shell: true`
- `bash -c`
- `cmd.exe /c`

This enforces that the plugin never invokes a shell when spawning `ormb`,
preventing argument-injection from note filenames.

## Release artifacts

For the initial submission, Obsidian requires three files in the GitHub
release attached to the submission tag:

1. `main.js` — the bundled plugin (produced by `npm run build`)
2. `manifest.json` — copied from `plugin/manifest.json`
3. `styles.css` — empty or minimal (the plugin currently ships no custom CSS;
   create an empty file so Obsidian doesn't 404)

To build and package:

```bash
cd plugin
npm ci
npm run build
# main.js is produced in plugin/
cp manifest.json ../release/
cp main.js ../release/
touch ../release/styles.css
```

Generate a checksums file for the release artifacts:

```bash
cd release
../scripts/release_checksums.sh .
# produces SHA256SUMS alongside the artifacts
```

## Submission process (operator action — DO NOT automate)

1. **Final E2E pass** — run the [T-WSL test playbook](T-WSL-TEST-PLAYBOOK.md)
   on a clean Windows + WSL2 machine. Capture the two screenshots
   (`docs/screenshots/publish.png`, `docs/screenshots/pull.png`) and commit
   them.
2. **Tag a release** — `git tag -a v0.1.0 -m "v0.1.0"` and
   `git push origin v0.1.0`. The release workflow (if configured) builds
   `main.js`; otherwise build manually and attach `main.js`,
   `manifest.json`, and `styles.css` to the GitHub release.
3. **Verify the release** — download the three files into a fresh vault's
   `plugins/obsidian-rm-bridge/` folder and confirm the plugin loads.
4. **Open the PR** — fork
   [`obsidianmd/obsidian-releases`](https://github.com/obsidianmd/obsidian-releases),
   add one line to `community-plugins.json`:

   ```json
   {
     "id": "obsidian-rm-bridge",
     "name": "Obsidian reMarkable Bridge",
     "author": "vevmesteren",
     "description": "Publish notes to reMarkable and pull back handwritten annotations",
     "repo": "vevmesteren/obsidian-rm-bridge"
   }
   ```

   Open the PR with the title `New plugin submission: obsidian-rm-bridge`.
5. **Respond to review** — the Obsidian team reviews for the manifest
   fields, the banned-pattern check, and the disclosure README. Keep this
   document and the README disclosures in sync with any review feedback.

> The worker stops at this document. The PR to `obsidianmd/obsidian-releases`
> is an explicit operator action and is **not** automated.
