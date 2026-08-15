#!/usr/bin/env python3
# STATUS_PY_VERSION: 2
"""status.py — freshness checker for this compiled wiki. Self-contained,
Python 3.9+ stdlib only, no plugin required: anyone who clones the repo can
run it, in any coding harness that can run a shell command.

The wiki is a CACHE of the codebase. This script is the cache-validity
check. It compares content hashes recorded in manifest.json (written by the
tokentelemetry plugin's stamp step at compile/ingest time) against the
repository's files RIGHT NOW. Content hashes, not git shas: results are
identical across worktrees, squash-merges, rebases, and tarballs.

Usage:
  python3 docs/wiki/status.py                 whole-wiki report
  python3 docs/wiki/status.py <page-id>       one page (e.g. subsystems/scanner)
  python3 docs/wiki/status.py <page-id> --note  also queue a refresh note in raw/
  python3 docs/wiki/status.py --json          machine-readable full report

Verdicts per page:
  FRESH        at least one recorded source verified byte-identical to
               compile time, none changed, and the page itself is
               untouched. Safe to answer from.
  STALE        a source changed (or moved/vanished). Do NOT trust the page
               body. Read the listed source files and answer from CODE; the
               page still tells you which files matter.
  TAMPERED     the page file was edited outside /brain workflows. Trust the
               listed sources, not the page.
  UNVERIFIABLE nothing checkable: no provenance recorded, no repo files
               cited, or every cited source is unhashable (too large,
               missing at stamp time). Treat as hints; verify before
               relying. An unhashable source is NEVER reported fresh.

Honest limits (read once):
- FRESH means "no drift since compile", not "cannot be forged": an editor
  with repo write access who updates both a page and manifest.json will not
  be detected. TAMPERED catches accidents and naive edits only.
- Many pages STALE at once usually means one shared source file changed,
  not that the wiki rotted; the report groups by changed file.
- A fact that moved to a file NO page cites is invisible per page; the
  repo-fingerprint advisory at the bottom of the report is the only signal.

The protocol for agents (also in the CLAUDE.md/AGENTS.md pointer block):
fresh -> use the page; stale/tampered -> read sources, answer from code,
re-run with --note; unverifiable -> verify first. Code is ALWAYS
authoritative over the wiki. Never edit wiki pages by hand; never "fix"
code to match a wiki page. Refreshing the wiki (/brain ingest, in Claude
Code) is optional batched maintenance, never required to keep working.

Exit codes: 0 fresh/ok, 1 stale or tampered pages found, 2 error,
3 nothing checkable (whole-wiki report where no page could be verified —
automation must not read this as a green light).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

WIKI = Path(__file__).resolve().parent
NOTES = WIKI / "raw" / "stale-notes.md"
NOTES_HEADER = ("# Pending wiki refresh notes\n\nAppended by status.py --note; "
                "swept and cleared by the next /brain ingest. One line per "
                "stale page.\n\n")
DIR_HASH_FILE_CAP = 200
SENTINELS = {"missing", "unhashable"}
SAFE_ID_RE = re.compile(r"[^\w/.-]")


def sha12(data):
    return hashlib.sha256(data).hexdigest()[:12]


def self_cmd():
    """How to invoke this script from the caller's cwd (footer suggestions
    must be copy-pasteable, not just the bare filename)."""
    try:
        return os.path.relpath(Path(__file__).resolve())
    except ValueError:
        return str(Path(__file__).resolve())


def repo_root():
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             cwd=WIKI, capture_output=True, text=True, check=True
                             ).stdout.strip()
        if top:
            return Path(top)
    except Exception:
        pass
    return WIKI.parent.parent


def hash_resource(root, rel):
    p = (root / rel.lstrip("/")).resolve()
    try:
        p.relative_to(root.resolve())
    except ValueError:
        return "unhashable"
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


def check_page(root, prov, page_id):
    """Return (verdict, changed_resources, sources, why). Precedence:
    TAMPERED > STALE > UNVERIFIABLE > FRESH. A sentinel recorded hash
    ("missing"/"unhashable") never counts as verification: comparing
    unhashable to unhashable proves nothing, so a page with only sentinel
    resources is UNVERIFIABLE, not FRESH."""
    entry = prov.get(page_id)
    page_file = WIKI / (page_id + ".md")
    if entry is None:
        return "UNVERIFIABLE", [], [], "no provenance recorded for this page"
    resources = entry.get("resources") or {}
    sources = sorted(resources)
    if not page_file.exists():
        return "STALE", [], sources, "page file missing (deleted or moved)"
    if sha12(page_file.read_bytes()) != entry.get("page_sha"):
        return ("TAMPERED", [], sources,
                "page body changed outside /brain workflows")
    if not resources:
        return ("UNVERIFIABLE", [], [],
                "page cites no repo files; nothing to check")
    changed, verified, unhashable = [], 0, 0
    for rel, recorded in resources.items():
        now = hash_resource(root, rel)
        if now != recorded:
            changed.append(f"{rel} ({recorded} -> {now})")
        elif recorded in SENTINELS:
            unhashable += 1
        else:
            verified += 1
    if changed:
        return "STALE", changed, sources, "source changed since this page was compiled"
    if verified == 0:
        return ("UNVERIFIABLE", [], sources,
                f"all {unhashable} cited source(s) unhashable or missing; "
                f"freshness cannot be proven")
    why = "all verifiable sources byte-identical to compile time"
    if unhashable:
        why += f" ({unhashable} source(s) unhashable, not counted)"
    return "FRESH", [], sources, why


def load():
    mpath = WIKI / "manifest.json"
    if not mpath.exists():
        print("error: no manifest.json next to status.py; this wiki has no "
              "provenance. Run the plugin's stamp step (wiki_manifest.py "
              "<wiki-dir> stamp) from Claude Code first.", file=sys.stderr)
        sys.exit(2)
    try:
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: cannot parse manifest.json: {e}", file=sys.stderr)
        sys.exit(2)
    prov = manifest.get("provenance")
    if not isinstance(prov, dict) or not prov:
        print("error: manifest.json has no provenance block; run the stamp "
              "step (wiki_manifest.py <wiki-dir> stamp) first.", file=sys.stderr)
        sys.exit(2)
    return manifest, prov


def pending_notes():
    if not NOTES.exists():
        return 0
    try:
        return sum(1 for l in NOTES.read_text(encoding="utf-8").splitlines()
                   if l.startswith("- STALE:"))
    except OSError:
        return 0


def append_note(page_id, changed):
    # page ids come from filenames, which an attacker (or accident) can fill
    # with instruction-looking text; sanitize so raw/stale-notes.md only ever
    # carries [word/.-] ids and known-charset paths, never free text
    safe_id = SAFE_ID_RE.sub("_", page_id)
    files = ", ".join(SAFE_ID_RE.sub("_", c.split(" ")[0]) for c in changed)
    line = f"- STALE: `{safe_id}` — changed: {files or 'page/sources'}"
    NOTES.parent.mkdir(parents=True, exist_ok=True)
    existing = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""
    if f"- STALE: `{safe_id}`" in existing:
        return False  # already queued; one note per page until the next ingest
    with open(NOTES, "a", encoding="utf-8") as f:
        if not existing:
            f.write(NOTES_HEADER)
        f.write(line + "\n")
    return True


def protocol_line(verdict):
    return {
        "FRESH": "OK to answer from this page.",
        "STALE": "Do NOT trust the page body. Read the changed source files "
                 "listed above and answer from CODE. The rest of the page's "
                 "file map is still useful for finding things.",
        "TAMPERED": "Page was hand-edited; do not trust its body. Answer from "
                    "the recorded source files listed above. Mention the "
                    "tamper to the user.",
        "UNVERIFIABLE": "Treat the page as hints only; verify claims against "
                        "the files it mentions before relying on them.",
    }[verdict]


def main(argv):
    as_json = "--json" in argv
    note = "--note" in argv
    args = [a for a in argv if not a.startswith("--")]
    manifest, prov = load()
    root = repo_root()

    if args:  # single page
        page_id = args[0]
        if page_id.endswith(".md"):
            page_id = page_id[:-3]
        page_id = page_id.strip("/")
        # never let a page id escape the wiki dir
        try:
            (WIKI / (page_id + ".md")).resolve().relative_to(WIKI)
        except ValueError:
            print(f"error: not a wiki page id: {page_id}", file=sys.stderr)
            return 2
        if page_id not in prov and not (WIKI / (page_id + ".md")).exists():
            print(f"error: no such page: {page_id}", file=sys.stderr)
            return 2
        verdict, changed, sources, why = check_page(root, prov, page_id)
        if as_json:
            print(json.dumps({"page": page_id, "verdict": verdict,
                              "changed": changed, "sources": sources,
                              "why": why}))
        else:
            print(f"{verdict}: {page_id} — {why}")
            for c in changed:
                print(f"  changed: {c}")
            if verdict in ("TAMPERED", "UNVERIFIABLE") and sources:
                print(f"  recorded sources: {', '.join(sources)}")
            print(f"  -> {protocol_line(verdict)}")
        if note and verdict in ("STALE", "TAMPERED"):
            added = append_note(page_id, changed)
            if not as_json:
                print("  note queued in raw/stale-notes.md" if added
                      else "  note already queued")
        return 1 if verdict in ("STALE", "TAMPERED") else 0

    # whole wiki
    rows = []
    for page_id in sorted(prov):
        verdict, changed, sources, why = check_page(root, prov, page_id)
        rows.append({"page": page_id, "verdict": verdict,
                     "changed": changed, "why": why})
    # pages on disk that were never stamped are unverifiable too
    for p in sorted(WIKI.rglob("*.md")):
        rel = p.relative_to(WIKI)
        if rel.name in ("index.md", "log.md", "BRAIN.md", "project-profile.md") and len(rel.parts) == 1:
            continue
        if any(part.startswith(".") for part in rel.parts) or rel.parts[0] == "raw":
            continue
        pid = str(rel)[:-3]
        if pid not in prov:
            rows.append({"page": pid, "verdict": "UNVERIFIABLE",
                         "changed": [], "why": "created after last stamp"})

    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    bad = [r for r in rows if r["verdict"] in ("STALE", "TAMPERED")]
    checkable = counts.get("FRESH", 0) + len(bad)
    queued = pending_notes()

    # repo-fingerprint advisory: files added/removed since stamp may carry
    # facts no page cites (the per-page check cannot see those)
    tree_note = None
    recorded_tree = manifest.get("source_tree")
    if isinstance(recorded_tree, dict) and recorded_tree.get("sha"):
        # recompute the same way stamp did (git list, pruned-walk fallback)
        try:
            out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True,
                                 text=True, check=True).stdout
            files = sorted(l for l in out.splitlines() if l)
        except (subprocess.CalledProcessError, OSError):
            skip = {"node_modules", "__pycache__", ".git", "output", "dist", "build"}
            files = sorted(
                str(f.relative_to(root)) for f in root.rglob("*")
                if f.is_file() and not any(
                    part in skip or part.startswith(".")
                    for part in f.relative_to(root).parts))
        now_sha = hashlib.sha256("\n".join(files).encode()).hexdigest()[:12]
        if now_sha != recorded_tree["sha"]:
            tree_note = (f"repo file set changed since stamp "
                         f"({recorded_tree.get('count')} -> {len(files)} files): "
                         f"new files may hold facts no page cites yet.")

    if as_json:
        print(json.dumps({"stamped": manifest.get("provenance_stamped"),
                          "counts": counts, "checkable": checkable,
                          "pending_notes": queued, "tree_changed": bool(tree_note),
                          "pages": rows}))
        return 1 if bad else (3 if checkable == 0 else 0)

    print(f"wiki status (stamped {manifest.get('provenance_stamped')}): "
          + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    for r in bad:
        print(f"  {r['verdict']}: {r['page']}"
              + (f" — {r['changed'][0]}" + (f" (+{len(r['changed'])-1} more)" if len(r['changed']) > 1 else "")
                 if r["changed"] else ""))
    unv = counts.get("UNVERIFIABLE", 0)
    if unv:
        print(f"  blind spot: {unv} page(s) have no checkable provenance and "
              f"CANNOT be verified — treat them as hints, not facts.")
    if queued:
        print(f"  pending: raw/stale-notes.md has {queued} queued note(s); "
              f"the next /brain ingest sweeps them.")
    if tree_note:
        print(f"  advisory: {tree_note}")
    if bad:
        print(f"  -> stale/tampered pages: answer from their source files, not "
              f"the page body. Queue refreshes with: python3 {self_cmd()} "
              f"<page> --note. Catch up anytime with /brain ingest "
              f"(Claude Code; optional).")
    if checkable == 0:
        print("  -> NOTHING here could be verified; this report is not a "
              "green light. Run the stamp step to establish provenance.")
        return 3
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
