// Pure Windows → WSL path translation (T-WSL).
//
// Only the vault root is translated; note paths are passed vault-relative and
// already forward-slash separated (Obsidian `file.path`). This function is the
// single chokepoint for turning a Windows path into a WSL path, and it rejects
// anything that could be smuggled into a child-process argument maliciously.

/**
 * Translate a Windows drive-letter path to its WSL automount equivalent.
 *
 * - Rejects NUL / control characters (char code < 32).
 * - Rejects UNC paths (`\\server\share\...`).
 * - Rejects anything that is not a drive-letter path (`^[A-Za-z]:`).
 * - Lowercases the drive letter and replaces all `\` with `/`.
 *
 * @param windowsPath e.g. `C:\Users\val\Documents\note.md`
 * @param automountRoot e.g. `/mnt`
 * @returns e.g. `/mnt/c/Users/val/Documents/note.md`
 */
export function winToWsl(windowsPath: string, automountRoot: string): string {
  // 1. Reject control characters (NUL injection etc.).
  for (let i = 0; i < windowsPath.length; i++) {
    if (windowsPath.charCodeAt(i) < 32) {
      throw new Error(
        "Path contains control characters (char code < 32)",
      );
    }
  }

  // 2. Reject UNC paths — a vault on \\wsl$ is the unsupported T-MIXED topology.
  if (windowsPath.startsWith("\\\\")) {
    throw new Error("UNC paths are not supported (use a drive-letter vault)");
  }

  // 3. Require drive-letter form.
  const driveMatch = windowsPath.match(/^([A-Za-z]):[\\/](.*)$/);
  if (!driveMatch) {
    throw new Error(`Unsupported path format (drive letter required): ${windowsPath}`);
  }

  const drive = driveMatch[1].toLowerCase();
  const rest = driveMatch[2].replace(/\\/g, "/");

  // Trim a trailing automount-root slash so we never emit `//mnt/...`.
  const root = automountRoot.replace(/\/+$/, "");

  return `${root}/${drive}/${rest}`;
}
