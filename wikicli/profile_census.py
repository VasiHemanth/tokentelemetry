#!/usr/bin/env python3
"""profile_census.py: walk a project dir and propose a /brain domain profile.

Usage:
    python3 scripts/profile_census.py <project-dir> [--json] [--max-files N]

Stdlib only. No network. No writes. Read-only walk of the given path.

Exit codes: 0 = ok (profile suggested), 1 = ok but low-confidence / no strong
signal, 2 = error (bad path, walk failure).

# decision: BUILD-SPEC exit-code convention is ok/findings/error. There is no
# "findings" concept for a census (it always produces *a* suggestion), so 0/2
# are used normally and 1 is reserved for "ran fine but confidence is low";
# callers that care can branch on it, everyone else treats 0 and 1 as success.
"""

import argparse
import json
import os
import sys
from collections import Counter

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", ".next", "dist", "build",
    "__pycache__", ".obsidian",
}

DEFAULT_MAX_FILES = 50_000

FRONTEND_FRAMEWORK_DEPS = {
    "next": "Next.js",
    "react": "React",
    "react-dom": "React",
    "vue": "Vue",
    "@angular/core": "Angular",
    "svelte": "Svelte",
}

BACKEND_PY_FRAMEWORK_MARKERS = {
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
}


def walk_project(root, max_files):
    """Single bounded walk. Returns dict of raw counters + collected paths."""
    ext_count = Counter()
    ext_bytes = Counter()
    top_dir_count = Counter()
    top_dir_bytes = Counter()
    package_json_paths = []
    pyproject_paths = []
    requirements_paths = []
    dockerfile_paths = []
    graphify_out_dirs = []
    obsidian_dirs = []
    adr_dirs = []
    design_doc_paths = []
    sql_count = 0
    ipynb_count = 0
    total_files = 0
    truncated = False

    root = os.path.abspath(root)

    for dirpath, dirnames, filenames in os.walk(root):
        # Prior-knowledge markers: record BEFORE pruning (graphify-out and
        # .obsidian are skipped for the histogram walk; their presence is
        # still a signal brain-init leverages).
        if "graphify-out" in dirnames:
            graphify_out_dirs.append(os.path.join(dirpath, "graphify-out"))
        if ".obsidian" in dirnames:
            obsidian_dirs.append(os.path.join(dirpath, ".obsidian"))
        for adr_name in ("adr", "adrs"):
            if adr_name in dirnames:
                adr_dirs.append(os.path.join(dirpath, adr_name))

        # prune skip dirs in-place (works with topdown os.walk). A dir
        # containing pyvenv.cfg is a virtualenv whatever its name
        # (.venv-qwen, env310, ...); name matching alone misses those and a
        # single venv can dominate the whole histogram.
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in SKIP_DIRS
            and d != "graphify-out"
            and not os.path.exists(os.path.join(dirpath, d, "pyvenv.cfg"))
        )

        rel = os.path.relpath(dirpath, root)
        top_dir = "." if rel == "." else rel.split(os.sep)[0]

        for fname in sorted(filenames):
            if total_files >= max_files:
                truncated = True
                break
            fpath = os.path.join(dirpath, fname)
            try:
                size = os.path.getsize(fpath)
            except OSError:
                size = 0

            total_files += 1
            top_dir_count[top_dir] += 1
            top_dir_bytes[top_dir] += size

            _, ext = os.path.splitext(fname)
            ext = ext.lower() if ext else "(no ext)"
            ext_count[ext] += 1
            ext_bytes[ext] += size

            lower = fname.lower()
            if lower == "package.json":
                package_json_paths.append(fpath)
            elif lower == "pyproject.toml":
                pyproject_paths.append(fpath)
            elif lower.startswith("requirements") and lower.endswith(".txt"):
                requirements_paths.append(fpath)
            elif lower == "dockerfile" or lower.startswith("dockerfile."):
                dockerfile_paths.append(fpath)
            elif lower in ("design.md", "architecture.md"):
                design_doc_paths.append(fpath)
            elif ext == ".sql":
                sql_count += 1
            elif ext == ".ipynb":
                ipynb_count += 1

        if truncated:
            break

    return {
        "root": root,
        "total_files": total_files,
        "truncated": truncated,
        "ext_count": ext_count,
        "ext_bytes": ext_bytes,
        "top_dir_count": top_dir_count,
        "top_dir_bytes": top_dir_bytes,
        "package_json_paths": package_json_paths,
        "pyproject_paths": pyproject_paths,
        "requirements_paths": requirements_paths,
        "dockerfile_paths": dockerfile_paths,
        "graphify_out_dirs": graphify_out_dirs,
        "obsidian_dirs": obsidian_dirs,
        "adr_dirs": adr_dirs,
        "design_doc_paths": design_doc_paths,
        "sql_count": sql_count,
        "ipynb_count": ipynb_count,
    }


