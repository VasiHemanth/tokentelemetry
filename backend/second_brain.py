"""Second Brain (project wiki) read-side: detection, graph, page detail, registry.

Serves the dashboard's Second Brain tab. Strictly read-only with respect to
project repos: the ONLY write this module ever performs is to TT's own
registry file (~/.tokentelemetry/brains.json), which maps a project path to a
wiki directory the user explicitly imported. Wikis are produced and mutated by
the tokentelemetry Claude Code plugin, never by the dashboard.

Wiki format: an OKF v0.1 bundle (markdown pages with YAML frontmatter carrying
`type`, plus index.md / log.md / manifest.json), but detection degrades
gracefully: a plain markdown wiki or an Obsidian vault still renders as a
graph (nodes = files, edges = links), just without types or staleness.
"""

import json
import os
import re
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from tt_paths import data_dir

# Files that are bundle plumbing, not concept pages. index.md links every page
# by design; graphing it would star-connect the whole wiki and destroy the
# real link structure, so reserved files are excluded from nodes AND edges.
_RESERVED = {"index.md", "log.md", "BRAIN.md", "project-profile.md", "README.md"}

# raw/ is the plugin's committed inbox of immutable source drops, .compile/ and
# .obsidian/ are working state: none of them are pages.
_SKIP_PARTS = ("raw",)

_MD_LINK_RE = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)

_BRAINS_FILE = "brains.json"

# Graph cache: wiki dirs are small (tens of pages) but the tab polls; a short
# TTL plus a max-mtime fingerprint keeps rebuilds cheap and correct.
_graph_cache: Dict[str, dict] = {}
_graph_cache_lock = threading.Lock()
_GRAPH_TTL_SEC = 10.0


# ---------------------------------------------------------------- registry

def _brains_path() -> Path:
    return data_dir() / _BRAINS_FILE


def load_brains() -> Dict[str, str]:
    """project path -> imported wiki dir. Missing/malformed reads never raise."""
    try:
        data = json.loads(_brains_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}


def save_brains(brains: Dict[str, str]) -> None:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    tmp = _brains_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(brains, indent=2))
    os.replace(tmp, _brains_path())


# ---------------------------------------------------------------- parsing

