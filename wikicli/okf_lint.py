#!/usr/bin/env python3
"""Lint an OKF v0.1 wiki bundle: frontmatter, type, links, index/log/manifest coverage.

Usage: python3 okf_lint.py <wiki-dir> [--json]

Exit codes: 0 clean, 1 findings (errors and/or warnings), 2 tool error.
Findings are split into errors (structural violations) and warnings
(recommended-but-missing fields, orphan pages). Both count toward exit 1;
only a script/argument/crash failure is exit 2.
"""
# decision: the spec's "0/1/2 (ok / findings / error)" does not say whether
# warnings alone are "findings". They are: any finding at all exits 1, and
# exit 2 is reserved strictly for tool failures (bad path, crash, no PyYAML).
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

# decision: root-level meta files carry no frontmatter/type schema and are
# excluded from the type/frontmatter/index-coverage checks. This mirrors the
# project-side file set in design doc section 4:
# docs/wiki/{BRAIN.md, project-profile.md, manifest.json, index.md, log.md, <pages>}.
RESERVED_ROOT_FILES = {"index.md", "log.md", "BRAIN.md", "project-profile.md"}

RECOMMENDED_FIELDS = ("title", "description", "timestamp")

# decision: a trailing #fragment (page.md#section) is tolerated and resolved
# against the page path; the original lint's regex rejected it.
LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")
# decision: log.md entries must sit under a '## YYYY-MM-DD' header and start
# with a bold action word from the set below (the format the reference wiki's
# log.md uses); the original lint did not check log.md content at all.
LOG_HEADER_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
LOG_ACTION_RE = re.compile(r"^\*\*(Creation|Update|Finding|Deprecation)\*\*")

# decision: manifest.json validation only runs if the file exists (hand-built
# bundles predate it), but when present it must carry every key of the fixed
# schema in BUILD-SPEC rule 8. Values are checked where derivable: page_count
# and page_types against the scanned bundle, status against its enum.
MANIFEST_REQUIRED_KEYS = (
    "okf", "profile", "created", "updated", "status",
    "batches_done", "batches_total", "page_count", "page_types",
    "compiled_from_sha", "plugin_version",
)
MANIFEST_STATUSES = {"compiling", "complete"}


def is_dot_path(rel: str) -> bool:
    # decision: dot-directories (.obsidian/, .compile/) are tooling/working
    # state per design section 4, not OKF pages; excluded from all scanning.
    return any(part.startswith(".") for part in Path(rel).parts)


def load_frontmatter(text: str):
    """Return (frontmatter_dict_or_None, error_str_or_None)."""
    if not text.startswith("---\n"):
        return None, "missing frontmatter"
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        return None, "malformed frontmatter delimiters"
    try:
        fm = yaml.safe_load(parts[1])
    except Exception as e:
        return None, f"frontmatter parse error: {e}"
    if not isinstance(fm, dict):
        return None, "frontmatter did not parse to a mapping"
    return fm, None


def resolve_link(page_path: Path, root: Path, target: str) -> Path:
    base = root if target.startswith("/") else page_path.parent
    return (base / target.lstrip("/")).resolve()