def parse_package_json_files(paths):
    """Parse each package.json found (excluding node_modules by construction
    of the walk). Returns aggregate dep set + per-file summaries."""
    all_deps = set()
    frontend_frameworks = set()
    files = []
    for p in paths:
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            files.append({"path": p, "error": "unparseable"})
            continue
        deps = {}
        deps.update(data.get("dependencies", {}) or {})
        deps.update(data.get("devDependencies", {}) or {})
        for dep_name in deps:
            all_deps.add(dep_name)
            if dep_name in FRONTEND_FRAMEWORK_DEPS:
                frontend_frameworks.add(FRONTEND_FRAMEWORK_DEPS[dep_name])
        files.append({
            "path": p,
            "name": data.get("name"),
            "dep_count": len(deps),
        })
    return {
        "files": files,
        "all_deps": sorted(all_deps),
        "frontend_frameworks": sorted(frontend_frameworks),
    }


def scan_python_backend_markers(pyproject_paths, requirements_paths):
    """Grep pyproject.toml / requirements*.txt text for known backend
    framework names. Cheap text search, not a real TOML/requirements parser
    (stdlib-only constraint; good enough for a marker, not a dependency
    resolver)."""
    found = set()
    for p in list(pyproject_paths) + list(requirements_paths):
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                text = f.read().lower()
        except OSError:
            continue
        for marker, label in BACKEND_PY_FRAMEWORK_MARKERS.items():
            if marker in text:
                found.add(label)
    return sorted(found)


def detect_git(root):
    # a worktree's ".git" is a *file* (gitdir: <path>), not a directory,
    # so check existence, not is-a-directory.
    return os.path.exists(os.path.join(root, ".git"))


