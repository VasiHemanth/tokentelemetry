"""Recall v3 discovery: find the project knowledge documents on disk.

Pure library, no network and no database. ``discover()`` returns the documents
(skills, commands, agent definitions, artifacts, images, instruction and memory
Markdown, MCP server descriptions) that belong to one project, plus a count of
everything skipped and why. Layouts follow docs/design/recall-knowledge-inventory.md;
rows the inventory marks unverified are probed defensively (a missing path is
counted as ``missing``, a bad file as ``parse_error``, nothing raises).

Rules enforced here, centrally:
  * ``is_never_index(path)`` is checked for every file and directory touched.
  * Only .md/.mdx files are walked in the project. Other text (.mdc, .txt,
    .toml commands) is read only from explicit inventory locations.
  * Directory walks use followlinks=False and never leave their base.
  * MCP configs are rendered through ``strip_secrets``; env, headers, token
    arguments, URL userinfo, paths and query strings never reach a document.
"""
from __future__ import annotations

import base64
import binascii
import fnmatch
import hashlib
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Set, Tuple
from urllib.parse import quote, unquote, urlsplit

try:  # pyyaml is in requirements.txt; stay importable without it
    import yaml as _yaml
except Exception:  # pragma: no cover
    _yaml = None

try:
    from redact import redact as _redact
except Exception:  # pragma: no cover
    def _redact(text: Any) -> str:
        return "" if text is None else str(text)

MD_EXTS = (".md", ".mdx")
IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif"}
MAX_MD_BYTES = 1_000_000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PROJECT_MD = 2000
MAX_CONFIG_BYTES = 32 * 1024 * 1024
MAX_DIR_FILES = 400          # per explicit directory (memory, plans, rules)

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", "target",
    ".venv", "venv", "__pycache__", ".mypy_cache", ".pytest_cache", ".tox",
    "site-packages",
}
SKIP_DIR_PATHS = (".claude/worktrees", ".codex/worktrees", ".grok/worktrees", ".worktrees")

# ---------------------------------------------------------------- never index

_NEVER_PARTS = {
    "paste-cache", "file-history", "antigravity-backup", "antigravity-browser-profile",
    "credentials", ".ssh", ".gnupg",
}
_NEVER_NAME_PATTERNS = (
    ".env", ".env.*", "*.env", "credentials*", ".credentials*", "auth*.json", "auth.json",
    "*.orig", "*.bak", "*.pem", "*.key", "id_rsa*", "shell_history", "history.jsonl",
    "oauth_creds.json", "google_accounts.json", "providers.json", "hosts.json", "apps.json",
    "jetski-standalone-oauth*", "default.rules", "*token*.json", "google_token.json",
)


def is_never_index(path: Any) -> bool:
    """True for credentials, caches of pasted/snapshotted content, histories and
    backups. Used by every discoverer; matching is on the basename and on exact
    directory names so unrelated parent directories cannot trigger it."""
    p = Path(str(path))
    name = p.name.lower()
    for pat in _NEVER_NAME_PATTERNS:
        if fnmatch.fnmatchcase(name, pat):
            return True
    return any(part.lower() in _NEVER_PARTS for part in p.parts)


# ----------------------------------------------------------------- secrets

_SECRET_KEY_RE = re.compile(
    r"(token|secret|passw|pwd|api[-_]?key|apikey|auth|bearer|credential|private[-_]?key|"
    r"access[-_]?key|session|cookie|(^|[-_.])key($|[-_.]))", re.I)
_HEADER_FLAGS = {"-h", "--header", "--headers"}
_OPAQUE_ARG_RE = re.compile(r"^[A-Za-z0-9_\-+/=.]{32,}$")


def _looks_secret_key(key: str) -> bool:
    return bool(_SECRET_KEY_RE.search(key.strip("-")))


def _safe_url(url: Any) -> str:
    """scheme://host[:port] only. Userinfo, path (may carry a token) and query are dropped."""
    if not isinstance(url, str) or not url.strip():
        return ""
    try:
        u = urlsplit(url.strip())
    except ValueError:
        return ""
    if not u.scheme or not u.hostname:
        return ""
    host = u.hostname
    if ":" in host:
        host = f"[{host}]"
    port = f":{u.port}" if u.port else ""
    return f"{u.scheme}://{host}{port}"


def _strip_args(args: Iterable[Any]) -> List[str]:
    out: List[str] = []
    drop_next = False
    for raw in args:
        if not isinstance(raw, (str, int, float)):
            continue
        a = str(raw)
        if drop_next:
            drop_next = False
            continue
        low = a.lower()
        if a.startswith("-"):
            flag, eq, val = a.partition("=")
            if flag.lower() in _HEADER_FLAGS or _looks_secret_key(flag):
                if not eq:
                    drop_next = True      # value is the next arg
                continue                  # --token=value dropped whole
            out.append(a)
            continue
        if "://" in a:
            out.append(_safe_url(a) or "<url>")
            continue
        if "bearer " in low or "authorization:" in low:
            continue
        if "=" in a:
            key = a.split("=", 1)[0]
            if _looks_secret_key(key):
                continue
        if _OPAQUE_ARG_RE.match(a) and not a.startswith(("/", ".", "@")) and not os.path.sep in a:
            continue                      # long opaque token passed positionally
        out.append(a)
    return out


def _tool_names(value: Any) -> List[str]:
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if isinstance(v, str)]
    if isinstance(value, dict):
        return [str(k) for k in value if isinstance(k, str)]
    return []


def strip_secrets(server_cfg: Any) -> Dict[str, Any]:
    """Reduce one MCP server config to the fields safe to index:
    ``transport``, ``command``, ``args`` (secret-free), ``url`` (scheme+host
    only), ``tools`` (names only) and ``disabled``. ``env``, ``headers``,
    ``environment`` and every other field are never copied."""
    if not isinstance(server_cfg, dict):
        return {"transport": "unknown", "command": "", "args": [], "url": "", "tools": [], "disabled": False}
    cmd = server_cfg.get("command")
    args = server_cfg.get("args")
    if isinstance(cmd, list):                       # OpenCode: command is an argv list
        argv = list(cmd)
        cmd = argv[0] if argv else ""
        args = argv[1:] + (args if isinstance(args, list) else [])
    if not isinstance(cmd, str):
        cmd = ""
    url = ""
    for k in ("url", "httpUrl", "serverUrl", "server_url"):
        if isinstance(server_cfg.get(k), str):
            url = _safe_url(server_cfg[k])
            break
    t = server_cfg.get("type") or server_cfg.get("transport")
    if isinstance(t, str) and t.lower() in {"local", "stdio"}:
        transport = "stdio"
    elif isinstance(t, str) and t.lower() in {"remote"}:
        transport = "http"
    elif isinstance(t, str) and t:
        transport = t.lower()
    elif cmd:
        transport = "stdio"
    elif url:
        transport = "http"
    else:
        transport = "unknown"
    tools: List[str] = []
    for k in ("tools", "includeTools", "include_tools", "autoApprove", "enabled_tools"):
        tools += _tool_names(server_cfg.get(k))
    disabled = bool(server_cfg.get("disabled")) or server_cfg.get("enabled") is False
    return {
        "transport": transport,
        "command": cmd if "://" not in cmd else (_safe_url(cmd) or ""),
        "args": _strip_args(args) if isinstance(args, list) else [],
        "url": url,
        "tools": list(dict.fromkeys(tools)),
        "disabled": disabled,
    }


