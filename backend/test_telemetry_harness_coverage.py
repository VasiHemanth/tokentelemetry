"""Guardrails that keep telemetry honest as new coding harnesses are added.

`test_telemetry_redaction.py` proves a payload can't carry content. These tests
prove something different and equally load-bearing: that the four places which
have to agree about the harness list actually do, and that a value we decide to
send survives all the way to the sink instead of being dropped en route.

Every one of these covers a failure that has already happened or came within one
commit of happening:

* the `agents` context field was 117 of its 120 characters, so the next harness
  would have truncated it *mid-name* — turning "smallcode" into "small" and
  inventing an agent that does not exist;
* the Cloudflare Worker keeps its own copy of the event allowlist, so a new
  backend event is accepted by the app, POSTed, answered 204 and then silently
  never written to the dataset;
* the Settings "exactly what we send" panel is the product's privacy promise, so
  an event missing from it is an inaccurate disclosure, not a cosmetic gap.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import telemetry

REPO = Path(__file__).resolve().parent.parent
WORKER = REPO / "proxy" / "cloudflare-worker.js"
WORKER_SRC = REPO / "proxy" / "cloudflare" / "src" / "index.js"


# --- the harness list, in all the places that must agree -------------------

def test_known_agents_matches_the_panel_builders():
    """telemetry's allowlist and the harness-panel registry are the same set.

    The comment on _KNOWN_AGENTS has always *claimed* this; nothing enforced it.
    An agent missing here is not a crash — it is quietly bucketed as
    "other-agent", so the new harness looks like it has no users at all.
    """
    from harness_panels import BUILDERS
    assert telemetry._KNOWN_AGENTS == set(BUILDERS), (
        "telemetry._KNOWN_AGENTS and harness_panels.BUILDERS disagree; "
        "missing from telemetry: %s; missing from BUILDERS: %s"
        % (sorted(set(BUILDERS) - telemetry._KNOWN_AGENTS),
           sorted(telemetry._KNOWN_AGENTS - set(BUILDERS)))
    )


def test_agents_field_holds_every_agent_without_truncating():
    """The whole recognised set, plus the "other-agent" bucket, must fit.

    This is the test that makes adding a harness fail here rather than silently
    corrupting the field in production.
    """
    names = sorted(telemetry._KNOWN_AGENTS | {"other-agent"})
    joined = ",".join(names)
    assert len(joined) <= telemetry._AGENTS_FIELD_MAX, (
        "the agents field would truncate: %d chars vs cap %d. Raise "
        "_AGENTS_FIELD_MAX *and* the matching blob() cap in the Cloudflare "
        "worker, which re-caps independently." % (len(joined), telemetry._AGENTS_FIELD_MAX)
    )
    assert telemetry._join_capped(names) == joined


def test_join_capped_never_emits_a_partial_agent_name():
    """Below the cap it drops whole names; it never cuts one in half.

    The plain `",".join(...)[:120]` this replaced ended the string on "small",
    which reads downstream as a real agent named "small".
    """
    names = sorted(telemetry._KNOWN_AGENTS | {"other-agent"})
    for limit in range(1, len(",".join(names)) + 8):
        out = telemetry._join_capped(names, limit)
        assert len(out) <= limit
        if out:
            assert all(tok in names for tok in out.split(",")), (
                "limit=%d produced a partial name: %r" % (limit, out))


def test_agent_enum_cannot_leak_a_custom_harness_name():
    props = telemetry._sanitize_props(
        "harness.scanned", {"agent": "my-employers-internal-agent", "volume": "1-9"})
    assert props["agent"] == "other"
    props = telemetry._sanitize_props("page.viewed", {"route": "agent-panel", "agent": "qoder"})
    assert props == {"route": "agent-panel", "agent": "qoder"}


def test_volume_is_bucketed_and_never_a_raw_count():
    assert telemetry.volume_bucket(0) == "0"
    assert telemetry.volume_bucket(7) == "1-9"
    assert telemetry.volume_bucket(42) == "10-99"
    assert telemetry.volume_bucket(500) == "100-999"
    assert telemetry.volume_bucket(9_999_999) == "1000-plus"
    # Whatever the count, the emitted value is always one of the enum members —
    # a raw session count can never ride through.
    allowed = telemetry._ENUMS["volume"]
    for n in (0, 1, 9, 10, 99, 100, 999, 1000, 12345, 10**9):
        assert telemetry.volume_bucket(n) in allowed


# --- the sink has its own allowlist ----------------------------------------

def _worker_allowed_events() -> set:
    src = WORKER.read_text(encoding="utf-8")
    block = re.search(r"const ALLOWED_EVENTS = new Set\(\[(.*?)\]\)", src, re.S)
    assert block, "could not find ALLOWED_EVENTS in the worker"
    return set(re.findall(r'"([^"]+)"', block.group(1)))


def test_worker_accepts_every_event_the_app_sends():
    """An event the sink does not know is dropped, not stored.

    The Worker answers 204 either way and the app fire-and-forgets, so this
    failure is completely invisible at runtime: the event looks sent, and the
    dataset simply never gains a row.
    """
    missing = set(telemetry._EVENT_PROPS) - _worker_allowed_events()
    assert not missing, (
        "these events would be silently discarded by the Cloudflare worker: %s "
        "— add them to ALLOWED_EVENTS in proxy/cloudflare-worker.js and "
        "proxy/cloudflare/src/index.js" % sorted(missing))


def test_worker_does_not_allow_events_the_app_never_sends():
    """Keeps the sink's allowlist from accumulating names nothing emits."""
    extra = _worker_allowed_events() - set(telemetry._EVENT_PROPS)
    assert not extra, "worker allows events the app never sends: %s" % sorted(extra)


