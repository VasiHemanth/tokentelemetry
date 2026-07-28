/* Filesystem-path helpers.
 *
 * Project paths come from whatever machine the agent ran on, so they are
 * POSIX ("/Users/dev/code/app") on macOS and Linux and Windows
 * ("C:\\Users\\dev\\Documents\\app") on Windows. Splitting on "/" alone returns
 * the ENTIRE Windows path instead of its last segment, which is why a Windows
 * project rendered its full path where a name belonged.
 */

/** Last segment of a filesystem path, on either separator.
 *  Trailing separators are ignored so "C:\\a\\b\\" still yields "b". */
export function projectBasename(path: string | null | undefined): string {
  if (!path) return "";
  const parts = String(path).split(/[\\/]+/).filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}
