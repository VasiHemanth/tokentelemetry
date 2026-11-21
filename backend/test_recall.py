from datetime import datetime, timezone

import pytest

import recall

GH = "gh" + "p_" + "a" * 36


@pytest.fixture(autouse=True)
def _no_repo_resolver(monkeypatch):
    # Importing main (another test may) installs canonical_repo, which walks
    # the real filesystem. These tests cover the pure path fold.
    monkeypatch.setattr(recall, "repo_resolver", None)


def dt(day, hour=0):
    return datetime(2026, 11, day, hour, tzinfo=timezone.utc)


def sess(agent, sid, project, day, **kw):
    s = {"agent": agent, "id": sid, "project": project, "timestamp": dt(day),
         "display": f"prompt {sid}", "model": "m", "tokens": {"total": 100}, "cost": 1.0}
    s.update(kw)
    return s


def chunk(idx, text, kind="assistant", turn=1):
    return {"idx": idx, "turn": turn, "kind": kind, "text": text}


def fake_loader(table, archive=()):
    def load(agent, sid):
        if (agent, sid) not in table:
            return None
        return table[(agent, sid)], ("archive" if (agent, sid) in archive else "live")
    return load


# ------------------------------------------------------------ project key

@pytest.mark.parametrize("path,expected", [
    ("/Users/dev/code/app", "/Users/dev/code/app"),
    ("/Users/dev/code/app/.claude/worktrees/feat-x", "/Users/dev/code/app"),
    ("/Users/dev/code/app/.codex/worktrees/abc", "/Users/dev/code/app"),
    ("/Users/dev/code/app/.worktrees/abc/", "/Users/dev/code/app"),
    ("C:\\Users\\dev\\app\\.claude\\worktrees\\x", "C:/Users/dev/app"),
    ("C:/Users/dev/app/", "C:/Users/dev/app"),
    ("/Users/dev/code/app/.claude/worktrees/feat-x/backend", "/Users/dev/code/app"),
    ("/Users/dev/code/app/.grok/worktrees/abc", "/Users/dev/code/app"),
    ("", None),
    (None, None),
    (recall.UNASSIGNED, None),
])
def test_project_key(path, expected):
    assert recall.project_key(path) == expected


def test_match_project():
    keys = ["/Users/dev/code/education-video", "/Users/dev/code/video-tools"]
    assert recall.match_project(keys, "/Users/dev/code/education-video") == keys[0]
    assert recall.match_project(keys, "Education-Video") == keys[0]
    assert recall.match_project(keys, "tools") == keys[1]
    assert recall.match_project(keys, "video") == keys[0]  # first key wins in a tier
    assert recall.match_project(keys, "nope") is None
    assert recall.match_project(keys, "") is None


# ------------------------------------------------------------ listings

SESSIONS = [
    sess("claude", "a", "/r/edu", 10, cost=2.0, delegated_cost=0.5),
    sess("codex", "b", "/r/edu/.claude/worktrees/w1", 12, cost=None),
    sess("antigravity", "c", recall.UNASSIGNED, 14),
    sess("claude", "d", "/r/other", 11),
]


def test_list_projects():
    out = recall.list_projects(SESSIONS)["projects"]
    assert [p["name"] for p in out] == ["edu", "other"]
    edu = out[0]
    assert edu["key"] == "/r/edu"
    assert edu["agents"] == ["claude", "codex"]
    assert edu["session_count"] == 2
    assert edu["cost"] == 2.5
    assert edu["last_ts"] == "2026-11-12T00:00:00Z"


def test_list_sessions_filters_and_total():
    out = recall.list_sessions(SESSIONS, project="edu", limit=1)
    assert out["project"] == {"key": "/r/edu", "name": "edu"}
    assert out["total"] == 2 and len(out["sessions"]) == 1
    assert out["sessions"][0]["id"] == "b"  # newest first
    assert out["sessions"][0]["project_key"] == "/r/edu"
    assert out["sessions"][0]["source_present"] is True
    assert recall.list_sessions(SESSIONS, agents="codex")["total"] == 1
    assert recall.list_sessions(SESSIONS, since="2026-11-12")["total"] == 2
    none = recall.list_sessions(SESSIONS, project="missing")
    assert none["project"] is None and none["total"] == 0
    # Unassigned sessions only appear with no project filter.
    assert recall.list_sessions(SESSIONS)["total"] == 4
    assert recall.list_sessions(SESSIONS)["sessions"][0]["project_key"] is None


def test_since_validation():
    with pytest.raises(ValueError):
        recall.list_sessions(SESSIONS, since="not a date")


# ------------------------------------------------------------ search