def _split_frontmatter(text: str) -> Tuple[dict, str]:
    """Return (frontmatter dict, body). Tolerant: bad YAML -> ({}, full text)."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            try:
                fm = yaml.safe_load(text[3:end])
                if isinstance(fm, dict):
                    return fm, text[end + 4:]
            except Exception:
                pass
    return {}, text


def _page_title(fm: dict, body: str, rel: str) -> str:
    t = str(fm.get("title") or "").strip()
    if t:
        return t
    m = _H1_RE.search(body)
    if m:
        return m.group(1).strip()
    return Path(rel).stem.replace("-", " ").replace("_", " ")


def _iter_pages(wiki_dir: Path):
    """Yield (rel_posix, path) for concept pages only."""
    for p in sorted(wiki_dir.rglob("*.md")):
        rel = p.relative_to(wiki_dir).as_posix()
        parts = Path(rel).parts
        if any(part.startswith(".") for part in parts):
            continue
        if parts[0] in _SKIP_PARTS:
            continue
        if rel in _RESERVED:
            continue
        yield rel, p


# ---------------------------------------------------------------- detection

def _read_manifest(wiki_dir: Path) -> Optional[dict]:
    try:
        data = json.loads((wiki_dir / "manifest.json").read_text())
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _looks_typed(wiki_dir: Path, sample: int = 20) -> bool:
    checked = 0
    for _, p in _iter_pages(wiki_dir):
        if checked >= sample:
            break
        checked += 1
        try:
            fm, _ = _split_frontmatter(p.read_text(errors="ignore"))
        except OSError:
            continue
        if str(fm.get("type") or "").strip():
            return True
    return False


def classify_wiki_dir(wiki_dir: Path) -> Optional[str]:
    """Detection ladder for one directory. Returns kind or None.

    plugin_wiki > okf_ish > obsidian_vault > markdown_wiki (same ladder the
    plugin's profile_census.py uses, so both sides agree on what counts).
    """
    if not wiki_dir.is_dir():
        return None
    if (wiki_dir / "manifest.json").is_file():
        return "plugin_wiki"
    has_index = (wiki_dir / "index.md").is_file()
    md_count = sum(1 for _ in _iter_pages(wiki_dir))
    if md_count == 0 and not has_index:
        return None
    if has_index and _looks_typed(wiki_dir):
        return "okf_ish"
    if (wiki_dir / ".obsidian").is_dir():
        return "obsidian_vault"
    if md_count >= 2:
        return "markdown_wiki"
    return None


def resolve_wiki(project: Path, registered: Optional[str]) -> Tuple[Optional[Path], Optional[str], str]:
    """(wiki_dir, kind, source). Registered import wins over the default location."""
    if registered:
        kind = classify_wiki_dir(Path(registered))
        if kind:
            return Path(registered), kind, "registered"
    default = project / "docs" / "wiki"
    kind = classify_wiki_dir(default)
    if kind:
        return default, kind, "default"
    # An Obsidian vault at the project root (no docs/wiki) still counts.
    if (project / ".obsidian").is_dir():
        return project, "obsidian_vault", "default"
    return None, None, "none"


def wiki_summary(project: Path, registered: Optional[str]) -> dict:
    wiki_dir, kind, source = resolve_wiki(project, registered)
    if wiki_dir is None:
        return {"exists": False, "kind": None, "source": "none"}
    manifest = _read_manifest(wiki_dir) or {}
    page_count = sum(1 for _ in _iter_pages(wiki_dir))
    return {
        "exists": True,
        "kind": kind,
        "source": source,
        "wiki_path": str(wiki_dir),
        "page_count": page_count,
        "status": manifest.get("status"),
        "profile": manifest.get("profile"),
        "batches_done": manifest.get("batches_done"),
        "batches_total": manifest.get("batches_total"),
        "updated": manifest.get("updated"),
        "compiled_from_sha": manifest.get("compiled_from_sha"),
    }


def scan_candidates(project: Path) -> List[dict]:
    """Shallow scan for importable wiki-shaped trees inside the project."""
    candidates = []
    seen = set()

    def consider(d: Path):
        key = str(d.resolve())
        if key in seen:
            return
        seen.add(key)
        kind = classify_wiki_dir(d)
        if kind:
            candidates.append({
                "path": str(d),
                "kind": kind,
                "page_count": sum(1 for _ in _iter_pages(d)),
            })

    # decision: bare docs/ is deliberately absent; loose documentation folders
    # classify as markdown_wiki too easily and the offer reads as noise.
    for rel in ("docs/wiki", "wiki", "docs/kb", "kb", "notes"):
        consider(project / rel)
    # Obsidian vaults anywhere shallow (depth <= 2), including the root.
    try:
        if (project / ".obsidian").is_dir():
            consider(project)
        for child in sorted(project.iterdir()):
            if child.is_dir() and not child.name.startswith(".") and (child / ".obsidian").is_dir():
                consider(child)
    except OSError:
        pass
    return candidates


# ---------------------------------------------------------------- graph

def _mtime_fingerprint(wiki_dir: Path) -> float:
    latest = 0.0
    try:
        for _, p in _iter_pages(wiki_dir):
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                continue
        m = wiki_dir / "manifest.json"
        if m.exists():
            latest = max(latest, m.stat().st_mtime)
    except OSError:
        pass
    return latest


def _label_propagation(node_ids: List[str], neighbors: Dict[str, List[str]]) -> Dict[str, int]:
    """Deterministic label propagation for community clustering.

    Nodes iterate in sorted order adopting the most common label among their
    neighbors (ties -> smallest label), for a bounded number of rounds. No
    randomness: same wiki, same clusters, every request.
    """
    labels = {nid: i for i, nid in enumerate(sorted(node_ids))}
    for _ in range(20):
        changed = False
        for nid in sorted(node_ids):
            nbrs = neighbors.get(nid, [])
            if not nbrs:
                continue
            counts = Counter(labels[n] for n in nbrs)
            best = min(
                (lab for lab, c in counts.items() if c == max(counts.values()))
            )
            if labels[nid] != best:
                labels[nid] = best
                changed = True
        if not changed:
            break
    return labels


def build_graph(wiki_dir: Path, kind: str) -> dict:
    """Nodes (concept pages) + edges (resolved links) + clusters."""
    pages: Dict[str, dict] = {}
    raw_links: List[Tuple[str, str]] = []

    name_index: Dict[str, str] = {}
    for rel, p in _iter_pages(wiki_dir):
        node_id = rel[:-3]  # strip .md
        try:
            text = p.read_text(errors="ignore")
        except OSError:
            continue
        fm, body = _split_frontmatter(text)
        pages[node_id] = {
            "id": node_id,
            "title": _page_title(fm, body, rel),
            "type": str(fm.get("type") or "").strip() or None,
            "description": str(fm.get("description") or "").strip() or None,
            "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
            "timestamp": str(fm.get("timestamp") or "") or None,
            "resource": str(fm.get("resource") or "") or None,
            "dir": Path(node_id).parts[0] if len(Path(node_id).parts) > 1 else "",
        }
        name_index[Path(node_id).name.lower()] = node_id

        for target in _MD_LINK_RE.findall(text):
            if target.startswith(("http://", "https://")):
                continue
            base = wiki_dir if target.startswith("/") else p.parent
            try:
                resolved = (base / target.lstrip("/")).resolve()
                rel_t = resolved.relative_to(wiki_dir.resolve()).as_posix()
            except (OSError, ValueError):
                continue
            raw_links.append((node_id, rel_t[:-3] if rel_t.endswith(".md") else rel_t))
        if kind in ("obsidian_vault", "markdown_wiki"):
            for target in _WIKILINK_RE.findall(text):
                raw_links.append((node_id, "wikilink:" + target.strip().lower()))

    # index.md is the hub: it links every page by design, so it joins the
    # graph as a special center node whose edges are typed "index" (the
    # frontend renders them faint and the physics treats them as loose ties).
    # It stays OUT of degree counts and clustering, or it would star-connect
    # everything into one community.
    index_path = wiki_dir / "index.md"
    has_index_node = False
    if index_path.is_file():
        try:
            itext = index_path.read_text(errors="ignore")
        except OSError:
            itext = None
        if itext is not None:
            has_index_node = True
            pages["index"] = {
                "id": "index",
                "title": "Index",
                "type": "Index",
                "description": "The wiki's grouped directory: every page, one line each.",
                "tags": [],
                "timestamp": None,
                "resource": None,
                "dir": "",
            }
            for target in _MD_LINK_RE.findall(itext):
                if target.startswith(("http://", "https://")):
                    continue
                try:
                    resolved = (wiki_dir / target.lstrip("/")).resolve()
                    rel_t = resolved.relative_to(wiki_dir.resolve()).as_posix()
                except (OSError, ValueError):
                    continue
                raw_links.append(("index", rel_t[:-3] if rel_t.endswith(".md") else rel_t))

    # Resolve wikilinks by basename, dedupe, drop self-loops and dangling ends.
    edge_set = set()
    for src, dst in raw_links:
        if dst.startswith("wikilink:"):
            dst = name_index.get(dst[len("wikilink:"):].split("/")[-1], "")
        if not dst or dst == src or dst not in pages or src not in pages:
            continue
        edge_set.add((src, dst))

    real_edges = {(s, d) for s, d in edge_set if s != "index" and d != "index"}
    concept_ids = [nid for nid in pages if nid != "index"]
    neighbors: Dict[str, List[str]] = {nid: [] for nid in concept_ids}
    for src, dst in real_edges:
        neighbors[src].append(dst)
        neighbors[dst].append(src)
    for nid in concept_ids:
        pages[nid]["degree"] = len(neighbors[nid])
    if has_index_node:
        pages["index"]["degree"] = sum(1 for s, d in edge_set if s == "index" or d == "index")

    # Clustering: directories ARE the semantic grouping in an OKF bundle
    # (subsystems/, features/, ...), so use them when they exist; label
    # propagation would just re-discover a coarser version of them on a dense
    # wiki. Flat vaults (Obsidian, loose markdown) have no directory signal,
    # so communities come from the link structure instead.
    dirs = {pages[n]["dir"] for n in concept_ids if pages[n]["dir"]}
    dir_coverage = sum(1 for n in concept_ids if pages[n]["dir"]) / max(len(concept_ids), 1)
    if len(dirs) >= 2 and dir_coverage >= 0.6:
        group_of = {nid: (pages[nid]["dir"] or "core") for nid in concept_ids}
        label_for_group = {g: (g if g != "core" else "core") for g in set(group_of.values())}
    else:
        labels = _label_propagation(concept_ids, neighbors)
        group_of = {nid: f"c{labels[nid]}" for nid in concept_ids}
        # Name each community after its best-connected member.
        label_for_group = {}
        for g in set(group_of.values()):
            members = [n for n in concept_ids if group_of[n] == g]
            top = max(members, key=lambda n: (pages[n]["degree"], n))
            label_for_group[g] = pages[top]["title"]

    clusters: List[dict] = []
    cluster_idx: Dict[str, int] = {}
    for g in sorted(set(group_of.values()), key=lambda g: (-sum(1 for n in group_of if group_of[n] == g), g)):
        cluster_idx[g] = len(clusters)
        clusters.append({
            "id": len(clusters),
            "label": label_for_group[g],
            "size": sum(1 for n in group_of if group_of[n] == g),
        })
    for nid in concept_ids:
        pages[nid]["cluster"] = cluster_idx[group_of[nid]]
    if has_index_node:
        pages["index"]["cluster"] = -1  # hub: no hull, anchored to the center

    type_counts = Counter(pages[n]["type"] or "untyped" for n in concept_ids)
    return {
        "nodes": list(pages.values()),
        "edges": [
            {"source": s, "target": t,
             "kind": "index" if "index" in (s, t) else "link"}
            for s, t in sorted(edge_set)
        ],
        "clusters": clusters,
        "types": dict(type_counts),
    }


def graph_cached(wiki_dir: Path, kind: str) -> dict:
    key = str(wiki_dir.resolve())
    now = time.time()
    with _graph_cache_lock:
        hit = _graph_cache.get(key)
        if hit and now - hit["at"] < _GRAPH_TTL_SEC:
            return hit["graph"]
    fp = _mtime_fingerprint(wiki_dir)
    with _graph_cache_lock:
        hit = _graph_cache.get(key)
        if hit and hit["fp"] == fp:
            hit["at"] = now
            return hit["graph"]
    graph = build_graph(wiki_dir, kind)
    with _graph_cache_lock:
        _graph_cache[key] = {"graph": graph, "fp": fp, "at": now}
    return graph


# ---------------------------------------------------------------- page detail

def _staleness(project: Path, compiled_sha: Optional[str], resource: Optional[str]) -> dict:
    """Has the page's source changed since the wiki was compiled?

    Local git call only (no network). Any failure -> status "unknown": an
    honest shrug beats a wrong "fresh".
    """
    if not compiled_sha or not resource:
        return {"status": "unknown", "reason": "no compiled SHA or resource on record"}
    try:
        proc = subprocess.run(
            ["git", "diff", "--stat", compiled_sha, "--", resource],
            cwd=str(project), capture_output=True, text=True, timeout=3,
        )
        if proc.returncode != 0:
            return {"status": "unknown", "reason": (proc.stderr or "git error").strip()[:200]}
        stat = proc.stdout.strip()
        if not stat:
            return {"status": "fresh"}
        return {"status": "stale", "diffstat": stat.splitlines()[-1].strip()}
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unknown", "reason": "git unavailable"}


def page_detail(project: Path, wiki_dir: Path, page_id: str,
                compiled_sha: Optional[str], graph: dict) -> Optional[dict]:
    # page_id comes from the client: re-resolve and confine it to the wiki dir.
    try:
        p = (wiki_dir / (page_id + ".md")).resolve()
        p.relative_to(wiki_dir.resolve())
    except (OSError, ValueError):
        return None
    if not p.is_file():
        return None
    try:
        text = p.read_text(errors="ignore")
    except OSError:
        return None
    fm, body = _split_frontmatter(text)

    outbound = [e["target"] for e in graph["edges"] if e["source"] == page_id]
    inbound = [e["source"] for e in graph["edges"] if e["target"] == page_id]
    titles = {n["id"]: n["title"] for n in graph["nodes"]}
    resource = str(fm.get("resource") or "") or None

    return {
        "id": page_id,
        "title": _page_title(fm, body, page_id + ".md"),
        "type": str(fm.get("type") or "").strip() or None,
        "description": str(fm.get("description") or "").strip() or None,
        "tags": fm.get("tags") if isinstance(fm.get("tags"), list) else [],
        "timestamp": str(fm.get("timestamp") or "") or None,
        "resource": resource,
        "status": str(fm.get("status") or "") or None,
        "body": body.strip(),
        "outbound": [{"id": i, "title": titles.get(i, i)} for i in sorted(set(outbound))],
        "inbound": [{"id": i, "title": titles.get(i, i)} for i in sorted(set(inbound))],
        "staleness": _staleness(project, compiled_sha, resource),
    }
