#!/usr/bin/env python3
"""Write/update docs/wiki/manifest.json for an OKF v0.1 wiki bundle.

Usage:
    python3 wiki_manifest.py <wiki-dir> init   --profile P [--status S] [--plugin-version V]
                                                [--sha SHA|auto] [--date D] [--json]
    python3 wiki_manifest.py <wiki-dir> update [--status S] [--batches-done N] [--batches-total N]
                                                [--sha SHA|auto] [--date D] [--json]
    python3 wiki_manifest.py <wiki-dir> stamp  [--date D] [--json]

`stamp` writes content-hash provenance for every page into the manifest
(the freshness ground truth docs/wiki/status.py checks) and installs or
refreshes status.py in the wiki dir. Hashes are of file CONTENT, so they
survive squash-merges, rebases, worktrees, and tarballs where commit shas
do not. Per page it records:
  - resources: frontmatter `resource:` plus repo paths cited in the body
    as code spans (playbooks cite the scripts they orchestrate without
    declaring resource:; body-cited paths close that blind spot),
    each mapped to a sha256-12 of the file bytes (dirs: capped tree hash).
  - page_sha: sha256-12 of the page file itself, so hand edits are
    detectable as tampering.
Run stamp after every compile/ingest that touches pages.

Stdlib only. Exit codes: 0 ok, 1 findings (not used by this script), 2 error.
"""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "0.1"
DEFAULT_PLUGIN_VERSION = "0.1.0"
DEFAULT_STATUS_INIT = "compiling"
# "project" is the sentinel for a census-derived schema (brain-init derives
# the page-type table from the project census instead of a shipped profile;
# the derivation record lives in project-profile.md, the contract in BRAIN.md).
VALID_PROFILES = {"fullstack-app", "research-data", "generic", "project"}
VALID_STATUSES = {"compiling", "complete"}

# Files at the wiki root that are bundle scaffolding, not concept pages.
# Mirrors okf_lint.py's index.md/log.md exclusion, plus the plugin-added
# BRAIN.md / project-profile.md (design doc section 4: project-side state).
NON_PAGE_NAMES = {"index.md", "log.md", "BRAIN.md", "project-profile.md"}

FRONTMATTER_DELIM = "---"
TYPE_LINE_RE = re.compile(r'^type:\s*["\']?([^"\'\n]+?)["\']?\s*$', re.MULTILINE)


def today(date_arg):
    if date_arg:
        try:
            datetime.date.fromisoformat(date_arg)
        except ValueError:
            die(f"--date must be YYYY-MM-DD, got {date_arg!r}")
        return date_arg
    return datetime.date.today().isoformat()


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def manifest_path(wiki_dir):
    return wiki_dir / "manifest.json"


def extract_type(text):
    """Minimal frontmatter parse: find the 'type:' line inside the leading
    ---/--- block. No PyYAML dependency (BUILD-SPEC rule 2 reserves PyYAML
    for okf_lint.py only)."""
    if not text.startswith(FRONTMATTER_DELIM + "\n"):
        return None
    body = text[len(FRONTMATTER_DELIM) + 1:]
    end = body.find("\n" + FRONTMATTER_DELIM)
    if end == -1:
        return None
    block = body[:end]
    m = TYPE_LINE_RE.search(block)
    if not m:
        return None
    return m.group(1).strip()


def scan_pages(wiki_dir):
    """Return (page_count, page_types dict) by walking *.md files, excluding
    scaffolding files and anything under a dot-directory (covers the .compile/
    working-state tree and editor dirs like .obsidian/). Must stay in lockstep
    with okf_lint.py's page set: lint cross-checks page_count/page_types
    against its own scan and errors on any mismatch."""
    page_types = {}
    count = 0
    for p in sorted(wiki_dir.rglob("*.md")):
        rel = p.relative_to(wiki_dir)
        if rel.name in NON_PAGE_NAMES and len(rel.parts) == 1:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        page_type = extract_type(text)
        count += 1
        if page_type:
            page_types[page_type] = page_types.get(page_type, 0) + 1
    return count, page_types


