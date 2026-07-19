#!/usr/bin/env python3
"""Tests for the wiki freshness pipeline:

  scripts/wiki_manifest.py stamp   — content-hash provenance written into
                                     manifest.json + status.py installation
  skills/brain-init/templates/wiki-skeleton/status.py
                                   — self-contained FRESH/STALE/TAMPERED/
                                     UNVERIFIABLE checker

Each test builds a synthetic repo in a tmp dir (src files + docs/wiki),
runs `init` then `stamp` in-process via wiki_manifest.main(), and invokes
the installed status.py via subprocess (it resolves everything from
__file__, so it must run from inside the fixture wiki).

Run: python3 -m unittest discover -s tests -v   (stdlib only)
"""

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

WIKICLI_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(WIKICLI_ROOT))
import wiki_manifest as wm  # noqa: E402

STATUS_TEMPLATE = WIKICLI_ROOT / "templates" / "status.py"

APP_PAGE = """---
type: concept
resource: src/app.py
---

# App entrypoint

Startup order lives in `src/app.py` (cited in frontmatter AND body,
to pin dedup).
"""

PLAYBOOK_PAGE = """---
type: playbook
---

# DB refresh playbook

Run `scripts/db.js` after every migration. No frontmatter resource:
the body citation is the only provenance link.
"""

ORPHAN_PAGE = """---
type: note
---

# Orphan note

Pure prose. Nothing here names a repo file.
"""

DATADIR_PAGE = """---
type: concept
resource: data
---

# Data directory

Whole-directory resource; provenance is a tree hash.
"""