def render_mcp(name: str, agent: str, scope: str, server_cfg: Any, used_tools: Iterable[str] = ()) -> str:
    s = strip_secrets(server_cfg)
    parts = [f"MCP server {name} ({agent}, {scope}): transport {s['transport']}"]
    if s["command"]:
        parts.append("command " + " ".join([s["command"]] + s["args"]))
    if s["url"]:
        parts.append("url " + s["url"])
    tools = list(dict.fromkeys(list(s["tools"]) + list(used_tools)))
    parts.append("tools: " + (", ".join(tools) if tools else "none listed"))
    if s["disabled"]:
        parts.append("disabled")
    return _redact(", ".join(parts))


# ------------------------------------------------------------ small helpers

def _fp(st: os.stat_result) -> str:
    return f"{st.st_mtime_ns}:{st.st_size}"


class _Ctx:
    """Shared state for one discover() run."""

    def __init__(self, project_root: str, sessions: List[dict], home: Path, env: Any, images: bool):
        self.root = Path(os.path.realpath(project_root)) if project_root else Path("/nonexistent-project")
        self.home = Path(home)
        self.env = env
        self.images = images
        self.sessions = [s for s in (sessions or []) if isinstance(s, dict)]
        self.skipped: Dict[str, int] = {}
        self.docs: Dict[str, dict] = {}
        self.seen_real: Set[str] = set()
        self.session_ids = {str(s.get("id")) for s in self.sessions if s.get("id")}
        self.used_names: Set[str] = set()      # skills, slash commands, subagent types
        self.used_servers: Dict[str, Set[str]] = {}
        self.plan_names: Set[str] = set()
        self._collect_usage()

    def skip(self, reason: str, n: int = 1) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + n

    # --- usage from existing session fields
    def _collect_usage(self) -> None:
        def add_name(v: Any) -> None:
            if isinstance(v, dict):
                v = v.get("name") or v.get("agent_type") or v.get("subagent_type") or v.get("skill")
            if isinstance(v, str) and v.strip():
                n = v.strip().lstrip("/").lower()
                self.used_names.add(n)
                if ":" in n:
                    self.used_names.add(n.rsplit(":", 1)[1])

        for s in self.sessions:
            for v in s.get("skills_used") or []:
                add_name(v)
            for v in s.get("commands_used") or s.get("slash_commands") or []:
                add_name(v)
            for v in s.get("subagents") or []:
                add_name(v)
            deleg = s.get("delegation")
            if isinstance(deleg, dict):
                for k in (deleg.get("by_type") or {}):
                    add_name(k)
                for e in deleg.get("subagents") or []:
                    add_name(e)
            tc = s.get("tool_counts")
            if isinstance(tc, dict):
                for t in tc:
                    self._add_mcp_tool(t)
            for t in s.get("mcp_tools") or []:
                self._add_mcp_tool(t)
            mu = s.get("mcp_usage")
            if isinstance(mu, dict):
                for server, tools in mu.items():
                    bucket = self.used_servers.setdefault(str(server), set())
                    if isinstance(tools, dict):
                        bucket.update(str(t) for t in tools)
            for p in s.get("plans") or []:
                n = p.get("path") or p.get("name") or p.get("file") if isinstance(p, dict) else p
                if isinstance(n, str) and n:
                    self.plan_names.add(os.path.basename(n))

    def _add_mcp_tool(self, name: Any) -> None:
        if not isinstance(name, str):
            return
        raw = name[len("default_api:"):] if name.startswith("default_api:") else name
        server = tool = None
        if raw.startswith("mcp__"):
            parts = raw.split("__", 2)
            if len(parts) == 3 and parts[1] and parts[2]:
                server, tool = parts[1], parts[2]
        elif raw.startswith("mcp_") and "_" in raw[4:]:
            server, tool = raw[4:].split("_", 1)
        if server:
            self.used_servers.setdefault(server, set()).add(tool or "")

    def name_used(self, name: str) -> bool:
        n = name.lower()
        return n in self.used_names or (":" in n and n.rsplit(":", 1)[1] in self.used_names)

    def server_used(self, name: str) -> bool:
        if name in self.used_servers:
            return True
        norm = name.replace("-", "_")
        return any(k.replace("-", "_") == norm for k in self.used_servers)

    def server_tools(self, name: str) -> List[str]:
        for k, v in self.used_servers.items():
            if k == name or k.replace("-", "_") == name.replace("-", "_"):
                return sorted(t for t in v if t)
        return []

    # --- paths
    def display(self, p: Path) -> str:
        try:
            return "~/" + p.relative_to(self.home).as_posix()
        except ValueError:
            pass
        try:
            rp = Path(os.path.realpath(self.home))
            return "~/" + p.relative_to(rp).as_posix()
        except ValueError:
            return p.as_posix()

    def rel_key(self, p: Path, scope: str) -> str:
        base = self.root if scope == "project" else self.home
        for b in (base, Path(os.path.realpath(base))):
            try:
                return p.relative_to(b).as_posix()
            except ValueError:
                continue
        return p.as_posix()

    def inside(self, p: Path, base: Path) -> bool:
        try:
            Path(os.path.realpath(p)).relative_to(Path(os.path.realpath(base)))
            return True
        except ValueError:
            return False

    # --- document registry
    def add_file(self, typ: str, agent: str, scope: str, title: str, path: Path,
                 key: Optional[str] = None, extra: Optional[dict] = None,
                 max_bytes: int = MAX_MD_BYTES) -> bool:
        """Register a file document. Returns True when added."""
        if is_never_index(path):
            self.skip("never_index")
            return False
        try:
            if (scope == "project" or path.is_symlink()) and not self.inside(
                    path, self.root if scope == "project" else self.home):
                self.skip("symlink_outside")
                return False
            st = path.stat()
        except OSError:
            self.skip("missing")
            return False
        if not path.is_file():
            self.skip("missing")
            return False
        real = os.path.realpath(path)
        if is_never_index(real):
            self.skip("never_index")
            return False
        if real in self.seen_real:
            return False
        if st.st_size > max_bytes:
            self.skip("too_large" if typ != "image" else "image_too_large")
            return False
        doc_id = f"{typ}:{agent}:{scope}:{key or self.rel_key(path, scope)}"
        doc = {
            "doc_id": doc_id, "type": typ, "agent": agent, "scope": scope, "title": title,
            "source": {"kind": "file", "path": self.display(path)},
            "mtime": st.st_mtime, "size": st.st_size, "cheap_fp": _fp(st),
            "abs_path": str(path), "real_path": real,
        }
        if extra:
            doc.update(extra)
        old = self.docs.get(doc_id)
        if old is not None:
            self.skip("duplicate")
            if old["mtime"] >= doc["mtime"]:
                return False
        self.docs[doc_id] = doc
        self.seen_real.add(real)
        return True