def test_idf_rare_term_beats_common():
    common = [chunk(i, "the build runs fine") for i in range(10)]
    table = {
        ("claude", "a"): common + [chunk(10, "build failed with zebra error")],
        ("claude", "d"): [chunk(0, "build ok build ok")],
    }
    out = recall.search(SESSIONS, fake_loader(table), "build zebra")
    top = out["hits"][0]
    assert "zebra" in top["snippet"]
    assert top["id"] == "a" and top["turn"] == 1 and top["kind"] == "assistant"
    assert top["source"] == "live"
    assert out["hits"][0]["score"] > out["hits"][-1]["score"]


def test_quoted_phrase_required():
    table = {("claude", "a"): [
        chunk(0, "the render pipeline is slow"),
        chunk(1, "pipeline for render of video"),
    ]}
    out = recall.search(SESSIONS, fake_loader(table), '"render pipeline"')
    assert [h["snippet"] for h in out["hits"]] == ["the render pipeline is slow"]
    # Case-insensitive.
    out = recall.search(SESSIONS, fake_loader(table), '"RENDER PIPELINE"')
    assert len(out["hits"]) == 1


def test_by_agent_counts_before_limit_and_coverage():
    table = {
        ("claude", "a"): [chunk(0, "alpha one"), chunk(1, "alpha two")],
        ("codex", "b"): [chunk(0, "alpha three")],
        ("claude", "d"): [chunk(0, "nothing")],
    }
    out = recall.search(SESSIONS, fake_loader(table), "alpha", limit=1)
    assert len(out["hits"]) == 1
    assert out["by_agent"] == {"claude": 2, "codex": 1}
    cov = out["coverage"]
    assert cov == {
        "candidates": 4, "sessions_scanned": 3, "sessions_skipped": 0, "skipped_reason": None,
        "unreadable": 1, "truncated": 0, "timed_out": False,
        "agents_scanned": ["claude", "codex"],
        "semantic": {"mode": "keyword"},
    }


def test_max_sessions_newest_first_and_reason():
    table = {("antigravity", "c"): [chunk(0, "alpha")], ("codex", "b"): [chunk(0, "alpha")],
             ("claude", "d"): [chunk(0, "alpha")], ("claude", "a"): [chunk(0, "alpha")]}
    out = recall.search(SESSIONS, fake_loader(table), "alpha", max_sessions=2)
    assert {h["id"] for h in out["hits"]} == {"c", "b"}
    cov = out["coverage"]
    assert cov["candidates"] == 4 and cov["sessions_scanned"] == 2
    assert cov["sessions_skipped"] == 2 and cov["skipped_reason"] == "max_sessions"


def test_timeout_budget():
    ticks = iter([0, 0, 5, 50, 50, 50, 50])
    table = {k: [chunk(0, "alpha")] for k in [("antigravity", "c"), ("codex", "b"), ("claude", "d"), ("claude", "a")]}
    out = recall.search(SESSIONS, fake_loader(table), "alpha", budget_s=20, clock=lambda: next(ticks))
    cov = out["coverage"]
    assert cov["timed_out"] is True and cov["skipped_reason"] == "timeout"
    assert cov["sessions_scanned"] == 2 and cov["sessions_skipped"] == 2


def test_truncation_keeps_last_chunks(monkeypatch):
    monkeypatch.setattr(recall, "MAX_CHUNKS_PER_SESSION", 5)
    chunks = [chunk(i, "alpha" if i in (0, 9) else "filler") for i in range(10)]
    out = recall.search(SESSIONS, fake_loader({("claude", "a"): chunks}), "alpha", project="edu")
    assert out["coverage"]["truncated"] == 1
    assert [h["turn"] for h in out["hits"]] == [1]  # only idx 9 survives
    assert len(out["hits"]) == 1


def test_archive_source_tag():
    table = {("claude", "a"): [chunk(0, "alpha")]}
    out = recall.search(SESSIONS, fake_loader(table, archive={("claude", "a")}), "alpha")
    assert out["hits"][0]["source"] == "archive"


def test_redaction_in_snippet_and_title():
    table = {("claude", "a"): [
        chunk(0, f"use {GH} for auth", kind="user"),
        chunk(1, f"the token {GH} was reused"),
    ]}
    out = recall.search(SESSIONS, fake_loader(table), "auth reused")
    blob = repr(out)
    assert GH not in blob
    assert "[REDACTED:github_token]" in out["hits"][0]["snippet"]
    assert out["hits"][0]["title"].startswith("use [REDACTED:github_token]")