def resolve_sha(wiki_dir, sha_arg):
    """--sha auto: git rev-parse HEAD of the repo containing wiki_dir.
    Any other value (including a literal sha, or omitted) passes through."""
    if sha_arg != "auto":
        return sha_arg
    try:
        toplevel = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=wiki_dir, capture_output=True, text=True, check=True,
        ).stdout.strip()
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=toplevel, capture_output=True, text=True, check=True,
        ).stdout.strip()
        return sha
    except (subprocess.CalledProcessError, OSError) as e:
        die(f"--sha auto requested but git rev-parse failed: {e}")


def cmd_init(args, wiki_dir):
    if args.profile not in VALID_PROFILES:
        die(f"--profile must be one of {sorted(VALID_PROFILES)}, got {args.profile!r}")
    status = args.status or DEFAULT_STATUS_INIT
    if status not in VALID_STATUSES:
        die(f"--status must be one of {sorted(VALID_STATUSES)}, got {status!r}")
    mpath = manifest_path(wiki_dir)
    # decision: init refuses to clobber an existing manifest.json (no --force
    # escape hatch requested by spec); re-running init on an already-compiled
    # wiki is almost certainly a mistake. Use `update` to change an existing
    # manifest.
    if mpath.exists():
        die(f"{mpath} already exists; use 'update' to modify it")
    date = today(args.date)
    page_count, page_types = scan_pages(wiki_dir)
    manifest = {
        "okf": SCHEMA_VERSION,
        "profile": args.profile,
        "created": date,
        "updated": date,
        "status": status,
        "batches_done": 0,
        "batches_total": 0,
        "page_count": page_count,
        "page_types": page_types,
        "compiled_from_sha": resolve_sha(wiki_dir, args.sha) if args.sha else None,
        "plugin_version": args.plugin_version,
    }
    write_manifest(mpath, manifest)
    return manifest


def cmd_update(args, wiki_dir):
    mpath = manifest_path(wiki_dir)
    if not mpath.exists():
        die(f"{mpath} not found; run 'init' first")
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        die(f"could not read/parse {mpath}: {e}")

    page_count, page_types = scan_pages(wiki_dir)
    manifest["page_count"] = page_count
    manifest["page_types"] = page_types
    manifest["updated"] = today(args.date)

    if args.profile is not None:
        # re-scaffolds may move a wiki from a shipped profile to the
        # census-derived "project" schema (or to a profile) without
        # losing created/batch history the way delete+init would.
        manifest["profile"] = args.profile
    if args.status is not None:
        if args.status not in VALID_STATUSES:
            die(f"--status must be one of {sorted(VALID_STATUSES)}, got {args.status!r}")
        manifest["status"] = args.status
    if args.batches_done is not None:
        manifest["batches_done"] = args.batches_done
    if args.batches_total is not None:
        manifest["batches_total"] = args.batches_total
    if args.sha is not None:
        manifest["compiled_from_sha"] = resolve_sha(wiki_dir, args.sha)

    write_manifest(mpath, manifest)
    return manifest


def write_manifest(mpath, manifest):
    mpath.write_text(json.dumps(manifest, indent=2, sort_keys=False) + "\n", encoding="utf-8")


# --- stamp: content-hash provenance ---------------------------------------

RESOURCE_LINE_RE = re.compile(r'^resource:\s*["\']?([^"\'\n]+?)["\']?\s*$', re.MULTILINE)
SENTINELS = {"missing", "unhashable"}
# Repo paths cited in a page body as `code spans`: must contain a slash or a
# file extension, no spaces/newlines, not a URL. Existence in the repo is the
# final filter, so prose that merely looks path-ish drops out.
BODY_PATH_RE = re.compile(r"`([A-Za-z0-9_./-]+(?:/[A-Za-z0-9_.-]+|\.[A-Za-z0-9]{1,8}))`")
DIR_HASH_FILE_CAP = 200     # dirs with more files than this are "unhashable"
BODY_RESOURCE_CAP = 12      # max body-cited paths recorded per page


def sha12(data):
    return hashlib.sha256(data).hexdigest()[:12]


def repo_root_for(wiki_dir):
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=wiki_dir, capture_output=True, text=True, check=True,
        ).stdout.strip()
        if top:
            return Path(top)
    except (subprocess.CalledProcessError, OSError):
        pass
    # docs/wiki -> repo root two levels up; best effort outside git
    return wiki_dir.parent.parent