def _listdir(path: Path) -> List[str]:
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _walk_files(base: Path, exts: Tuple[str, ...], recursive: bool, cap: int = MAX_DIR_FILES,
                maxdepth: int = 6) -> Iterator[Path]:
    """Files under base with one of exts, deterministic order, no symlinked dirs."""
    n = 0
    base = Path(base)
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        depth = len(Path(dirpath).relative_to(base).parts)
        dirnames[:] = sorted(d for d in dirnames if not is_never_index(d) and d not in SKIP_DIRS)
        if not recursive or depth >= maxdepth:
            dirnames[:] = []
        for f in sorted(filenames):
            if f.lower().endswith(exts):
                n += 1
                if n > cap:
                    return
                yield Path(dirpath) / f


def _find_skill_dirs(root: Path, maxdepth: int = 4) -> List[Path]:
    """Directories holding SKILL.md under root; does not descend into a skill dir."""
    out: List[Path] = []
    if not root.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        depth = len(Path(dirpath).relative_to(root).parts)
        if "SKILL.md" in filenames:
            out.append(Path(dirpath))
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if not is_never_index(d) and d not in SKIP_DIRS) if depth < maxdepth else []
    return out


def _scan_plugins(root: Path, visit_cap: int = 30000) -> Dict[str, List[Path]]:
    """One bounded walk of a plugin cache: skills/commands/agents dirs and .mcp.json files."""
    found: Dict[str, List[Path]] = {"skills": [], "commands": [], "agents": [], "mcp": []}
    if not root.is_dir():
        return found
    visited = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        visited += 1
        if visited > visit_cap:
            break
        depth = len(Path(dirpath).relative_to(root).parts)
        if ".mcp.json" in filenames:
            found["mcp"].append(Path(dirpath) / ".mcp.json")
        keep = []
        for d in sorted(dirnames):
            if d in SKIP_DIRS or is_never_index(d):
                continue
            if d in ("skills", "commands", "agents"):
                found[d].append(Path(dirpath) / d)
                continue                       # do not descend into definition dirs
            keep.append(d)
        dirnames[:] = keep if depth < 9 else []
    return found


# ---------------------------------------------------------- per-agent layout

# Entries: relative paths. Project paths are relative to the project root;
# user paths are relative to the home ("~/" implied) with {tokens} for env homes.
# Dir entries are (relpath, exts, recursive).

def _d(rel: str, exts: Tuple[str, ...] = MD_EXTS, recursive: bool = False):
    return (rel, exts, recursive)