def test_title_and_snippet_limits():
    long = "alpha " + "word " * 400
    table = {("claude", "a"): [chunk(0, "  first\n\nprompt  " + "x" * 300, kind="user"), chunk(1, long)]}
    out = recall.search(SESSIONS, fake_loader(table), "alpha")
    h = out["hits"][0]
    assert len(h["snippet"]) <= 600
    assert h["title"].startswith("first prompt x") and len(h["title"]) == 160


def test_loader_exception_counts_unreadable():
    def boom(agent, sid):
        raise RuntimeError("x")
    out = recall.search(SESSIONS, boom, "alpha")
    assert out["coverage"]["unreadable"] == 4 and out["hits"] == []


def test_empty_query_terms():
    with pytest.raises(ValueError):
        recall.search(SESSIONS, fake_loader({}), "the and of")


# ------------------------------------------------------------ read_session

def test_read_session_paging_and_kinds():
    chunks = [chunk(i, f"t{i} {GH}" if i == 0 else f"t{i}", kind="user" if i % 2 == 0 else "tool") for i in range(7)]
    meta = SESSIONS[0]
    p1 = recall.read_session(meta, chunks, "live", "claude", "a", offset=0, limit=3)
    assert [c["idx"] for c in p1["chunks"]] == [0, 1, 2]
    assert p1["next_offset"] == 3 and p1["total_chunks"] == 7
    assert GH not in repr(p1) and "[REDACTED:github_token]" in p1["chunks"][0]["text"]
    p2 = recall.read_session(meta, chunks, "live", "claude", "a", offset=p1["next_offset"], limit=10)
    assert [c["idx"] for c in p2["chunks"]] == [3, 4, 5, 6] and p2["next_offset"] is None
    users = recall.read_session(meta, chunks, "live", "claude", "a", kinds="user", limit=2)
    assert [c["idx"] for c in users["chunks"]] == [0, 2] and users["next_offset"] == 4
    assert users["project"] == "edu" and users["source"] == "live"
    with pytest.raises(ValueError):
        recall.read_session(meta, chunks, "live", "claude", "a", kinds="bogus")


# ------------------------------------------------------------ route smoke
# httpx (needed by TestClient) is not a dev dependency, so the route
# functions are awaited directly; FastAPI only adds routing on top.

def test_http_routes(monkeypatch):
    import asyncio
    from fastapi import HTTPException
    import main

    async def fake_sessions(fresh=False):
        return SESSIONS

    table = {("claude", "a"): [chunk(0, "render pipeline notes", kind="user"), chunk(1, "alpha")]}
    monkeypatch.setattr(main, "get_sessions_cached", fake_sessions)
    monkeypatch.setattr(main, "_recall_load_chunks", fake_loader(table))
    run = asyncio.run

    assert run(main.recall_projects())["projects"][0]["name"] == "edu"
    assert run(main.recall_sessions(project="edu", agent="claude"))["total"] == 1

    j = run(main.recall_search(q="render", project="edu"))
    assert j["hits"][0]["id"] == "a"
    assert j["coverage"]["candidates"] == 2 and j["coverage"]["unreadable"] == 1

    def status(coro):
        with pytest.raises(HTTPException) as e:
            run(coro)
        return e.value.status_code

    assert status(main.recall_search()) == 400
    assert status(main.recall_search(q="x", limit="999")) == 400
    assert status(main.recall_sessions(since="garbage")) == 400

    r = run(main.recall_session("claude", "a", limit="1"))
    assert r["next_offset"] == 1
    assert status(main.recall_session("claude", "zzz")) == 404


# ------------------------------------------------------------ review fixes

def test_repo_resolver_folds_like_projects(monkeypatch):
    monkeypatch.setattr(recall, "repo_resolver", lambda p: "/Users/dev/code/app" if "sibling-wt" in p else p)
    assert recall.project_key("/Users/dev/code/sibling-wt") == "/Users/dev/code/app"
    monkeypatch.setattr(recall, "repo_resolver", lambda p: (_ for _ in ()).throw(OSError("boom")))
    assert recall.project_key("/Users/dev/code/app") == "/Users/dev/code/app"


def _pem_chunks():
    begin = "-----BEGIN RSA PRIV" + "ATE KEY-----"
    end = "-----END RSA PRIV" + "ATE KEY-----"
    body = "MIIEow" + "Q" * 590
    return [
        chunk(0, "here is the key " + begin + "\n" + body[:300]),
        chunk(1, body),
        chunk(2, body[:100] + end + " and then render pipeline notes"),
        chunk(3, "plain text after the key"),
    ]