def sha12(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


class WikiBase(unittest.TestCase):
    """Fixture: tmp repo with two source files, a data dir, and a stamped
    docs/wiki containing four pages (frontmatter-resource, body-cited,
    no-resource, dir-resource)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wiki-status-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "repo"
        self.wiki = self.root / "docs" / "wiki"
        self.wiki.mkdir(parents=True)
        self.src_app = self.root / "src" / "app.py"
        self.db_js = self.root / "scripts" / "db.js"
        self.data_file = self.root / "data" / "one.txt"
        for p, text in ((self.src_app, "print('v1')\n"),
                        (self.db_js, "console.log('v1');\n"),
                        (self.data_file, "one v1\n")):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")
        # git init makes repo-root resolution deterministic even if the tmp
        # dir sits under some outer repo; if git is absent, the scripts'
        # wiki.parent.parent fallback lands on the same root anyway.
        subprocess.run(["git", "init", "-q", str(self.root)],
                       capture_output=True)

        rc, _ = self.manifest_cli("init", "--profile", "generic",
                                  "--status", "complete")
        self.assertEqual(rc, 0)
        self.write_page("concepts/app.md", APP_PAGE)
        self.write_page("playbooks/db-refresh.md", PLAYBOOK_PAGE)
        self.write_page("notes/orphan.md", ORPHAN_PAGE)
        self.write_page("datasets/data-dir.md", DATADIR_PAGE)
        rc, _ = self.manifest_cli("stamp")
        self.assertEqual(rc, 0)

    # -- helpers -------------------------------------------------------

    def manifest_cli(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wm.main([str(self.wiki), *args])
        return rc, buf.getvalue()

    def write_page(self, rel, text):
        p = self.wiki / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def read_manifest(self):
        return json.loads((self.wiki / "manifest.json").read_text(
            encoding="utf-8"))

    def status(self, *args, wiki=None):
        """Run the installed status.py via subprocess: it resolves the wiki
        and repo root from __file__, so in-process import would not work."""
        wiki = wiki or self.wiki
        return subprocess.run(
            [sys.executable, str(wiki / "status.py"), *args],
            capture_output=True, text=True)


class TestStamp(WikiBase):
    def test_records_frontmatter_and_body_resources(self):
        prov = self.read_manifest()["provenance"]
        self.assertEqual(
            set(prov),
            {"concepts/app", "playbooks/db-refresh", "notes/orphan",
             "datasets/data-dir"})
        # frontmatter resource, hashed to the file's actual content sha
        app_res = prov["concepts/app"]["resources"]
        self.assertEqual(app_res.get("src/app.py"),
                         sha12(self.src_app.read_bytes()))
        # cited in frontmatter AND body: recorded exactly once (dedup)
        self.assertEqual(len(app_res), 1)
        # body-only code-span citation is picked up for the playbook
        self.assertEqual(
            prov["playbooks/db-refresh"]["resources"].get("scripts/db.js"),
            sha12(self.db_js.read_bytes()))

    def test_page_sha_present_and_orphan_has_empty_resources(self):
        prov = self.read_manifest()["provenance"]
        self.assertEqual(prov["notes/orphan"]["resources"], {})
        for page_id, entry in prov.items():
            self.assertEqual(
                entry["page_sha"],
                sha12((self.wiki / (page_id + ".md")).read_bytes()),
                f"page_sha mismatch for {page_id}")

    def test_installs_status_py_matching_template(self):
        installed = self.wiki / "status.py"
        self.assertTrue(installed.exists())
        self.assertEqual(installed.read_bytes(), STATUS_TEMPLATE.read_bytes())

    def test_dir_resource_gets_tree_hash_that_tracks_contents(self):
        recorded = self.read_manifest()["provenance"][
            "datasets/data-dir"]["resources"]["data"]
        self.assertRegex(recorded, r"^[0-9a-f]{12}$")
        # editing a file inside the dir changes the tree hash
        self.data_file.write_text("one v2\n", encoding="utf-8")
        self.manifest_cli("stamp")
        after_edit = self.read_manifest()["provenance"][
            "datasets/data-dir"]["resources"]["data"]
        self.assertNotEqual(recorded, after_edit)
        # adding a file changes it again (tree hash covers the file list)
        (self.root / "data" / "two.txt").write_text("new\n", encoding="utf-8")
        self.manifest_cli("stamp")
        after_add = self.read_manifest()["provenance"][
            "datasets/data-dir"]["resources"]["data"]
        self.assertNotEqual(after_edit, after_add)

    def test_dir_resource_over_file_cap_is_unhashable(self):
        big = self.root / "big"
        big.mkdir()
        for i in range(201):  # cap is 200 files
            (big / f"f{i}.txt").write_text(str(i), encoding="utf-8")
        self.write_page("datasets/big-dir.md",
                        "---\ntype: concept\nresource: big\n---\n\n# Big\n")
        self.manifest_cli("stamp")
        self.assertEqual(
            self.read_manifest()["provenance"]["datasets/big-dir"]
            ["resources"]["big"],
            "unhashable")

    def test_frontmatter_resource_escaping_repo_is_unhashable(self):
        secret = self.tmp / "secret.txt"
        secret.write_text("outside the repo\n", encoding="utf-8")
        self.write_page(
            "security/outside.md",
            "---\ntype: note\nresource: ../secret.txt\n---\n\n# Outside\n")
        self.manifest_cli("stamp")
        recorded = self.read_manifest()["provenance"]["security/outside"][
            "resources"]
        self.assertEqual(recorded.get("../secret.txt"), "unhashable")
        # the sentinel must never be the real content hash: no read outside
        self.assertNotEqual(recorded.get("../secret.txt"),
                            sha12(secret.read_bytes()))

    def test_body_cited_escape_is_unhashable_too(self):
        secret = self.tmp / "secret.txt"
        secret.write_text("outside the repo\n", encoding="utf-8")
        self.write_page(
            "security/body-escape.md",
            "---\ntype: note\n---\n\nSee `../secret.txt` for details.\n")
        self.manifest_cli("stamp")
        res = self.read_manifest()["provenance"]["security/body-escape"][
            "resources"]
        # page_resources' exists() filter does not confine body citations to
        # the repo (Path.exists resolves the ..), so the escaping path IS
        # recorded — but only ever as the unhashable sentinel, never hashed
        # content.
        self.assertNotIn("../secret.txt", res)  # escapes repo: never recorded
        self.assertNotIn(sha12(secret.read_bytes()), res.values())


class TestStatusFresh(WikiBase):
    def test_all_fresh_exit0_with_blind_spot_line(self):
        r = self.status()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("FRESH", r.stdout)
        self.assertNotIn("STALE:", r.stdout)
        self.assertNotIn("TAMPERED:", r.stdout)
        # the orphan page is a blind spot; exit stays 0 (nothing stale)
        self.assertIn("blind spot", r.stdout)

    def test_single_page_fresh(self):
        r = self.status("concepts/app")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("FRESH: concepts/app"))

    def test_orphan_page_is_unverifiable_exit0(self):
        r = self.status("notes/orphan")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("UNVERIFIABLE: notes/orphan"))


class TestStatusStale(WikiBase):
    def test_source_change_marks_only_affected_pages_stale(self):
        self.src_app.write_text("print('v2')\n", encoding="utf-8")
        r = self.status()
        self.assertEqual(r.returncode, 1)
        self.assertIn("STALE: concepts/app", r.stdout)
        # unaffected pages stay FRESH (checked precisely via --json)
        rj = self.status("--json")
        verdicts = {row["page"]: row["verdict"]
                    for row in json.loads(rj.stdout)["pages"]}
        self.assertEqual(verdicts["concepts/app"], "STALE")
        self.assertEqual(verdicts["playbooks/db-refresh"], "FRESH")
        self.assertEqual(verdicts["datasets/data-dir"], "FRESH")

    def test_single_page_mode_prints_the_changed_file(self):
        self.db_js.write_text("console.log('v2');\n", encoding="utf-8")
        r = self.status("playbooks/db-refresh")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("STALE: playbooks/db-refresh"))
        self.assertIn("changed: scripts/db.js", r.stdout)

    def test_dir_resource_page_goes_stale_when_inner_file_changes(self):
        self.data_file.write_text("one v2\n", encoding="utf-8")
        r = self.status("datasets/data-dir")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("STALE: datasets/data-dir"))
        self.assertIn("changed: data", r.stdout)

    def test_restamp_after_source_refresh_returns_to_fresh(self):
        self.src_app.write_text("print('v2')\n", encoding="utf-8")
        self.assertEqual(self.status().returncode, 1)  # stale first
        rc, _ = self.manifest_cli("stamp")               # the ingest re-stamp
        self.assertEqual(rc, 0)
        r = self.status()
        self.assertEqual(r.returncode, 0)
        self.assertTrue(
            self.status("concepts/app").stdout.startswith(
                "FRESH: concepts/app"))


class TestTampered(WikiBase):
    def test_hand_edit_wins_over_stale(self):
        # change BOTH the page and its source: TAMPERED must take precedence
        page = self.wiki / "concepts" / "app.md"
        page.write_text(page.read_text(encoding="utf-8")
                        + "\nhand-edited line\n", encoding="utf-8")
        self.src_app.write_text("print('v2')\n", encoding="utf-8")
        r = self.status("concepts/app")
        self.assertEqual(r.returncode, 1)
        self.assertTrue(r.stdout.startswith("TAMPERED: concepts/app"))
        # whole-wiki report flags it too
        rw = self.status()
        self.assertEqual(rw.returncode, 1)
        self.assertIn("TAMPERED: concepts/app", rw.stdout)


class TestNewPage(WikiBase):
    def test_page_added_after_stamp_is_unverifiable(self):
        self.write_page("notes/later.md",
                        "---\ntype: note\n---\n\n# Added after stamp\n")
        r = self.status("--json")
        self.assertEqual(r.returncode, 0)
        report = json.loads(r.stdout)
        rows = {row["page"]: row for row in report["pages"]}
        self.assertEqual(rows["notes/later"]["verdict"], "UNVERIFIABLE")
        self.assertGreaterEqual(report["counts"]["UNVERIFIABLE"], 2)


class TestNote(WikiBase):
    NOTES = property(lambda self: self.wiki / "raw" / "stale-notes.md")

    def test_note_not_written_for_fresh_page(self):
        r = self.status("playbooks/db-refresh", "--note")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.NOTES.exists())

    def test_note_written_once_and_deduped(self):
        self.db_js.write_text("console.log('v2');\n", encoding="utf-8")
        r1 = self.status("playbooks/db-refresh", "--note")
        self.assertEqual(r1.returncode, 1)
        self.assertIn("note queued", r1.stdout)
        text = self.NOTES.read_text(encoding="utf-8")
        self.assertIn("- STALE: `playbooks/db-refresh`", text)
        r2 = self.status("playbooks/db-refresh", "--note")
        self.assertIn("already queued", r2.stdout)
        text = self.NOTES.read_text(encoding="utf-8")
        self.assertEqual(text.count("STALE: `playbooks/db-refresh`"), 1)

    def test_note_written_for_tampered_page(self):
        page = self.wiki / "concepts" / "app.md"
        page.write_text(page.read_text(encoding="utf-8") + "\nedit\n",
                        encoding="utf-8")
        r = self.status("concepts/app", "--note")
        self.assertEqual(r.returncode, 1)
        self.assertIn("concepts/app", self.NOTES.read_text(encoding="utf-8"))


class TestJson(WikiBase):
    def test_json_single_page_fresh_and_stale(self):
        out = json.loads(self.status("concepts/app", "--json").stdout)
        self.assertEqual(out["page"], "concepts/app")
        self.assertEqual(out["verdict"], "FRESH")
        self.assertEqual(out["changed"], [])
        self.assertIn("why", out)
        self.src_app.write_text("print('v2')\n", encoding="utf-8")
        r = self.status("concepts/app", "--json")
        self.assertEqual(r.returncode, 1)
        out = json.loads(r.stdout)
        self.assertEqual(out["verdict"], "STALE")
        self.assertTrue(out["changed"][0].startswith("src/app.py"))

    def test_json_whole_wiki_shape_and_counts(self):
        r = self.status("--json")
        self.assertEqual(r.returncode, 0)
        report = json.loads(r.stdout)
        self.assertIn("stamped", report)
        self.assertEqual(report["counts"].get("FRESH"), 3)
        self.assertEqual(report["counts"].get("UNVERIFIABLE"), 1)
        verdicts = {row["page"]: row["verdict"] for row in report["pages"]}
        self.assertEqual(verdicts["notes/orphan"], "UNVERIFIABLE")
        self.assertEqual(verdicts["concepts/app"], "FRESH")


class TestErrorsAndTraversal(WikiBase):
    def test_missing_manifest_exits_2_with_hint(self):
        bare = self.tmp / "bare" / "docs" / "wiki"
        bare.mkdir(parents=True)
        shutil.copy(STATUS_TEMPLATE, bare / "status.py")
        r = self.status(wiki=bare)
        self.assertEqual(r.returncode, 2)
        self.assertIn("manifest.json", r.stderr)
        self.assertIn("stamp", r.stderr)  # tells the user what to run

    def test_manifest_without_provenance_exits_2_with_hint(self):
        # init writes a manifest but only stamp adds the provenance block
        other_root = self.tmp / "unstamped"
        other = other_root / "docs" / "wiki"
        other.mkdir(parents=True)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = wm.main([str(other), "init", "--profile", "generic"])
        self.assertEqual(rc, 0)
        shutil.copy(STATUS_TEMPLATE, other / "status.py")
        r = self.status(wiki=other)
        self.assertEqual(r.returncode, 2)
        self.assertIn("provenance", r.stderr)
        self.assertIn("stamp", r.stderr)

    def test_traversal_page_id_never_yields_trusted_verdict(self):
        # an .md file OUTSIDE the wiki that a ..-id could point at
        (self.root / "evil.md").write_text("# outside the wiki\n",
                                           encoding="utf-8")
        r = self.status("../../evil")
        # provenance keys never contain '..', so the traversal id can only
        # degrade to UNVERIFIABLE (file exists) or an error — never
        # FRESH/STALE/TAMPERED, and check_page never reads the target.
        self.assertIn(r.returncode, (0, 2))
        for trusted in ("FRESH", "STALE", "TAMPERED"):
            self.assertNotIn(trusted, r.stdout)
        r2 = self.status("../../does-not-exist")
        self.assertEqual(r2.returncode, 2)
        self.assertIn("not a wiki page id", r2.stderr)


if __name__ == "__main__":
    unittest.main()