LAYOUT: Dict[str, Dict[str, Any]] = {
    "claude": {
        "skills_p": [".claude/skills"],
        "skills_u": ["{claude}/skills"], "plugins": ["{claude}/plugins"],
        "cmd_p": [_d(".claude/commands", recursive=True)], "cmd_u": [_d("{claude}/commands", recursive=True)],
        "agent_p": [_d(".claude/agents")], "agent_u": [_d("{claude}/agents")],
        "instr_p": ["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md", _d(".claude/rules", recursive=True)],
        "instr_u": ["{claude}/CLAUDE.md", _d("{claude}/rules", recursive=True)],
        "plans_p": [_d(".claude/plans")], "plans_u": [_d("{claude}/plans")],
        "mcp_p": [(".mcp.json", "json")],
        "mcp_u": [],  # ~/.claude.json handled specially (needs the project key)
    },
    "codex": {
        "skills_p": [".agents/skills"], "skills_u": ["{codex}/skills"], "plugins": ["{codex}/plugins/cache"],
        "cmd_u": [_d("{codex}/prompts")],
        "agent_p": [_d(".codex/agents", (".toml",))], "agent_u": [_d("{codex}/agents", (".toml",))],
        "instr_p": ["AGENTS.md", "AGENTS.override.md"],
        "instr_u": ["{codex}/AGENTS.md", "{codex}/AGENTS.override.md", "{codex}/instructions.md"],
        "memory_u": [_d("{codex}/memories")],
        "mcp_p": [(".codex/config.toml", "toml")], "mcp_u": [("{codex}/config.toml", "toml")],
        "image_dirs": ["{codex}/generated_images", "{codex}/attachments"],
    },
    "gemini": {
        "skills_p": [".gemini/skills"], "skills_u": ["{gemini}/skills", "{gemini}/extensions/*/skills"],
        "cmd_p": [_d(".gemini/commands", (".toml",), True)], "cmd_u": [_d("{gemini}/commands", (".toml",), True)],
        "agent_p": [_d(".gemini/agents")], "agent_u": [_d("{gemini}/agents")],
        "instr_p": ["GEMINI.md"], "instr_u": ["{gemini}/GEMINI.md"],
        "mcp_p": [(".gemini/settings.json", "json")], "mcp_u": [("{gemini}/settings.json", "json")],
    },
    "antigravity": {
        "skills_p": [".agents/skills", ".agent/skills"],
        "skills_u": ["{gemini}/antigravity/skills", "{gemini}/antigravity-cli/skills"],
        "cmd_p": [_d(".agents/workflows"), _d(".agent/workflows")], "cmd_u": [_d("{gemini}/antigravity/global_workflows")],
        "instr_p": [_d(".agents/rules"), _d(".agent/rules"), "GEMINI.md", "AGENTS.md"],
        "instr_u": ["{gemini}/GEMINI.md"],
        "mcp_u": [("{gemini}/antigravity/mcp_config.json", "json"), ("{gemini}/antigravity-cli/settings.json", "json")],
    },
    "cursor": {
        "skills_p": [".cursor/skills", ".cursor/skills-cursor"], "skills_u": ["~.cursor/skills", "~.cursor/skills-cursor"],
        "cmd_p": [_d(".cursor/commands")], "cmd_u": [_d("~.cursor/commands")],
        "agent_p": [_d(".cursor/agents")], "agent_u": [_d("~.cursor/agents")],
        "instr_p": [_d(".cursor/rules", (".mdc", ".md"), True), ".cursorrules", "AGENTS.md"],
        "mcp_p": [(".cursor/mcp.json", "json")], "mcp_u": [("~.cursor/mcp.json", "json")],
    },
    "copilot": {
        "skills_p": [".github/skills", ".claude/skills", ".agents/skills"], "skills_u": ["~.copilot/skills", "~.agents/skills"],
        "cmd_p": [_d(".github/prompts")],
        "agent_p": [_d(".github/agents")],
        "instr_p": [".github/copilot-instructions.md", _d(".github/instructions"), "AGENTS.md"],
        "instr_u": ["~.copilot/copilot-instructions.md"],
        "mcp_p": [(".vscode/mcp.json", "json"), (".mcp.json", "json")], "mcp_u": [("~.copilot/mcp-config.json", "json")],
    },
    "cline": {
        "skills_p": [".cline/skills", ".clinerules/skills", ".claude/skills"], "skills_u": ["~.cline/skills"],
        "cmd_p": [_d(".clinerules/workflows")],
        "instr_p": [".clinerules", _d(".clinerules", (".md", ".txt")), "AGENTS.md"],
        "memory_p": [_d("memory-bank")],
        "mcp_p": [(".cline/mcp.json", "json")],
        "mcp_u": [("{cline_mcp}", "json"), ("~.cline/data/settings/cline_mcp_settings.json", "json")],
    },
    "qwen": {
        "skills_p": [".qwen/skills"], "skills_u": ["~.qwen/skills"],
        "cmd_p": [_d(".qwen/commands", (".toml",), True)], "cmd_u": [_d("~.qwen/commands", (".toml",), True)],
        "agent_p": [_d(".qwen/agents")], "agent_u": [_d("~.qwen/agents")],
        "instr_p": ["QWEN.md"], "instr_u": ["~.qwen/QWEN.md"],
        "mcp_p": [(".qwen/settings.json", "json")], "mcp_u": [("~.qwen/settings.json", "json")],
    },
    "kimi": {
        "skills_p": [".agents/skills", ".kimi-code/skills"], "skills_u": ["~.agents/skills", "{kimicode}/skills", "{kimi}/skills"],
        "instr_p": ["AGENTS.md", ".kimi-code/AGENTS.md"],
        "instr_u": ["{kimicode}/AGENTS.md", "~.agents/AGENTS.md"],
        "mcp_p": [(".kimi-code/mcp.json", "json"), (".mcp.json", "json")], "mcp_u": [("{kimicode}/mcp.json", "json")],
    },
    "opencode": {
        "skills_p": [".opencode/skills", ".claude/skills"], "skills_u": ["{xdg}/opencode/skills"],
        "cmd_p": [_d(".opencode/commands")], "cmd_u": [_d("{xdg}/opencode/commands")],
        "agent_p": [_d(".opencode/agents")], "agent_u": [_d("{xdg}/opencode/agents")],
        "instr_p": ["AGENTS.md", "CLAUDE.md"], "instr_u": ["{xdg}/opencode/AGENTS.md"],
        "plans_p": [_d(".opencode/plans")],
        "mcp_p": [("opencode.json", "json"), ("opencode.jsonc", "json")],
        "mcp_u": [("{xdg}/opencode/opencode.json", "json"), ("{xdg}/opencode/opencode.jsonc", "json")],
    },
    "grok": {
        "skills_p": [".grok/skills", ".claude/skills"], "skills_u": ["~.grok/skills"],
        "agent_p": [_d(".grok/agents"), _d(".claude/agents")],
        "instr_p": ["AGENTS.md", "CLAUDE.md"],
        "memory_u": ["~.grok/memory-v2/global/MEMORY.md", _d("~.grok/memory-v2/global/topics")],
        "mcp_p": [(".mcp.json", "json")], "mcp_u": [("~.grok/config.toml", "toml")],
    },
    "pi": {
        "skills_p": [".pi/skills", ".agents/skills"], "skills_u": ["~.pi/agent/skills", "~.agents/skills"],
        "cmd_p": [_d(".pi/prompts")], "cmd_u": [_d("~.pi/agent/prompts")],
        "instr_p": ["AGENTS.md", "CLAUDE.md", "SYSTEM.md"], "instr_u": ["~.pi/agent/AGENTS.md"],
        "mcp_p": [(".pi/mcp.json", "json")], "mcp_u": [("~.pi/agent/mcp.json", "json")],
    },
    "omp": {
        "skills_p": [".omp/skills"], "skills_u": ["~.omp/agent/skills", "~.agents/skills"],
        "cmd_p": [_d(".omp/commands")], "cmd_u": [_d("~.omp/agent/commands")],
        "instr_p": [".omp/AGENTS.md", "AGENTS.md", "CLAUDE.md"],
    },
    "vibe": {
        "skills_p": [".vibe/skills"], "skills_u": ["{vibe}/skills"],
        "agent_p": [_d(".vibe/agents", (".toml",))], "agent_u": [_d("{vibe}/agents", (".toml",))],
        "instr_p": ["AGENTS.md"], "instr_u": ["{vibe}/AGENTS.md", "{vibe}/instructions.md"],
        "mcp_p": [(".vibe/config.toml", "toml")], "mcp_u": [("{vibe}/config.toml", "toml")],
    },
    "muse": {
        "skills_p": [".agents/skills", ".claude/skills", ".codex/skills"],
        "instr_p": ["AGENTS.md", "CLAUDE.md"], "memory_p": [_d(".agents/memory", recursive=True)],
    },
    "prime": {
        "instr_p": ["AGENTS.md", "CLAUDE.md"], "instr_u": ["~.prime/agent/AGENTS.md"],
    },
    "dsh": {
        "skills_p": [".dsh/skills", ".agents/skills"], "skills_u": ["~.dsh/skills"],
        "instr_p": ["AGENTS.md", "CLAUDE.md"],
        "mcp_u": [("~.dsh/settings.yaml", "yaml")],
    },
    "qoder": {
        "skills_u": ["~.qoder/skills"],
        "cmd_p": [_d(".qoder/commands")], "cmd_u": [_d("~.qoder/commands")],
        "agent_p": [_d(".qoder/agents")], "agent_u": [_d("~.qoder/agents")],
        "instr_p": ["AGENTS.md", "AGENTS.local.md", _d(".qoder/rules", recursive=True)], "instr_u": ["~.qoder/AGENTS.md"],
        "mcp_p": [(".mcp.json", "json")], "mcp_u": [("~.qoder/settings.json", "json")],
    },
    "zcode": {
        "plugins": ["~.zcode/cli/plugins/cache"],
        "instr_p": ["AGENTS.md"], "instr_u": ["~.zcode/AGENTS.md"],
        "mcp_p": [(".zcode/config.json", "json")], "mcp_u": [("~.zcode/cli/config.json", "json")],
    },
    "smallcode": {
        "skills_p": [".smallcode/skills"],
    },
    "hermes": {
        "skills_u": ["{hermes}/skills"],
        "instr_p": ["AGENTS.md", ".hermes.md", "CLAUDE.md", ".cursorrules"],
        "memory_u": ["{hermes}/memories/MEMORY.md", "{hermes}/memories/USER.md", "{hermes}/SOUL.md"],
        "mcp_u": [("{hermes}/config.yaml", "yaml")],
    },
}