def test_private_key_body_masked_across_chunks():
    chunks = _pem_chunks()
    masked = recall.mask_key_continuations(chunks)
    assert masked[1] == "[REDACTED:private_key]"
    assert masked[2].startswith("[REDACTED:private_key]") and "render pipeline" in masked[2]
    assert 3 not in masked
    page = recall.read_session(None, chunks, "live", "claude", "s1")
    joined = " ".join(c["text"] for c in page["chunks"])
    assert "QQQQQQQQ" not in joined and "MIIEow" not in joined


def test_private_key_body_not_in_search_snippet():
    sessions = [sess("claude", "s1", "/Users/dev/code/app", 1)]
    chunks = _pem_chunks()
    chunks[1] = chunk(1, "render " + "Q" * 500)
    res = recall.search(sessions, fake_loader({("claude", "s1"): chunks}), "render")
    assert res["hits"]
    assert all("QQQQ" not in h["snippet"] for h in res["hits"])


def test_phrase_matches_across_line_wrap():
    sessions = [sess("claude", "s1", "/Users/dev/code/app", 1)]
    loader = fake_loader({("claude", "s1"): [chunk(0, "the render\n  pipeline is slow")]})
    res = recall.search(sessions, loader, '"render pipeline"')
    assert len(res["hits"]) == 1


def test_budget_checked_inside_a_large_session():
    sessions = [sess("claude", "s1", "/Users/dev/code/app", 2), sess("codex", "s2", "/Users/dev/code/app", 1)]
    big = [chunk(i, f"word{i} alpha") for i in range(5000)]
    ticks = iter(range(0, 10**6))
    res = recall.search(
        sessions, fake_loader({("claude", "s1"): big, ("codex", "s2"): [chunk(0, "alpha")]}),
        "alpha", budget_s=1.0, clock=lambda: next(ticks))
    assert res["coverage"]["timed_out"] is True
    assert res["coverage"]["sessions_scanned"] == 1


def test_codex_rollout_records_become_chunks():
    import summaries
    events = [
        {"type": "session_meta", "payload": {"cwd": "/Users/dev/code/app"}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /x"}]}},
        {"type": "response_item", "payload": {"type": "message", "role": "user",
                                              "content": [{"type": "input_text", "text": "set up the render pipeline"}]}},
        {"type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "use remotion"}]}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                              "arguments": "{\"cmd\": \"ls remotion/src\"}"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "output": "remotion/src/Root.tsx"}},
        {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                              "content": [{"type": "input_text", "text": "sandbox rules"}]}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "mirror"}},
    ]
    chunks = summaries.build_chunks(recall.codex_to_message_events(events))
    kinds = [c["kind"] for c in chunks]
    assert kinds == ["user", "assistant", "tool", "result"]
    assert "remotion" in chunks[3]["text"]
    assert not any("sandbox rules" in c["text"] or "mirror" in c["text"] for c in chunks)


def test_recall_indexes_tool_output_past_first_line():
    import summaries
    ev = [{"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "content": "pipeline.js\nremotion/src/Root.tsx"}]}}]
    assert not any("Root.tsx" in c["text"] for c in summaries.build_chunks(ev))
    assert any("Root.tsx" in c["text"] for c in summaries.build_chunks(ev, result_chars=recall.RESULT_CHARS))


# ------------------------------------------------------------ v2: modes

class FakeSem:
    """Semantic bundle with canned ranking. ``current`` is the set of sessions
    whose stored fingerprint matches."""

    def __init__(self, ranking, current):
        self.ranking = ranking
        self.current = set(current)
        self.fingerprints = {}
        self.allowed_seen = None

    def bundle(self):
        def is_current(agent, sid, fp):
            self.fingerprints[(agent, sid)] = fp
            return (agent, sid) in self.current

        def rank(q, allowed):
            self.allowed_seen = set(allowed)
            return [r for r in self.ranking if (r[0], r[1]) in allowed]
        return recall.Semantic(model="fake", is_current=is_current, rank=rank)


V2_TABLE = {
    ("claude", "a"): [chunk(0, "alpha alpha alpha"), chunk(1, "paraphrase of the topic"), chunk(2, "alpha once")],
    ("codex", "b"): [chunk(0, "alpha twice alpha"), chunk(1, "unrelated words")],
}
V2_SESS = [sess("claude", "a", "/r/app", 10), sess("codex", "b", "/r/app", 12)]


def test_mode_validation_and_disabled():
    with pytest.raises(ValueError, match="mode"):
        recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="fuzzy")
    with pytest.raises(ValueError, match="not enabled"):
        recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="hybrid")


def test_keyword_mode_unchanged_and_tagged():
    out = recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha")
    assert all(h["match"] == "keyword" for h in out["hits"])
    assert out["coverage"]["semantic"] == {"mode": "keyword"}