def hash_resource(root, rel):
    """Hash one resource path. Files: sha256-12 of bytes. Dirs: sha256-12 of
    the sorted (relpath, file-sha) list, capped — a moved/added/removed file
    changes the hash. Returns 'missing' or 'unhashable' sentinels."""
    p = (root / rel.lstrip("/")).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return "unhashable"  # escapes the repo; never follow
    if p.is_file():
        try:
            return sha12(p.read_bytes())
        except OSError:
            return "unhashable"
    if p.is_dir():
        files = sorted(f for f in p.rglob("*") if f.is_file()
                       and not any(part.startswith(".") for part in f.relative_to(p).parts))
        if len(files) > DIR_HASH_FILE_CAP:
            return "unhashable"
        h = hashlib.sha256()
        for f in files:
            try:
                h.update(str(f.relative_to(p)).encode())
                h.update(sha12(f.read_bytes()).encode())
            except OSError:
                return "unhashable"
        return h.hexdigest()[:12]
    return "missing"


def page_resources(root, text, wiki_rel):
    """Resource paths for one page: frontmatter resource: (if repo-local)
    plus body-cited repo paths that actually exist. Paths inside the wiki
    itself are excluded — the wiki referencing the wiki is self-provenance
    (stamp's own manifest write would flip such pages stale forever).
    Returns ordered unique relpath list."""
    def wiki_internal(rel):
        return rel == wiki_rel or rel.startswith(wiki_rel + "/")

    def in_repo(rel):
        # resolve() so a body-cited ../x can never smuggle an outside path
        # into the provenance record (it would only ever hash to a sentinel,
        # but recording it at all invites vacuous-freshness bugs)
        try:
            p = (root / rel).resolve()
            p.relative_to(root.resolve())
            return p.exists()
        except (ValueError, OSError):
            return False

    out = []
    # frontmatter block only: a body line starting "resource: x" is prose,
    # not metadata
    fm = ""
    if text.startswith(FRONTMATTER_DELIM + "\n"):
        end = text.find("\n" + FRONTMATTER_DELIM, len(FRONTMATTER_DELIM))
        if end != -1:
            fm = text[:end]
    m = RESOURCE_LINE_RE.search(fm)
    if m:
        r = m.group(1).strip().lstrip("/")
        if r and "://" not in r and not wiki_internal(r):
            out.append(r)
    body_hits = 0
    for cand in BODY_PATH_RE.findall(text):
        if body_hits >= BODY_RESOURCE_CAP:
            break
        cand = cand.strip().lstrip("/")
        if not cand or "://" in cand or cand in out or wiki_internal(cand):
            continue
        if in_repo(cand):
            out.append(cand)
            body_hits += 1
    return out