AGENT_ORDER = list(LAYOUT)


def _resolve(ctx: _Ctx, tmpl: str) -> Optional[Path]:
    env = ctx.env
    home = ctx.home

    def e(name: str) -> Optional[str]:
        v = env.get(name) if hasattr(env, "get") else None
        return v if isinstance(v, str) and v else None

    toks = {
        "{claude}": e("CLAUDE_CONFIG_DIR") or str(home / ".claude"),
        "{codex}": e("CODEX_HOME") or str(home / ".codex"),
        "{gemini}": str(home / ".gemini"),
        "{hermes}": e("HERMES_HOME") or str(home / ".hermes"),
        "{kimi}": e("KIMI_HOME") or str(home / ".kimi"),
        "{kimicode}": e("KIMI_CODE_HOME") or str(home / ".kimi-code"),
        "{vibe}": e("VIBE_HOME") or str(home / ".vibe"),
        "{xdg}": e("XDG_CONFIG_HOME") or str(home / ".config"),
    }
    if tmpl == "{cline_mcp}":
        v = e("CLINE_MCP_SETTINGS_PATH")
        return Path(v) if v else None
    if tmpl.startswith("~"):
        return home / tmpl[1:]
    for k, v in toks.items():
        if tmpl.startswith(k):
            return Path(v + tmpl[len(k):])
    return home / tmpl


def _expand(ctx: _Ctx, tmpl: str) -> List[Path]:
    """Resolve a user-scope template; a single '*' path segment is expanded."""
    p = _resolve(ctx, tmpl)
    if p is None:
        return []
    if "*" not in p.parts:
        return [p]
    idx = p.parts.index("*")
    base = Path(*p.parts[:idx])
    rest = p.parts[idx + 1:]
    out = []
    for name in _listdir(base):
        cand = base / name
        if cand.is_dir() and not cand.is_symlink() and not is_never_index(cand):
            out.append(cand.joinpath(*rest))
    return out


# ------------------------------------------------------------- discoverers

def _frontmatter_name(path: Path) -> Optional[str]:
    return None  # names come from paths; frontmatter is not parsed (cheap, no reads)


def _add_skills(ctx: _Ctx, agent: str, scope: str, base: Path) -> None:
    dirs = _find_skill_dirs(base)
    if not dirs and not base.exists():
        ctx.skip("missing")
        return
    for d in dirs:
        name = d.name
        if scope == "user" and not ctx.name_used(name):
            ctx.skip("unused_user_item")
            continue
        ctx.add_file("skill", agent, scope, name, d / "SKILL.md", key=name if scope == "user" else None)


def _def_title(base: Path, f: Path) -> str:
    rel = f.relative_to(base).with_suffix("")
    return ":".join(rel.parts)


def _add_defs(ctx: _Ctx, typ: str, agent: str, scope: str, base: Path, exts: Tuple[str, ...], recursive: bool) -> None:
    if not base.is_dir():
        ctx.skip("missing")
        return
    for f in _walk_files(base, exts, recursive):
        title = _def_title(base, f)
        if scope == "user" and not ctx.name_used(title):
            ctx.skip("unused_user_item")
            continue
        ctx.add_file(typ, agent, scope, title, f, key=title)


def _add_text_entry(ctx: _Ctx, typ: str, agent: str, scope: str, base: Path, entry: Any,
                    exts_default: Tuple[str, ...] = MD_EXTS) -> None:
    """Instruction / memory / plan entry: a file path or a (dir, exts, recursive) tuple."""
    if isinstance(entry, tuple):
        d = base / entry[0] if scope == "project" else Path(entry[0])
        if not d.is_dir():
            ctx.skip("missing")
            return
        for f in _walk_files(d, entry[1], entry[2]):
            if scope == "project" and not ctx.inside(f, ctx.root):
                ctx.skip("symlink_outside")
                continue
            ctx.add_file(typ, agent, scope, f.name, f)
        return
    f = base / entry if scope == "project" else Path(entry)
    if f.is_dir():                                  # e.g. .clinerules as a directory handled by tuple entry
        return
    if not f.exists():
        ctx.skip("missing")
        return
    ctx.add_file(typ, agent, scope, f.name, f)


