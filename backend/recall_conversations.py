"""Local Ask conversations, stored separately from the searchable Recall index."""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone

from tt_paths import data_dir

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    project TEXT,
    project_name TEXT,
    agents TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS turns (
    seq INTEGER PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    answer TEXT
);
CREATE INDEX IF NOT EXISTS conversation_turns ON turns(conversation_id, seq);
"""


def _connect():
    path = data_dir() / "recall_conversations.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


def _summary(row):
    return {**dict(row), "agents": json.loads(row["agents"])}


def list_conversations():
    with closing(_connect()) as conn:
        return [_summary(row) for row in conn.execute(
            "SELECT * FROM conversations ORDER BY updated_at DESC, id"
        )]


def get_conversation(conversation_id, *, recent=None):
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM conversations WHERE id=?", (conversation_id,)).fetchone()
        if row is None:
            return None
        sql = "SELECT seq, question, answer FROM turns WHERE conversation_id=?"
        if recent is None:
            turns = conn.execute(sql + " ORDER BY seq", (conversation_id,)).fetchall()
        else:
            turns = list(reversed(conn.execute(sql + " ORDER BY seq DESC LIMIT ?",
                                               (conversation_id, recent)).fetchall()))
        return {**_summary(row), "turns": [
            {"id": turn["seq"], "question": turn["question"],
             "answer": json.loads(turn["answer"]) if turn["answer"] else None}
            for turn in turns
        ]}


def add_question(conversation_id, question, project, project_name, agents):
    now = datetime.now(timezone.utc).isoformat()
    title = " ".join(question.split())[:100]
    with closing(_connect()) as conn, conn:
        conn.execute(
            "INSERT INTO conversations VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (conversation_id, title, project, project_name, json.dumps(agents), now),
        )
        saved = conn.execute("SELECT project, agents FROM conversations WHERE id=?",
                             (conversation_id,)).fetchone()
        if saved["project"] != project or json.loads(saved["agents"]) != agents:
            raise ValueError("This conversation uses different project or agent filters. Start a new chat.")
        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conversation_id))
        return conn.execute("INSERT INTO turns(conversation_id, question) VALUES (?, ?)",
                            (conversation_id, question)).lastrowid


def save_answer(conversation_id, turn_id, answer):
    with closing(_connect()) as conn, conn:
        conn.execute("UPDATE turns SET answer=? WHERE conversation_id=? AND seq=?",
                     (json.dumps(answer), conversation_id, turn_id))


def delete_conversation(conversation_id):
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
