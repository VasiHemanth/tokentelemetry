import { test } from "node:test";
import assert from "node:assert/strict";
import { looksLikeMarkdown } from "./markdown";

test("recognizes document structure, fenced code, and GFM tables", () => {
  for (const value of ["## Findings\n\nRecorded text", "- First item\n- Second item", "1. First item", "```ts\nconst n = 1;\n```", "| Name | Status |\n| --- | --- |\n| Read | Done |", "> Recorded note"]) assert.equal(looksLikeMarkdown(value), true, value);
});

test("recognizes inline code, emphasis, and links without converting plain logs", () => {
  for (const value of ["Use `read_file` here.", "**Recorded result**", "[Reference](docs/readme.md)"]) assert.equal(looksLikeMarkdown(value), true);
  for (const value of ["exit code: 0\nstdout: OK", "file.ts:12:4 - error TS1234", "Hello world", "__init__.py\n__main__.py", "total 24\n-rw-r--r-- 1 dev staff 120 file.ts"]) assert.equal(looksLikeMarkdown(value), false);
});

test("diffs and stack traces stay literal even with Markdown-like lines", () => {
  assert.equal(looksLikeMarkdown("diff --git a/file b/file\n--- a/file\n+++ b/file\n- old line\n+ new line"), false);
  assert.equal(looksLikeMarkdown('Traceback (most recent call last):\n  File "app.py", line 10\nValueError: **bad**'), false);
});