def test_worker_agents_cap_matches_the_backend():
    """The Worker re-caps `agents` independently; a stale cap there silently
    undoes the backend fix at the edge."""
    src = WORKER.read_text(encoding="utf-8")
    m = re.search(r"blob\(p\.agents,\s*(\d+)\)", src)
    assert m, "could not find the agents blob cap in the worker"
    assert int(m.group(1)) >= telemetry._AGENTS_FIELD_MAX, (
        "worker caps agents at %s but the backend allows %d"
        % (m.group(1), telemetry._AGENTS_FIELD_MAX))


def test_worker_copies_stay_byte_identical():
    """proxy/cloudflare-worker.js is a reference copy of the deployed entry
    point. They are meant to be the same file; drift means one of them is a lie
    about what is running."""
    a = hashlib.sha256(WORKER.read_bytes()).hexdigest()
    b = hashlib.sha256(WORKER_SRC.read_bytes()).hexdigest()
    assert a == b, "proxy/cloudflare-worker.js and proxy/cloudflare/src/index.js differ"


def test_worker_blob_positions_are_append_only():
    """Blob indices are the dataset schema every saved query reads by position.

    Renumbering silently re-labels historical rows, so the ordering is asserted
    rather than trusted. Append new fields at the end and extend this list.
    """
    src = WORKER.read_text(encoding="utf-8")
    order = re.findall(r"//\s*blob(\d+)", src)
    assert [int(n) for n in order] == list(range(1, len(order) + 1)), (
        "blob comments are not a contiguous 1..N sequence: %s" % order)
    expected_tail = ["blob17", "blob18"]
    assert ["blob" + n for n in order[-2:]] == expected_tail


# --- the disclosure surface -------------------------------------------------

def test_every_event_appears_in_the_settings_disclosure():
    """The Settings panel renders `event_catalog`; an event absent from it is an
    inaccurate privacy disclosure."""
    catalog = telemetry.event_catalog()
    assert {row["event"] for row in catalog} == set(telemetry._EVENT_PROPS)
    for row in catalog:
        assert {p["name"] for p in row["props"]} == telemetry._EVENT_PROPS[row["event"]]


def test_disclosure_lists_the_real_permitted_values():
    """Each enum-controlled prop shows its actual closed set, so the panel can't
    describe a narrower set than the sanitizer will accept."""
    for row in telemetry.event_catalog():
        for prop in row["props"]:
            if prop["name"] in telemetry._ENUMS:
                assert prop["values"] == sorted(telemetry._ENUMS[prop["name"]])
            else:
                assert prop["values"] is None


def test_always_sent_covers_every_context_and_system_prop():
    rows = telemetry.always_sent()
    named = {(r["scope"], r["name"]) for r in rows}
    expected = {("context", k) for k in telemetry._context_props()}
    expected |= {("system", k) for k in telemetry._system_props()}
    assert named == expected


def test_preview_is_json_serialisable():
    """It is returned straight over HTTP to the Settings panel."""
    json.dumps(telemetry.preview())


def test_declared_events_are_actually_emitted_somewhere():
    """No event may be declared, disclosed to users, and then never sent.

    `retention.opted_in` shipped in exactly that state: it appeared in the
    Settings panel's sample payloads for months with no emitter anywhere, so the
    transparency surface advertised something the app never did.
    """
    sources = [(REPO / "backend" / "main.py").read_text(encoding="utf-8")]
    ts = REPO / "frontend" / "src" / "lib" / "telemetry.ts"
    sources.append(ts.read_text(encoding="utf-8"))
    blob = "\n".join(sources)
    # Events the frontend raises go through the bridge allowlist rather than a
    # literal emit() call, so accept either spelling.
    for event in telemetry._EVENT_PROPS:
        assert '"%s"' % event in blob, (
            "%s is declared and disclosed but nothing emits it" % event)