def cmd_stamp(args, wiki_dir):
    mpath = manifest_path(wiki_dir)
    if not mpath.exists():
        die(f"{mpath} not found; run 'init' first")
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        die(f"could not read/parse {mpath}: {e}")

    root = repo_root_for(wiki_dir)
    old_prov = manifest.get("provenance") or {}
    try:
        wiki_rel = str(wiki_dir.resolve().relative_to(root.resolve()))
    except ValueError:
        wiki_rel = wiki_dir.name

    provenance = {}
    drifted = []
    for p in sorted(wiki_dir.rglob("*.md")):
        rel = p.relative_to(wiki_dir)
        if rel.name in NON_PAGE_NAMES and len(rel.parts) == 1:
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue
        # raw/ is the immutable inbox, not compiled pages; never stamp it
        if rel.parts[0] == "raw":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        page_id = str(rel)[:-3]
        resources = {r: hash_resource(root, r) for r in page_resources(root, text, wiki_rel)}
        # a page whose sources moved since the LAST stamp is being
        # re-baselined right now; if its body wasn't refreshed first, this
        # stamp would launder staleness into a forged FRESH
        old = old_prov.get(page_id)
        if old and any(old["resources"].get(r) not in (None, h)
                       for r, h in resources.items()):
            drifted.append(page_id)
        provenance[page_id] = {
            "resources": resources,
            "page_sha": sha12(p.read_bytes()),
        }

    manifest["provenance"] = provenance
    manifest["provenance_stamped"] = today(args.date)
    # repo-wide file-set fingerprint: lets status.py warn when new source
    # files appear that NO page cites (the fact-moved-to-a-new-file blind
    # spot cannot be caught per page, but it can be flagged per repo)
    manifest["source_tree"] = source_tree_fingerprint(root)
    manifest["updated"] = today(args.date)
    write_manifest(mpath, manifest)

    # install/refresh status.py next to the manifest so the checker travels
    # with the repo (collaborators without the CLI can still run it)
    tmpl = Path(__file__).resolve().parent / "templates" / "status.py"
    if tmpl.exists():
        dst = wiki_dir / "status.py"
        if not dst.exists() or dst.read_bytes() != tmpl.read_bytes():
            dst.write_bytes(tmpl.read_bytes())
    else:
        # never silently skip: a missing template means a broken install
        print(f"warning: status.py template missing at {tmpl}; "
              "freshness checker not installed", file=sys.stderr)

    checkable = sum(1 for v in provenance.values()
                    if any(h not in SENTINELS for h in v["resources"].values()))
    print(f"stamped {len(provenance)} pages ({checkable} checkable, "
          f"{len(provenance) - checkable} unverifiable) in {mpath}")
    if drifted:
        print(f"warning: {len(drifted)} page(s) had drifted sources and are "
              f"now re-baselined: {', '.join(drifted[:6])}"
              + (" ..." if len(drifted) > 6 else ""))
        print("  if their content was NOT refreshed from source first "
              "(/brain ingest), this stamp just hid real staleness.")
    return manifest


def source_tree_fingerprint(root):
    """{count, sha12} over the repo's tracked file list (git), falling back
    to a pruned walk. List only, no contents: cheap, and enough to notice
    'files appeared that no page cites'."""
    files = None
    try:
        out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                             text=True, check=True).stdout
        files = sorted(l for l in out.splitlines() if l)
    except (subprocess.CalledProcessError, OSError):
        pass
    if files is None:
        skip = {"node_modules", "__pycache__", ".git", "output", "dist", "build"}
        files = sorted(
            str(f.relative_to(root)) for f in root.rglob("*")
            if f.is_file() and not any(
                part in skip or part.startswith(".")
                for part in f.relative_to(root).parts))
    h = hashlib.sha256("\n".join(files).encode()).hexdigest()[:12]
    return {"count": len(files), "sha": h}


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("wiki_dir", help="path to docs/wiki (or equivalent) directory")
    p.add_argument("command", choices=["init", "update", "stamp"])
    p.add_argument("--profile", choices=sorted(VALID_PROFILES), help="required for init")
    p.add_argument("--status", choices=sorted(VALID_STATUSES), default=None)
    p.add_argument("--plugin-version", default=DEFAULT_PLUGIN_VERSION)
    p.add_argument("--batches-done", type=int, default=None)
    p.add_argument("--batches-total", type=int, default=None)
    p.add_argument("--sha", default=None, help="git sha, or 'auto' to resolve HEAD of the containing repo")
    p.add_argument("--date", default=None, help="override created/updated date (YYYY-MM-DD); default: today")
    p.add_argument("--json", action="store_true", help="print resulting manifest as JSON to stdout")
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    wiki_dir = Path(args.wiki_dir)
    if not wiki_dir.exists():
        die(f"wiki dir does not exist: {wiki_dir}")
    if not wiki_dir.is_dir():
        die(f"not a directory: {wiki_dir}")

    if args.command == "init":
        if not args.profile:
            die("init requires --profile")
        manifest = cmd_init(args, wiki_dir)
    elif args.command == "stamp":
        manifest = cmd_stamp(args, wiki_dir)
    else:
        manifest = cmd_update(args, wiki_dir)

    if args.json:
        print(json.dumps(manifest, indent=2))
    else:
        # .get(): an `update` may be run against a hand-written manifest
        # (design S3 adopt path) that lacks some schema keys.
        print(f"wrote {manifest_path(wiki_dir)}")
        print(f"  profile={manifest.get('profile')} status={manifest.get('status')} "
              f"page_count={manifest.get('page_count')} "
              f"batches={manifest.get('batches_done')}/{manifest.get('batches_total')} "
              f"sha={manifest.get('compiled_from_sha')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