def _discover_agent(ctx: _Ctx, agent: str, lay: Dict[str, Any]) -> None:
    root = ctx.root

    # skills
    for rel in lay.get("skills_p", []):
        _add_skills(ctx, agent, "project", root / rel)
    for t in lay.get("skills_u", []):
        for p in _expand(ctx, t):
            _add_skills(ctx, agent, "user", p)

    # plugin bundles (user scope, used-only)
    for t in lay.get("plugins", []):
        p = _resolve(ctx, t)
        if p is None:
            continue
        if not p.is_dir():
            ctx.skip("missing")
            continue
        found = _scan_plugins(p)
        for d in found["skills"]:
            _add_skills(ctx, agent, "user", d)
        for d in found["commands"]:
            _add_defs(ctx, "command", agent, "user", d, MD_EXTS, True)
        for d in found["agents"]:
            _add_defs(ctx, "agent", agent, "user", d, MD_EXTS, False)
        for f in found["mcp"]:
            _mcp_from_file(ctx, agent, "user", f, "json")

    # commands / agents
    for entry in lay.get("cmd_p", []):
        _add_defs(ctx, "command", agent, "project", root / entry[0], entry[1], entry[2])
    for entry in lay.get("cmd_u", []):
        p = _resolve(ctx, entry[0])
        if p:
            _add_defs(ctx, "command", agent, "user", p, entry[1], entry[2])
    for entry in lay.get("agent_p", []):
        _add_defs(ctx, "agent", agent, "project", root / entry[0], entry[1], entry[2])
    for entry in lay.get("agent_u", []):
        p = _resolve(ctx, entry[0])
        if p:
            _add_defs(ctx, "agent", agent, "user", p, entry[1], entry[2])

    # instruction, memory
    for entry in lay.get("instr_p", []):
        _add_text_entry(ctx, "markdown", agent, "project", root, entry)
    for entry in lay.get("memory_p", []):
        _add_text_entry(ctx, "markdown", agent, "project", root, entry)
    for key in ("instr_u", "memory_u"):
        for entry in lay.get(key, []):
            if isinstance(entry, tuple):
                p = _resolve(ctx, entry[0])
                if p:
                    _add_text_entry(ctx, "markdown", agent, "user", root, (str(p), entry[1], entry[2]))
            else:
                p = _resolve(ctx, entry)
                if p:
                    _add_text_entry(ctx, "markdown", agent, "user", root, str(p))

    # plans in project (only when the agent lists a project plans dir)
    for entry in lay.get("plans_p", []):
        d = root / entry[0]
        if d.is_dir():
            for f in _walk_files(d, entry[1], entry[2]):
                ctx.add_file("artifact", agent, "project", f.name, f)
    # user plans: included only when a session in this project referenced the file
    for entry in lay.get("plans_u", []):
        p = _resolve(ctx, entry[0])
        if p is None or not p.is_dir():
            ctx.skip("missing")
            continue
        for f in _walk_files(p, entry[1], entry[2]):
            if f.name in ctx.plan_names:
                ctx.add_file("artifact", agent, "user", f.name, f)
            else:
                ctx.skip("unlinked_plan")

    # MCP
    for rel, kind in lay.get("mcp_p", []):
        _mcp_from_file(ctx, agent, "project", root / rel, kind)
    for tmpl, kind in lay.get("mcp_u", []):
        p = _resolve(ctx, tmpl)
        if p is not None:
            _mcp_from_file(ctx, agent, "user", p, kind)


# ------------------------------------------------------------------- MCP

def _strip_jsonc(text: str) -> str:
    out = []
    i, n, in_str = 0, len(text), False
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        else:
            out.append(c)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def _load_config(path: Path, kind: str) -> Any:
    st = path.stat()
    if st.st_size > MAX_CONFIG_BYTES:
        raise ValueError("config too large")
    raw = path.read_bytes()
    if kind == "toml":
        return tomllib.loads(raw.decode("utf-8", "replace"))
    if kind == "yaml":
        if _yaml is None:
            raise ValueError("no yaml")
        return _yaml.safe_load(raw.decode("utf-8", "replace"))
    text = raw.decode("utf-8", "replace")
    try:
        return json.loads(text)
    except ValueError:
        return json.loads(_strip_jsonc(text))