def lint(root: Path):
    errors = []
    warnings = []

    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")
    # Resolve so is_relative_to()/relative_to() work when the caller passes a
    # relative wiki-dir (link targets are resolved to absolute paths below).
    root = root.resolve()

    all_md = sorted(p for p in root.rglob("*.md"))
    # decision: raw/ is the committed inbox of immutable non-repo sources
    # (llm-wiki's raw layer). Its files are sources, not pages: no frontmatter
    # schema, no index listing, no link lint. Fully excluded from page
    # scanning; a separate pass below warns on unprocessed inbox items.
    all_md = [
        p for p in all_md
        if not is_dot_path(p.relative_to(root).as_posix())
        and not p.relative_to(root).as_posix().startswith("raw/")
    ]

    pages = []       # (rel, path) for content pages (non-reserved)
    reserved = {}     # rel -> path, for index.md/log.md/etc found at root
    for p in all_md:
        rel = p.relative_to(root).as_posix()
        if rel in RESERVED_ROOT_FILES:
            reserved[rel] = p
        else:
            pages.append((rel, p))

    page_rels = {rel for rel, _ in pages}
    fm_by_page = {}

    # --- frontmatter / type / recommended fields ---
    for rel, p in pages:
        text = p.read_text()
        fm, err = load_frontmatter(text)
        if err:
            errors.append(f"{rel}: {err}")
            continue
        fm_by_page[rel] = fm
        if not str(fm.get("type") or "").strip():
            errors.append(f"{rel}: empty/missing type")
        for k in RECOMMENDED_FIELDS:
            if not fm.get(k):
                warnings.append(f"{rel}: missing recommended field '{k}'")

    # --- link resolution + inbound-link tracking (all md files, including reserved) ---
    inbound = {rel: 0 for rel in page_rels}
    for p in all_md:
        rel = p.relative_to(root).as_posix()
        text = p.read_text()
        for target in LINK_RE.findall(text):
            if target.startswith("http://") or target.startswith("https://"):
                continue
            resolved = resolve_link(p, root, target)
            if not resolved.exists():
                errors.append(f"{rel}: broken link -> {target}")
                continue
            if resolved.is_relative_to(root):
                target_rel = resolved.relative_to(root).as_posix()
                if target_rel in inbound and target_rel != rel:
                    inbound[target_rel] += 1

    # --- orphan pages (warning) ---
    for rel in sorted(page_rels):
        if inbound.get(rel, 0) == 0:
            warnings.append(f"{rel}: orphan page (no inbound links)")

    # --- index.md coverage (exact: every page listed exactly once) ---
    # decision: duplicate listings are errors too, not just missing/extra;
    # "listed exactly once" is read literally.
    if "index.md" not in reserved:
        errors.append("index.md: missing")
    else:
        index_text = reserved["index.md"].read_text()
        listed = [t for t in LINK_RE.findall(index_text) if not t.startswith("http")]
        counts = {}
        for t in listed:
            resolved = resolve_link(reserved["index.md"], root, t)
            if not resolved.is_relative_to(root):
                # Outside the bundle: not a page listing. The broken-link pass
                # above already errors if the target does not exist.
                continue
            key = resolved.relative_to(root).as_posix()
            counts[key] = counts.get(key, 0) + 1

        for rel in sorted(page_rels):
            n = counts.get(rel, 0)
            if n == 0:
                errors.append(f"index.md: page not listed -> {rel}")
            elif n > 1:
                errors.append(f"index.md: page listed {n} times (expected exactly 1) -> {rel}")

        for key, n in counts.items():
            if key not in page_rels and key not in RESERVED_ROOT_FILES:
                errors.append(f"index.md: lists nonexistent page -> {key}")

    # --- log.md entries: '## YYYY-MM-DD' headers, bold action words ---
    if "log.md" not in reserved:
        errors.append("log.md: missing")
    else:
        log_lines = reserved["log.md"].read_text().splitlines()
        current_date = None
        entries_under_date = 0
        for i, line in enumerate(log_lines, start=1):
            header_match = LOG_HEADER_RE.match(line)
            if header_match:
                if current_date is not None and entries_under_date == 0:
                    errors.append(f"log.md: date section '{current_date}' has no entries")
                current_date = header_match.group(1)
                entries_under_date = 0
                continue
            if line.startswith("**"):
                if current_date is None:
                    errors.append(f"log.md:{i}: bold entry outside any '## YYYY-MM-DD' section")
                    continue
                if LOG_ACTION_RE.match(line):
                    entries_under_date += 1
                else:
                    errors.append(
                        f"log.md:{i}: entry does not start with a recognized bold action "
                        f"word (Creation/Update/Finding/Deprecation): {line[:60]!r}"
                    )
        if current_date is not None and entries_under_date == 0:
            errors.append(f"log.md: date section '{current_date}' has no entries")
        if current_date is None and log_lines:
            # log.md exists with content but no dated section at all
            has_any_heading = any(l.strip().startswith("#") for l in log_lines)
            if has_any_heading:
                warnings.append("log.md: no '## YYYY-MM-DD' section found")

    # --- raw/ inbox: warn on unprocessed items ---
    # raw/<file> is pending; raw/processed/<file> has been distilled into
    # pages by /brain ingest. Any filetype counts (sources are not limited to
    # markdown); dotfiles (.gitkeep) are ignored.
    raw_dir = root / "raw"
    if raw_dir.is_dir():
        for p in sorted(raw_dir.rglob("*")):
            if not p.is_file() or p.name.startswith("."):
                continue
            rel = p.relative_to(root).as_posix()
            inner = p.relative_to(raw_dir).as_posix()
            if not inner.startswith("processed/"):
                warnings.append(
                    f"{rel}: unprocessed inbox item (run /brain ingest to distill it)"
                )

    # --- manifest.json (optional) ---
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception as e:
            errors.append(f"manifest.json: parse error: {e}")
            manifest = None
        if manifest is not None and not isinstance(manifest, dict):
            errors.append("manifest.json: top level is not an object")
            manifest = None
        if manifest is not None:
            for key in MANIFEST_REQUIRED_KEYS:
                if key not in manifest:
                    errors.append(f"manifest.json: missing required key '{key}'")
            status = manifest.get("status")
            if "status" in manifest and status not in MANIFEST_STATUSES:
                errors.append(
                    f"manifest.json: status={status!r}, expected one of "
                    f"{sorted(MANIFEST_STATUSES)}"
                )
            okf_version = manifest.get("okf")
            if "okf" in manifest and okf_version != "0.1":
                warnings.append(
                    f"manifest.json: okf={okf_version!r}, this linter targets '0.1'"
                )

            actual_count = len(page_rels)
            claimed_count = manifest.get("page_count")
            if "page_count" in manifest and claimed_count != actual_count:
                errors.append(
                    f"manifest.json: page_count={claimed_count!r}, actual={actual_count}"
                )

            actual_types = {}
            for rel, fm in fm_by_page.items():
                t = str(fm.get("type") or "").strip()
                if t:
                    actual_types[t] = actual_types.get(t, 0) + 1
            claimed_types = manifest.get("page_types") or {}
            if "page_types" in manifest and claimed_types != actual_types:
                errors.append(
                    f"manifest.json: page_types mismatch. "
                    f"manifest={claimed_types!r} actual={actual_types!r}"
                )

    return {
        "root": str(root),
        "page_count": len(page_rels),
        "file_count": len(all_md),
        "errors": errors,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description="Lint an OKF v0.1 wiki bundle.")
    parser.add_argument("wiki_dir", help="path to the wiki bundle (e.g. docs/wiki)")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    root = Path(args.wiki_dir)
    try:
        result = lint(root)
    except FileNotFoundError as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": f"unexpected failure: {e}"}))
        else:
            print(f"error: unexpected failure: {e}", file=sys.stderr)
        sys.exit(2)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['page_count']} concept pages, {result['file_count']} files total")
        if result["errors"]:
            print(f"\n{len(result['errors'])} error(s):")
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        if result["warnings"]:
            print(f"\n{len(result['warnings'])} warning(s):")
            for w in result["warnings"]:
                print(f"  WARN: {w}")
        if not result["errors"] and not result["warnings"]:
            print("OK: bundle conforms")

    sys.exit(1 if (result["errors"] or result["warnings"]) else 0)


if __name__ == "__main__":
    main()
