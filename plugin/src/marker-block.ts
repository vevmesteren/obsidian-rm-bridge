// Pure helpers for the pull-annotation marker block (Phase 5b).
//
// Extracted from the plugin class so they are unit-testable in node:test
// without instantiating the full Obsidian `App`. The plugin's pullAnnotations
// method composes these with vault.process for atomic, undo-able writes.
//
// Marker block format (ARB Phase 5b):
//   <!-- ormb:annotations doc="<id>" rev="<hash>" -->
//
// On re-pull the existing marker block AND everything after it (the
// transcribed annotation sections) is stripped, then the new marker +
// sections are appended — replace, not duplicate (ARB R4).

import type { OrmbPullData } from "./types.ts";

/** Build the marker comment that anchors a pulled-annotation block. */
export function buildMarkerBlock(data: OrmbPullData): string {
  // Sanitize doc_id and rev to prevent HTML comment injection —
  // reject `"` and `--` which could break the comment or inject
  // a premature `-->` close (grok suggestion).
  const safeDoc = data.doc_id.replace(/["]/g, "_").replace(/--/g, "__");
  const safeRev = data.rev.replace(/["]/g, "_").replace(/--/g, "__");
  return `<!-- ormb:annotations doc="${safeDoc}" rev="${safeRev}" -->`;
}

/**
 * Remove an existing marker block and everything after it (the annotation
 * sections). Content with no marker is returned unchanged.
 *
 * Annotations always live at the end of the note, so stripping from the
 * first marker to end-of-file is the correct replace semantic.
 */
export function stripExistingAnnotations(content: string): string {
  const idx = content.search(/<!-- ormb:annotations/);
  if (idx === -1) return content;
  return content.slice(0, idx).trimEnd();
}

/**
 * Compose the new note content: original (minus old annotations) + marker
 * block + transcribed sections. Pure — does not touch the vault. The plugin
 * applies the result via `vault.process` for atomic, undo-able writes.
 */
export function applyMarkerBlock(
  content: string,
  markerBlock: string,
  data: OrmbPullData,
): string {
  const cleaned = stripExistingAnnotations(content);
  // Format each section with a page header so pulled annotations are
  // readable in the note. The CLI's retrieve_to_json returns raw text
  // per page — we add the `## Page N` header here (grok C2).
  const sections = data.sections.map((s) =>
    `## Page ${s.page}\n\n${s.text}`,
  ).join("\n\n");
  return `${cleaned}\n${markerBlock}\n${sections}\n`;
}

/** Default vision model slug shown in the consent modal when settings is blank. */
export const DEFAULT_VISION_MODEL = "z-ai/glm-4.5v";

/**
 * Build the disclosure text for the first-run pull consent modal.
 * Pure so the wording is unit-testable independent of the Obsidian Modal API.
 */
export function buildConsentBody(fileBasename: string, visionModel: string): string {
  const model = visionModel.trim() || `${DEFAULT_VISION_MODEL} (CLI default)`;
  return (
    `This will transcribe handwritten annotations from the reMarkable document ` +
    `"${fileBasename}" using the vision model (OpenRouter). ` +
    `Page images are sent to OpenRouter for handwriting transcription. ` +
    `Model: ${model}.`
  );
}