def _server_maps(cfg: Any, project_root: Path, home: Path) -> List[Tuple[str, Dict[str, Any]]]:
    """(scope_hint, {name: server_cfg}) candidates found in a parsed config."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    if not isinstance(cfg, dict):
        return out

    def as_map(v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return {str(k): s for k, s in v.items() if isinstance(s, dict)}
        if isinstance(v, list):                    # Vibe [[mcp_servers]]
            return {str(s.get("name")): s for s in v if isinstance(s, dict) and s.get("name")}
        return {}

    for key in ("mcpServers", "mcp_servers", "servers", "mcp"):
        m = as_map(cfg.get(key))
        if m:
            out.append(("file", m))
    projects = cfg.get("projects")                  # ~/.claude.json local scope, keyed by abs path
    if isinstance(projects, dict):
        for pk, pv in projects.items():
            if isinstance(pv, dict) and isinstance(pk, str):
                try:
                    same = os.path.realpath(pk) == str(project_root)
                except OSError:
                    same = False
                if same:
                    m = as_map(pv.get("mcpServers"))
                    if m:
                        out.append(("local", m))
    return out


def _mcp_from_file(ctx: _Ctx, agent: str, scope: str, path: Path, kind: str) -> None:
    if is_never_index(path):
        ctx.skip("never_index")
        return
    try:
        if path.is_symlink() and not ctx.inside(path, ctx.root if scope == "project" else ctx.home):
            ctx.skip("symlink_outside")
            return
        if not path.is_file():
            ctx.skip("missing")
            return
        st = path.stat()
        cfg = _load_config(path, kind)
    except OSError:
        ctx.skip("missing")
        return
    except Exception:
        ctx.skip("parse_error")
        return
    maps = _server_maps(cfg, ctx.root, ctx.home)
    # ~/.claude.json: top-level mcpServers are user scope, projects[<root>] are project-local
    for hint, servers in maps:
        eff_scope = "project" if hint == "local" else scope
        for name, s in sorted(servers.items()):
            if eff_scope == "user" and not ctx.server_used(name):
                ctx.skip("unused_user_item")
                continue
            tools = ctx.server_tools(name) if eff_scope == "user" or ctx.server_used(name) else []
            text = render_mcp(name, agent, eff_scope, s, tools)
            key = f"{name}@{ctx.rel_key(path, 'project' if scope == 'project' else 'user')}"
            doc_id = f"mcp:{agent}:{eff_scope}:{key}"
            dedupe = f"mcp:{os.path.realpath(path)}:{name}"
            if dedupe in ctx.seen_real:
                continue
            ctx.seen_real.add(dedupe)
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
            ctx.docs[doc_id] = {
                "doc_id": doc_id, "type": "mcp", "agent": agent, "scope": eff_scope, "title": name,
                "source": {"kind": "file", "path": ctx.display(path), "server": name},
                "mtime": st.st_mtime, "size": st.st_size, "cheap_fp": f"{_fp(st)}:{h}",
                "text": text,
            }


def _discover_claude_json(ctx: _Ctx) -> None:
    """~/.claude.json: user-scope mcpServers plus projects[<root>].mcpServers."""
    cdir = ctx.env.get("CLAUDE_CONFIG_DIR") if hasattr(ctx.env, "get") else None
    cands = [ctx.home / ".claude.json"]
    if cdir:
        cands.insert(0, Path(cdir) / ".claude.json")
    for p in cands:
        if p.exists():
            _mcp_from_file(ctx, "claude", "user", p, "json")
            return
    ctx.skip("missing")


# --------------------------------------------------- memory, artifacts, images

def _claude_slug(path: str) -> str:
    return re.sub(r"[/\\.]", "-", path)


def _discover_slug_memory(ctx: _Ctx, agent: str, base: Path) -> None:
    """<base>/projects/<slug>/memory/*.md for the project and its agent worktrees."""
    pdir = base / "projects"
    if not pdir.is_dir():
        ctx.skip("missing")
        return
    slugs = {_claude_slug(str(ctx.root)), _claude_slug(str(ctx.home / os.path.relpath(ctx.root, ctx.home)))
             if str(ctx.root).startswith(str(ctx.home)) else ""}
    slugs.discard("")
    for name in _listdir(pdir):
        if not any(name == s or name.startswith(s + "--claude-worktrees-") for s in slugs):
            continue
        mem = pdir / name / "memory"
        if mem.is_dir() and not mem.is_symlink():
            for f in _walk_files(mem, MD_EXTS, True):
                ctx.add_file("markdown", agent, "user", f.name, f)


def _discover_antigravity_brain(ctx: _Ctx) -> None:
    gem = _resolve(ctx, "{gemini}")
    if gem is None:
        return
    for sub in ("antigravity", "antigravity-cli", "antigravity-ide"):
        brain = gem / sub / "brain"
        if not brain.is_dir():
            ctx.skip("missing")
            continue
        for uid in _listdir(brain):
            d = brain / uid
            if not d.is_dir() or d.is_symlink():
                continue
            if uid not in ctx.session_ids:
                ctx.skip("unlinked_artifact")
                continue
            for f in _walk_files(d, MD_EXTS, False):
                ctx.add_file("artifact", "antigravity", "user", f.name, f, extra={"session_id": uid})
            if ctx.images:
                for f in _walk_files(d, tuple(IMAGE_EXTS), False):
                    ctx.add_file("image", "antigravity", "user", f.name, f, extra={
                        "mime": IMAGE_EXTS[f.suffix.lower()], "session_id": uid}, max_bytes=MAX_IMAGE_BYTES)


def _discover_gemini_tmp(ctx: _Ctx) -> None:
    gem = _resolve(ctx, "{gemini}")
    if gem is None:
        return
    h = hashlib.sha256(str(ctx.root).encode("utf-8")).hexdigest()
    d = gem / "tmp" / h
    if not d.is_dir():
        ctx.skip("missing")
        return
    plans = d / "plans"
    if plans.is_dir():
        for f in _walk_files(plans, MD_EXTS, True):
            ctx.add_file("artifact", "gemini", "user", f.name, f)
    if ctx.images and (d / "images").is_dir():
        for f in _walk_files(d / "images", tuple(IMAGE_EXTS), False):
            ctx.add_file("image", "gemini", "user", f.name, f, extra={"mime": IMAGE_EXTS[f.suffix.lower()]},
                         max_bytes=MAX_IMAGE_BYTES)


def _discover_copilot_state(ctx: _Ctx) -> None:
    base = ctx.home / ".copilot" / "session-state"
    if not base.is_dir():
        ctx.skip("missing")
        return
    for uid in _listdir(base):
        if uid not in ctx.session_ids:
            continue
        d = base / uid
        if d.is_dir() and not d.is_symlink():
            for f in _walk_files(d, MD_EXTS, True, maxdepth=3):
                ctx.add_file("artifact", "copilot", "user", f.name, f, extra={"session_id": uid})


def _discover_session_image_dirs(ctx: _Ctx) -> None:
    """Codex generated_images/<id>/ and attachments/<uuid>/, linked by session id."""
    if not ctx.images:
        return
    for tmpl in LAYOUT["codex"]["image_dirs"]:
        base = _resolve(ctx, tmpl)
        if base is None or not base.is_dir():
            ctx.skip("missing")
            continue
        for uid in _listdir(base):
            d = base / uid
            if not d.is_dir() or d.is_symlink():
                continue
            if uid not in ctx.session_ids:
                ctx.skip("unlinked_image")
                continue
            for f in _walk_files(d, tuple(IMAGE_EXTS), True, maxdepth=2):
                ctx.add_file("image", "codex", "user", f.name, f, extra={
                    "mime": IMAGE_EXTS[f.suffix.lower()], "session_id": uid}, max_bytes=MAX_IMAGE_BYTES)


def _discover_grok(ctx: _Ctx) -> None:
    base = ctx.home / ".grok" / "sessions"
    if not base.is_dir():
        ctx.skip("missing")
        return
    want = quote(str(ctx.root), safe="")
    for name in _listdir(base):
        if name != want and unquote(name) != str(ctx.root):
            continue
        for uid in _listdir(base / name):
            imgs = base / name / uid / "images"
            if ctx.images and imgs.is_dir() and not imgs.is_symlink():
                for f in _walk_files(imgs, tuple(IMAGE_EXTS), False):
                    ctx.add_file("image", "grok", "user", f.name, f, extra={
                        "mime": IMAGE_EXTS[f.suffix.lower()], "session_id": uid}, max_bytes=MAX_IMAGE_BYTES)


def _discover_qoder_memory(ctx: _Ctx) -> None:
    _discover_slug_memory(ctx, "qoder", ctx.home / ".qoder")
    mem = ctx.home / ".qoder" / "memory"
    if mem.is_dir() and not mem.is_symlink():
        for f in _walk_files(mem, MD_EXTS, True):
            ctx.add_file("markdown", "qoder", "user", f.name, f)


def _discover_hermes_extra(ctx: _Ctx) -> None:
    home = _resolve(ctx, "{hermes}")
    if home is None:
        return
    prof = home / "profiles"
    for name in _listdir(prof):
        d = prof / name
        if not d.is_dir() or d.is_symlink():
            continue
        _add_skills(ctx, "hermes", "user", d / "skills")
        for rel in ("SOUL.md", "memories/MEMORY.md", "memories/USER.md"):
            f = d / rel
            if f.exists():
                ctx.add_file("markdown", "hermes", "user", f.name, f)


def _discover_vscode_prompts(ctx: _Ctx) -> None:
    # VS Code user prompts; macOS location, then Linux. Unverified elsewhere.
    for rel in ("Library/Application Support/Code/User/prompts", ".config/Code/User/prompts"):
        d = ctx.home / rel
        if d.is_dir():
            for f in _walk_files(d, (".prompt.md", ".md"), False):
                title = f.name[:-len(".prompt.md")] if f.name.endswith(".prompt.md") else f.stem
                if ctx.name_used(title):
                    ctx.add_file("command", "copilot", "user", title, f, key=title)
                else:
                    ctx.skip("unused_user_item")


def _discover_extras(ctx: _Ctx) -> None:
    _discover_claude_json(ctx)
    _discover_slug_memory(ctx, "claude", _resolve(ctx, "{claude}") or ctx.home / ".claude")
    _discover_qoder_memory(ctx)
    _discover_antigravity_brain(ctx)
    _discover_gemini_tmp(ctx)
    _discover_copilot_state(ctx)
    _discover_session_image_dirs(ctx)
    _discover_grok(ctx)
    _discover_hermes_extra(ctx)
    _discover_vscode_prompts(ctx)


# --------------------------------------------------------- project *.md walk

def _gitignored_dirs(root: Path) -> Set[str]:
    out: Set[str] = set()
    gi = root / ".gitignore"
    try:
        if gi.stat().st_size > 256 * 1024:
            return out
        lines = gi.read_text("utf-8", "replace").splitlines()
    except OSError:
        return out
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith(("#", "!")) or any(c in ln for c in "*?[\\"):
            continue
        out.add(ln.strip("/"))
    return out


def _agent_for_md(name: str) -> str:
    return {"CLAUDE.md": "claude", "GEMINI.md": "gemini", "QWEN.md": "qwen"}.get(name, "repo")


def _walk_project_markdown(ctx: _Ctx) -> None:
    root = ctx.root
    if not root.is_dir():
        ctx.skip("missing")
        return
    ignored = _gitignored_dirs(root)
    count = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        keep = []
        for d in sorted(dirnames):
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if rel in SKIP_DIR_PATHS or d == ".worktrees":
                ctx.skip("nested_worktree")
                continue
            if d in SKIP_DIRS or rel in ignored or (d in ignored and "/" not in d):
                continue
            if is_never_index(d):
                ctx.skip("never_index")
                continue
            if (Path(dirpath) / d).is_symlink():
                continue                              # never follow, never leave the root
            keep.append(d)
        dirnames[:] = keep
        for f in sorted(filenames):
            if not f.lower().endswith(MD_EXTS):
                continue
            p = Path(dirpath) / f
            if is_never_index(p):
                ctx.skip("never_index")
                continue
            if p.is_symlink():
                ctx.skip("symlink_outside" if not ctx.inside(p, root) else "symlink")
                continue
            if count >= MAX_PROJECT_MD:
                ctx.skip("md_cap")
                continue
            if ctx.add_file("markdown", _agent_for_md(f), "project", f, p):
                count += 1


# ----------------------------------------------------------------- discover

def discover(project_root: str, sessions_for_project: List[dict], home: Optional[Path] = None,
             env: Any = None, images: bool = True) -> Dict[str, Any]:
    """Discover the project's knowledge documents.

    Returns ``{"documents": [...], "skipped": {reason: count}}``. Project-scope
    items are those under ``project_root``. User-scope skills, commands, agent
    definitions and MCP servers are included only when a session in
    ``sessions_for_project`` used them (``skills_used``, ``mcp_usage``/``mcp_tools``/
    ``tool_counts``, ``delegation``/``subagents``); user instruction and memory
    files are global and always included. Never raises on bad or missing files."""
    home = Path(home) if home is not None else Path.home()
    env = os.environ if env is None else env
    ctx = _Ctx(project_root, sessions_for_project, home, env, images)
    for agent in AGENT_ORDER:
        try:
            _discover_agent(ctx, agent, LAYOUT[agent])
        except Exception:
            ctx.skip("parse_error")
    for fn in (_discover_extras, _walk_project_markdown):
        try:
            fn(ctx)
        except Exception:
            ctx.skip("parse_error")
    if images:
        _project_images(ctx)
    docs = sorted(ctx.docs.values(), key=lambda d: d["doc_id"])
    if not images:
        docs = [d for d in docs if d["type"] != "image"]
    return {"documents": docs, "skipped": dict(sorted(ctx.skipped.items()))}


def _project_images(ctx: _Ctx) -> None:
    # No project-scope image locations are listed by the inventory.
    return


# ---------------------------------------------------------- inline images

INLINE_IMAGE_AGENTS = {"claude", "codex"}


def extract_inline_images(raw_session_events: Iterable[Any]) -> List[Tuple[bytes, str, int]]:
    """Inline base64 image blocks from Claude-style transcript events.

    Handles ``{type: image, source: {type: base64, media_type, data}}`` in
    ``message.content`` (user messages and nested tool_result content). Returns
    ``[(bytes, media_type, turn)]`` where turn is the event's position in the
    input. Anything else (other shapes, bad base64, oversized or non-image
    media) is ignored."""
    out: List[Tuple[bytes, str, int]] = []
    valid = set(IMAGE_EXTS.values())

    def blocks(content: Any, depth: int = 0) -> Iterator[dict]:
        if not isinstance(content, list) or depth > 3:
            return
        for b in content:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "image":
                yield b
            elif b.get("type") == "tool_result":
                yield from blocks(b.get("content"), depth + 1)

    try:
        events = list(raw_session_events or [])
    except TypeError:
        return out
    for turn, ev in enumerate(events):
        if isinstance(ev, str):
            try:
                ev = json.loads(ev)
            except ValueError:
                continue
        if not isinstance(ev, dict):
            continue
        msg = ev.get("message") or ev.get("payload")
        content = msg.get("content") if isinstance(msg, dict) else ev.get("content")
        if ev.get("type") == "response_item" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "input_image":
                    continue
                url = block.get("image_url")
                if isinstance(url, str) and url.startswith("data:"):
                    meta, _, data = url[5:].partition(",")
                    if meta.endswith(";base64"):
                        content = [*content, {"type": "image", "source": {
                            "type": "base64", "media_type": meta[:-7], "data": data}}]
        for b in blocks(content):
            src = b.get("source")
            if not isinstance(src, dict) or src.get("type") != "base64":
                continue
            mt, data = src.get("media_type"), src.get("data")
            if mt not in valid or not isinstance(data, str) or len(data) > MAX_IMAGE_BYTES * 4 // 3 + 8:
                continue
            try:
                raw = base64.b64decode(data, validate=True)
            except (binascii.Error, ValueError):
                continue
            if raw and len(raw) <= MAX_IMAGE_BYTES:
                out.append((raw, mt, turn))
    return out