def test_semantic_mode_ranks_by_cosine_and_finds_paraphrase():
    sem = FakeSem([("claude", "a", 1, 0.91234567), ("codex", "b", 1, 0.5)], [("claude", "a"), ("codex", "b")])
    out = recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="semantic", semantic=sem.bundle())
    assert [(h["id"], h["turn"], h["score"], h["match"]) for h in out["hits"]] == [
        ("a", 1, 0.9123, "semantic"), ("b", 1, 0.5, "semantic")]
    assert out["hits"][0]["snippet"] == "paraphrase of the topic"
    assert out["coverage"]["semantic"] == {"mode": "semantic", "model": "fake",
                                           "indexed_sessions": 2, "unindexed_sessions": 0}


def test_hybrid_rrf_order_and_match_tags():
    kw = recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha")["hits"]
    assert len(kw) == 3
    kw_rank = {h["snippet"]: i for i, h in enumerate(kw, 1)}
    sem = FakeSem([("claude", "a", 1, 0.9), ("claude", "a", 0, 0.8)], [("claude", "a"), ("codex", "b")])
    out = recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="hybrid", semantic=sem.bundle(), limit=10)
    hits = {h["snippet"]: h for h in out["hits"]}
    only_sem = hits["paraphrase of the topic"]
    assert only_sem["match"] == "semantic" and only_sem["score"] == round(1 / 61, 4)
    both = hits["alpha alpha alpha"]
    assert both["match"] == "both"
    assert both["score"] == round(1 / (60 + kw_rank["alpha alpha alpha"]) + 1 / 62, 4)
    for snip, h in hits.items():
        if h["match"] == "keyword":
            assert h["score"] == round(1 / (60 + kw_rank[snip]), 4)
    scores = [h["score"] for h in out["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert out["by_agent"] == {"claude": 3, "codex": 1} or sum(out["by_agent"].values()) == len(out["hits"])


def test_hybrid_falls_back_to_keyword_when_unindexed():
    sem = FakeSem([("claude", "a", 1, 0.9)], [])
    out = recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="hybrid", semantic=sem.bundle())
    assert out["coverage"]["semantic"] == {"mode": "hybrid", "model": "fake",
                                           "indexed_sessions": 0, "unindexed_sessions": 2}
    assert out["hits"] and all(h["match"] == "keyword" for h in out["hits"])
    assert sem.allowed_seen is None  # nothing to rank, so rank() is not called


def test_semantic_only_candidates_are_the_current_sessions():
    sem = FakeSem([("claude", "a", 1, 0.9), ("codex", "b", 1, 0.8)], [("codex", "b")])
    out = recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="semantic", semantic=sem.bundle())
    assert sem.allowed_seen == {("codex", "b")}
    assert [h["id"] for h in out["hits"]] == ["b"]
    assert out["coverage"]["semantic"]["unindexed_sessions"] == 1


def test_semantic_hit_text_is_redacted_and_idx_must_exist():
    table = {("claude", "a"): [chunk(0, f"leaked {GH} token"), chunk(1, "ok")]}
    sem = FakeSem([("claude", "a", 0, 0.9), ("claude", "a", 99, 0.8)], [("claude", "a")])
    out = recall.search([sess("claude", "a", "/r/app", 10)], fake_loader(table), "token", mode="semantic",
                        semantic=sem.bundle())
    assert len(out["hits"]) == 1  # stale idx 99 dropped
    assert GH not in out["hits"][0]["snippet"] and "REDACTED" in out["hits"][0]["snippet"]


def test_fingerprint_passed_to_bundle_matches_session_fingerprint():
    sem = FakeSem([], [("codex", "b")])
    recall.search(V2_SESS, fake_loader(V2_TABLE), "alpha", mode="hybrid", semantic=sem.bundle())
    assert sem.fingerprints[("codex", "b")] == recall.session_fingerprint(V2_TABLE[("codex", "b")])


def test_hybrid_falls_back_to_keyword_when_embedding_fails():
    sessions = [sess("claude", "s1", "/Users/dev/code/app", 1)]
    loader = fake_loader({("claude", "s1"): [chunk(0, "render pipeline notes")]})

    def boom(q, allowed):
        raise RuntimeError("Ollama is not reachable at 127.0.0.1:11434")

    sem = recall.Semantic(model="m", is_current=lambda a, i, f: True, rank=boom)
    res = recall.search(sessions, loader, "render", mode="hybrid", semantic=sem)
    assert [h["match"] for h in res["hits"]] == ["keyword"]
    assert "not reachable" in res["coverage"]["semantic"]["error"]