def _file_has_frontmatter_type(path):
    """True if the file's leading YAML frontmatter block contains a
    `type:` key. Cheap line scan, not a YAML parser."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return False
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:200]:
        if line.strip() == "---":
            return False
        if line.lstrip().lower().startswith("type:"):
            return True
    return False


def any_wiki_page_has_frontmatter_type(wiki_dir, exclude=("index.md", "log.md")):
    """OKF page frontmatter (`type: Subsystem`, etc.) lives on content pages,
    not index.md/log.md. Sample up to 20 markdown files under the wiki dir
    (one level of subdirectories deep is enough; OKF bundles are shallow) and
    return True on the first frontmatter `type:` hit."""
    checked = 0
    for dirpath, dirnames, filenames in os.walk(wiki_dir):
        dirnames[:] = [d for d in sorted(dirnames) if d not in SKIP_DIRS]
        for fname in sorted(filenames):
            if not fname.endswith(".md") or fname in exclude:
                continue
            if checked >= 20:
                return False
            checked += 1
            if _file_has_frontmatter_type(os.path.join(dirpath, fname)):
                return True
    return False


def detect_existing_wiki(root):
    """Design doc section 8 detection ladder, applied to a single project
    root: docs/wiki/manifest.json (first-class) > OKF-ish (index.md + log.md
    + frontmatter type:) > Obsidian markers > generic markdown-wiki shape.
    Returns dict with `kind` in {plugin_wiki, okf_ish, obsidian_vault,
    generic_markdown_wiki, none} and supporting evidence."""
    docs_wiki = os.path.join(root, "docs", "wiki")
    manifest_path = os.path.join(docs_wiki, "manifest.json")
    index_path = os.path.join(docs_wiki, "index.md")
    log_path = os.path.join(docs_wiki, "log.md")
    obsidian_in_wiki = os.path.join(docs_wiki, ".obsidian")
    obsidian_at_root = os.path.join(root, ".obsidian")

    if os.path.isfile(manifest_path):
        return {
            "kind": "plugin_wiki",
            "path": docs_wiki,
            "evidence": ["docs/wiki/manifest.json present"],
        }

    if os.path.isdir(docs_wiki):
        has_index = os.path.isfile(index_path)
        has_log = os.path.isfile(log_path)
        if has_index and has_log:
            frontmatter_hit = any_wiki_page_has_frontmatter_type(docs_wiki)
            if frontmatter_hit:
                return {
                    "kind": "okf_ish",
                    "path": docs_wiki,
                    "evidence": [
                        "docs/wiki/index.md + log.md present",
                        "wiki page(s) carry frontmatter `type:` field",
                    ],
                }
            if os.path.isdir(obsidian_in_wiki):
                return {
                    "kind": "obsidian_vault",
                    "path": docs_wiki,
                    "evidence": [
                        "docs/wiki/index.md + log.md present",
                        "docs/wiki/.obsidian/ present",
                    ],
                }
            # decision: design section 8 lists OKF-ish signals conjunctively
            # (index.md + log.md + frontmatter type:). index+log alone, with
            # no typed page, falls through to generic markdown wiki rather
            # than claiming okf_ish on a partial match.
            return {
                "kind": "generic_markdown_wiki",
                "path": docs_wiki,
                "evidence": ["docs/wiki/index.md + log.md present, but no page carries frontmatter type:"],
            }
        if any(fname.endswith(".md") for fname in os.listdir(docs_wiki) if
               os.path.isfile(os.path.join(docs_wiki, fname))):
            return {
                "kind": "generic_markdown_wiki",
                "path": docs_wiki,
                "evidence": ["docs/wiki/ contains markdown files, no manifest/index+log"],
            }

    if os.path.isdir(obsidian_at_root):
        return {
            "kind": "obsidian_vault",
            "path": root,
            "evidence": [".obsidian/ present at project root"],
        }

    return {"kind": "none", "path": None, "evidence": []}


def collect_prior_knowledge(census, wiki):
    """Aggregate pre-existing knowledge sources /brain-init can leverage
    instead of paying full discovery cost: graphify graphs, Obsidian vaults,
    ADR dirs, design docs, and any wiki detect_existing_wiki found. One list,
    strongest evidence first. Paths capped at 10 per kind."""
    entries = []
    root = census["root"]

    for d in census["graphify_out_dirs"][:10]:
        graph = os.path.join(d, "graph.json")
        if os.path.isfile(graph):
            entries.append({
                "kind": "graphify_graph",
                "path": graph,
                "evidence": ["graphify-out/graph.json present (clusters can seed the compile queue)"],
            })
        else:
            entries.append({
                "kind": "graphify_out",
                "path": d,
                "evidence": ["graphify-out/ present but no graph.json (partial run?)"],
            })

    if wiki["kind"] != "none":
        entries.append({
            "kind": f"wiki:{wiki['kind']}",
            "path": wiki["path"],
            "evidence": wiki["evidence"],
        })

    # .obsidian inside docs/wiki is already covered by detect_existing_wiki;
    # report other vault locations separately.
    wiki_path = wiki["path"] or ""
    for d in census["obsidian_dirs"][:10]:
        parent = os.path.dirname(d)
        if wiki["kind"] == "obsidian_vault" and parent == wiki_path:
            continue
        entries.append({
            "kind": "obsidian_vault",
            "path": parent,
            "evidence": [os.path.relpath(d, root) + "/ present"],
        })

    for d in census["adr_dirs"][:10]:
        entries.append({
            "kind": "adr_dir",
            "path": d,
            "evidence": [os.path.relpath(d, root) + "/ present"],
        })

    if census["design_doc_paths"]:
        entries.append({
            "kind": "design_docs",
            "path": None,
            "evidence": [os.path.relpath(p, root)
                         for p in census["design_doc_paths"][:10]],
        })

    return entries


def suggest_profile(census, pkg_info, backend_markers, sql_count, ipynb_count):
    """Design doc section 5 detect signals:
    - package.json + backend/*.py -> fullstack-app
    - high .sql/.ipynb density -> research-data
    - .md/.pdf dominant, no build files -> generic
    """
    reasons_fullstack = []
    reasons_research = []
    reasons_generic = []

    has_package_json = bool(pkg_info["files"])
    has_frontend_framework = bool(pkg_info["frontend_frameworks"])
    has_backend_py = bool(backend_markers)
    has_pyproject_or_reqs = bool(census["pyproject_paths"]) or bool(census["requirements_paths"])
    has_dockerfile = bool(census["dockerfile_paths"])
    has_any_py = census["ext_count"].get(".py", 0) > 0

    if has_package_json:
        reasons_fullstack.append(
            f"package.json found ({len(pkg_info['files'])} file(s))"
        )
    if has_frontend_framework:
        reasons_fullstack.append(
            "frontend framework dep(s): " + ", ".join(pkg_info["frontend_frameworks"])
        )
    if has_backend_py:
        reasons_fullstack.append(
            "backend Python framework marker(s): " + ", ".join(backend_markers)
        )
    elif has_pyproject_or_reqs and has_any_py:
        reasons_fullstack.append("pyproject.toml/requirements.txt + .py files present")
    if has_dockerfile:
        reasons_fullstack.append(f"Dockerfile present ({len(census['dockerfile_paths'])})")

    total_files = max(census["total_files"], 1)
    sql_density = sql_count / total_files
    ipynb_density = ipynb_count / total_files

    if sql_count >= 5:
        reasons_research.append(f".sql files: {sql_count}")
    if ipynb_count >= 3:
        reasons_research.append(f".ipynb notebooks: {ipynb_count}")
    if sql_density > 0.03:
        reasons_research.append(f".sql density {sql_density:.1%} of all files")
    if ipynb_density > 0.02:
        reasons_research.append(f".ipynb density {ipynb_density:.1%} of all files")

    md_pdf_count = census["ext_count"].get(".md", 0) + census["ext_count"].get(".pdf", 0)
    md_pdf_ratio = md_pdf_count / total_files
    no_build_files = not has_package_json and not has_pyproject_or_reqs and not has_dockerfile
    if md_pdf_ratio > 0.4:
        reasons_generic.append(f".md/.pdf are {md_pdf_ratio:.1%} of all files")
    if no_build_files:
        reasons_generic.append("no package.json / pyproject.toml / requirements.txt / Dockerfile found")

    # scoring: each qualifying reason contributes; fullstack and research
    # signals are stronger indicators (explicit build tooling) than the
    # generic fallback, which is deliberately the weakest default.
    fullstack_score = len(reasons_fullstack) * 2
    research_score = len(reasons_research) * 2
    generic_score = len(reasons_generic)

    scores = {
        "fullstack-app": fullstack_score,
        "research-data": research_score,
        "generic": generic_score,
    }
    reasons_by_profile = {
        "fullstack-app": reasons_fullstack,
        "research-data": reasons_research,
        "generic": reasons_generic,
    }

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    top_profile, top_score = ranked[0]
    second_score = ranked[1][1]

    reasons = reasons_by_profile[top_profile][:4]
    if len(reasons) < 2:
        # pad with the generic no-signal reason so we never emit a bare
        # 1-reason suggestion (spec asks for 2-4 stated reasons).
        if not reasons:
            reasons.append("no strong domain signal detected; defaulting to generic")
            top_profile = "generic"
        reasons.append("insufficient corroborating signals; treat as a starting guess")

    if top_score == 0:
        confidence = "low"
        top_profile = "generic"
        reasons = reasons_by_profile["generic"][:4] or [
            "no strong domain signal detected; defaulting to generic",
            "run /brain-init and confirm/override manually",
        ]
    elif top_score >= 4 and top_score >= 2 * max(second_score, 1):
        confidence = "high"
    elif top_score >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "profile": top_profile,
        "confidence": confidence,
        "reasons": reasons,
        "scores": scores,
    }


def build_report(root, max_files):
    census = walk_project(root, max_files)
    pkg_info = parse_package_json_files(census["package_json_paths"])
    backend_markers = scan_python_backend_markers(
        census["pyproject_paths"], census["requirements_paths"]
    )
    git_present = detect_git(census["root"])
    wiki = detect_existing_wiki(census["root"])
    prior_knowledge = collect_prior_knowledge(census, wiki)
    suggestion = suggest_profile(
        census, pkg_info, backend_markers, census["sql_count"], census["ipynb_count"]
    )

    ext_histogram = [
        {"ext": ext, "count": count, "bytes": census["ext_bytes"][ext]}
        for ext, count in census["ext_count"].most_common()
    ]
    top_dir_summary = [
        {"dir": d, "count": count, "bytes": census["top_dir_bytes"][d]}
        for d, count in census["top_dir_count"].most_common()
    ]

    return {
        "root": census["root"],
        "total_files_scanned": census["total_files"],
        "walk_truncated": census["truncated"],
        "ext_histogram": ext_histogram,
        "top_dir_summary": top_dir_summary,
        "framework_markers": {
            "package_json": pkg_info["files"],
            "frontend_frameworks": pkg_info["frontend_frameworks"],
            "backend_python_frameworks": backend_markers,
            "pyproject_toml": census["pyproject_paths"],
            "requirements_txt": census["requirements_paths"],
            "dockerfiles": census["dockerfile_paths"],
            "sql_file_count": census["sql_count"],
            "ipynb_file_count": census["ipynb_count"],
        },
        "git_present": git_present,
        "existing_wiki": wiki,
        "prior_knowledge": prior_knowledge,
        "suggested_profile": suggestion,
    }


def format_bytes(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def print_human(report):
    print(f"project census: {report['root']}")
    print(f"files scanned: {report['total_files_scanned']}" +
          (" (TRUNCATED at cap)" if report["walk_truncated"] else ""))
    print(f"git present: {'yes' if report['git_present'] else 'no'}")
    print()

    print("extension histogram (top 15 by count):")
    for row in report["ext_histogram"][:15]:
        print(f"  {row['ext']:<14} count={row['count']:<6} bytes={format_bytes(row['bytes'])}")
    print()

    print("top-level dir summary:")
    for row in report["top_dir_summary"]:
        print(f"  {row['dir']:<20} count={row['count']:<6} bytes={format_bytes(row['bytes'])}")
    print()

    fm = report["framework_markers"]
    print("framework markers:")
    print(f"  package.json files: {len(fm['package_json'])}")
    for p in fm["package_json"]:
        if "error" in p:
            print(f"    {p['path']} (unparseable)")
        else:
            print(f"    {p['path']} (name={p.get('name')}, deps={p.get('dep_count')})")
    print(f"  frontend frameworks: {', '.join(fm['frontend_frameworks']) or 'none'}")
    print(f"  backend python frameworks: {', '.join(fm['backend_python_frameworks']) or 'none'}")
    print(f"  pyproject.toml: {len(fm['pyproject_toml'])}")
    print(f"  requirements.txt: {len(fm['requirements_txt'])}")
    print(f"  Dockerfiles: {len(fm['dockerfiles'])}")
    print(f"  .sql files: {fm['sql_file_count']}")
    print(f"  .ipynb files: {fm['ipynb_file_count']}")
    print()

    wiki = report["existing_wiki"]
    print(f"existing wiki: {wiki['kind']}" + (f" ({wiki['path']})" if wiki["path"] else ""))
    for ev in wiki["evidence"]:
        print(f"  - {ev}")
    print()

    pk = report["prior_knowledge"]
    print(f"prior knowledge sources: {len(pk)}")
    for entry in pk:
        loc = f" ({entry['path']})" if entry["path"] else ""
        print(f"  {entry['kind']}{loc}")
        for ev in entry["evidence"]:
            print(f"    - {ev}")
    print()

    sugg = report["suggested_profile"]
    print(f"suggested profile: {sugg['profile']}  (confidence: {sugg['confidence']})")
    print("reasons:")
    for r in sugg["reasons"]:
        print(f"  - {r}")
    print(f"scores: {sugg['scores']}")


def main():
    parser = argparse.ArgumentParser(
        description="Census a project dir and suggest a /brain domain profile."
    )
    parser.add_argument("project_dir", help="path to project root to scan")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of human text")
    parser.add_argument(
        "--max-files", type=int, default=DEFAULT_MAX_FILES,
        help=f"hard cap on files walked (default {DEFAULT_MAX_FILES})",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.project_dir):
        print(f"error: not a directory: {args.project_dir}", file=sys.stderr)
        return 2

    try:
        report = build_report(args.project_dir, args.max_files)
    except OSError as e:
        print(f"error: walk failed: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human(report)

    return 0 if report["suggested_profile"]["confidence"] != "low" else 1


if __name__ == "__main__":
    sys.exit(main())
