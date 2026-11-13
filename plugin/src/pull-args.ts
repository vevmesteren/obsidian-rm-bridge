// Argv construction for `ormb pull --emit json` (Phase 5b).
//
// Extracted from the plugin's pullAnnotations method so the argv contract
// against the CLI's argparse schema can be unit-tested without instantiating
// the full Obsidian App. The CLI's pull parser (cli.py:_setup_pull_parser)
// requires a `page_name` positional (nargs="?") and errors out without it;
// the --emit json path calls retrieve_to_json(page_name, rm_folder=...).

/** Minimal file shape needed to build pull argv. */
export interface PullFile {
  /** Vault-relative path (unused by the emit-json path, kept for symmetry). */
  path: string;
  /** reMarkable page name = the note's basename (no extension). */
  basename: string;
}

/**
 * Build the argv for `ormb pull --emit json`.
 *
 * `page_name` (the file basename) is the FIRST positional, immediately after
 * "pull" — the CLI requires it (cli.py:110,311) and exits 2 without it.
 * `--rm-folder` forwards the user's reMarkable folder setting so pull reads
 * from the same folder publish writes to. `--md` is intentionally omitted:
 * retrieve_to_json never reads it on the emit-json path.
 */
export function buildPullArgs(
  file: PullFile,
  vaultRoot: string,
  rmFolder: string,
): string[] {
  return [
    "pull",
    file.basename,
    "--emit",
    "json",
    "--vault",
    vaultRoot,
    "--rm-folder",
    rmFolder,
    "--json",
  ];
}
