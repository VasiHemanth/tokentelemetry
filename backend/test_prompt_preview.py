"""Session-list prompt previews for IDE-originated Claude Code sessions.

Discussion #129: sessions started from the VS Code / JetBrains plugins prefix
the first user prompt with <ide_selection>/<ide_opened_file> context tags, so
the sessions list showed either the tag junk or "No prompt content". The
preview helper must strip the editor context and surface the typed prompt.
"""

from main import _claude_user_prompt_preview, _strip_context_tags


def _user_line(content, **extra):
    line = {"type": "user", "message": {"role": "user", "content": content}}
    line.update(extra)
    return line


def test_plain_string_prompt_passes_through():
    assert _claude_user_prompt_preview(_user_line("fix the login bug")) == "fix the login bug"


def test_ide_selection_prefix_is_stripped():
    raw = "<ide_selection>The user selected lines 4-9 of foo.py:\ndef f(): ...</ide_selection>\nRefactor this function"
    assert _claude_user_prompt_preview(_user_line(raw)) == "Refactor this function"


def test_ide_opened_file_prefix_is_stripped():
    raw = "<ide_opened_file>The user opened bar.ts</ide_opened_file>\nAdd null checks here"
    assert _claude_user_prompt_preview(_user_line(raw)) == "Add null checks here"


def test_multiple_ide_tags_and_system_reminder_stripped():
    raw = (
        "<ide_opened_file>a.py</ide_opened_file>"
        "<ide_diagnostics>2 warnings</ide_diagnostics>"
        "<system-reminder>injected context</system-reminder>"
        "\nExplain the warnings"
    )
    assert _claude_user_prompt_preview(_user_line(raw)) == "Explain the warnings"


def test_content_block_list_is_supported():
    content = [
        {"type": "text", "text": "<ide_selection>sel</ide_selection>\nWrite a test for this"},
    ]
    assert _claude_user_prompt_preview(_user_line(content)) == "Write a test for this"


def test_ide_context_only_message_yields_none():
    raw = "<ide_opened_file>The user opened baz.rs</ide_opened_file>"
    assert _claude_user_prompt_preview(_user_line(raw)) is None


def test_meta_and_command_lines_are_skipped():
    assert _claude_user_prompt_preview(_user_line("anything", isMeta=True)) is None
    assert _claude_user_prompt_preview(_user_line("<local-command-stdout>out</local-command-stdout>")) is None
    assert _claude_user_prompt_preview(_user_line("<command-name>/model</command-name>")) is None
    assert _claude_user_prompt_preview(_user_line("Caveat: the messages below were generated…")) is None


def test_tool_result_only_content_yields_none():
    content = [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]
    assert _claude_user_prompt_preview(_user_line(content)) is None


def test_preview_is_truncated_to_limit():
    long = "x" * 500
    out = _claude_user_prompt_preview(_user_line(long))
    assert out == "x" * 200


def test_strip_context_tags_handles_opencode_system_reminder():
    # OpenCode text parts get the same treatment (e.g. VS Code extension
    # prefixes "Note: The user opened the file …" reminders).
    raw = '<system-reminder>Note: The user opened the file "/x/y.py"</system-reminder>\nSummarize it'
    assert _strip_context_tags(raw) == "Summarize it"
    assert _strip_context_tags('<system-reminder>only context</system-reminder>') == ""


def test_unclosed_tag_falls_back_to_raw_text():
    # A malformed/unclosed tag can't be stripped safely — better to show
    # something than nothing.
    raw = "<ide_selection>partial…\nDo the thing"
    assert _claude_user_prompt_preview(_user_line(raw)).startswith("<ide_selection>partial")
