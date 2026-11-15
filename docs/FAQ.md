# FAQ

> **Audience:** All users

← Back to [README](../README.md)

## General

### What does obsidian-rm-bridge do?

It publishes your Obsidian markdown notes to your reMarkable tablet as PDFs,
lets you annotate by hand on the reMarkable, then pulls the handwritten
annotations back into your Obsidian vault as structured text appended to the
source note. It's the only tool that does the full round-trip.

### Do I need an OpenRouter account?

Only for pulling annotations. Publishing (markdown → PDF → reMarkable) works
without any API key. Pulling (reMarkable → text) uses a vision LLM via
OpenRouter to transcribe handwriting, so you need an OpenRouter account and
API key for that step.

### How much does pulling cost?

Each annotated page is sent as a PNG image to the vision model. With GLM-4.5V
(the default), costs are typically a fraction of a cent per page. You can
check the page count before pulling with `ormb pull <page> --info --json`
(which doesn't call the vision API). Results are cached by PDF content hash,
so re-pulling an unchanged document doesn't re-pay.

### Can I use a different vision model?

Yes. Set it in config:
```bash
ormb config set vision.model openai/gpt-4o
```
Any vision-capable model available on OpenRouter works.

### Can I use a local model instead of OpenRouter?

Not yet. The vision client uses OpenRouter's API. Local model support (e.g.
Ollama with a vision model) is a potential future feature.

## Publishing

### What happens to mermaid diagrams?

Mermaid diagrams in your markdown are rendered to SVG by Playwright (the same
browser engine used for PDF rendering), so they appear correctly in the PDF
on your reMarkable.

### Can I publish a folder of notes?

Yes:
```bash
ormb publish my-project/ --folder
```
All `.md` files in the folder are combined into a single PDF.

### What if I re-publish a page I already annotated?

Use `--on-exists content-only` to replace the page only if the content has
changed. If the content is the same (annotations didn't change the source),
the page is preserved. Annotation sections and marker blocks are
automatically stripped from the published PDF so they don't clutter your
reMarkable.

## Pulling

### What format do annotations appear in?

```markdown
## [2026-11-13] Annotations

- handwritten annotation text
- another annotation
```

A single date-titled section with one bullet per annotation, appended after
a marker block in your note.

### What is the consent modal?

The first time you pull annotations for a page, the plugin shows a modal with
the page count and the model that will be used. You must click "Consent &
Pull" to proceed. This ensures you know the cost before any images are sent
to OpenRouter.

### Can I pull annotations from the CLI without the plugin?

Yes. The CLI is fully standalone:
```bash
ormb pull my-page-name
```
The consent step in the CLI is simply running the command explicitly — there's
no modal, you're in control.

### What gets cached?

Vision transcription results are cached by PDF content hash + model at
`~/.obsidian-rm-bridge/pull_cache.json`. The cache contains only transcribed
text, never images. If the PDF hasn't changed (no new annotations), re-pulling
hits the cache and skips the vision call entirely.

## Security

### What data leaves my machine?

See the [Security & Data Egress Disclosures](../README.md#security--data-egress-disclosures)
section in the README. Short version:
- **Publish:** PDF → reMarkable Cloud (via rmapi)
- **Pull:** annotated PDF ← reMarkable Cloud, page images → OpenRouter

### Is my API key stored securely?

The key is stored in `~/.obsidian-rm-bridge/config.toml` with `0600`
permissions (readable only by your user). It's never passed as a command-line
argument. The plugin does not handle the key at all — you set it via the CLI.

← Back to [README](../README.md)
