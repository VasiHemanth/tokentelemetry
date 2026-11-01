import asyncio
import json
import sqlite3

import pytest
import main


def detail(sid, agent):
    return asyncio.run(main.get_session_detail(sid, agent))


def test_pi_preserves_usage_model_and_error(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'PI_SESSIONS_DIR', tmp_path)
    bucket = tmp_path / 'project'; bucket.mkdir()
    rows = [
        {'type': 'message', 'timestamp': '2026-01-01T00:00:00Z', 'message': {'role': 'assistant', 'model': 'test-model', 'usage': {'input': 10, 'output': 3, 'cacheRead': 5, 'cacheWrite': 2}, 'content': [{'type': 'toolCall', 'id': 'call', 'name': 'run', 'arguments': {}}]}},
        {'type': 'message', 'timestamp': '2026-01-01T00:00:01Z', 'message': {'role': 'toolResult', 'toolCallId': 'call', 'isError': True, 'content': [{'type': 'text', 'text': 'failed'}]}},
    ]
    (bucket / 'test-session.jsonl').write_text('\n'.join(map(json.dumps, rows)))
    events = detail('test-session', 'pi')
    assert events[0]['message']['usage'] == rows[0]['message']['usage']
    assert events[0]['message']['model'] == 'test-model'
    assert events[1]['message']['content'][0]['is_error'] is True


def test_prime_preserves_usage_and_call_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'PRIME_SESSIONS_DIR', tmp_path)
    ts = '2026-01-01T00:00:00Z'
    rows = [{'type': 'session', 'id': 'test'},
            {'type': 'message', 'id': 'a', 'timestamp': ts, 'message': {'role': 'assistant', 'model': 'test-model', 'usage': {'input': 10, 'output': 3}, 'content': [{'type': 'toolCall', 'id': 'call', 'name': 'run', 'arguments': {}}]}},
            {'type': 'message', 'id': 'b', 'parentId': 'a', 'timestamp': ts, 'message': {'role': 'toolResult', 'toolCallId': 'call', 'toolName': 'run', 'isError': True, 'content': [{'type': 'text', 'text': 'failed'}]}}]
    (tmp_path / 'session.jsonl').write_text('\n'.join(map(json.dumps, rows)))
    events = detail('test', 'prime')
    assert events[0]['payload']['callID'] == 'call'
    assert events[0]['usage'] == {'input': 10, 'output': 3}
    assert events[0]['model'] == 'test-model'
    assert events[1]['payload']['callID'] == 'call'
    assert events[1]['payload']['is_error'] is True


@pytest.mark.parametrize('agent', ['opencode', 'zcode'])
def test_step_usage_stays_with_its_own_message(tmp_path, monkeypatch, agent):
    db = tmp_path / 'test.db'; conn = sqlite3.connect(db)
    conn.executescript('CREATE TABLE session(id TEXT); CREATE TABLE message(id TEXT, session_id TEXT, time_created INTEGER, data TEXT); CREATE TABLE part(message_id TEXT, session_id TEXT, time_created INTEGER, data TEXT);')
    conn.execute('INSERT INTO session VALUES (?)', ('session',))
    for i in range(3): conn.execute('INSERT INTO message VALUES (?, ?, ?, ?)', (f'm{i}', 'session', i, json.dumps({'role': 'assistant'})))
    parts = [('m0', 1, {'type':'text','text':'one'}), ('m0', 2, {'type':'step-finish','tokens':{'input': 10}}), ('m1', 3, {'type':'step-start'}), ('m1', 4, {'type':'step-finish','tokens':{'input': 20}}), ('m2', 5, {'type':'text','text':'two'}), ('m2', 6, {'type':'step-finish','tokens':{'input': 30}})]
    for mid, t, data in parts: conn.execute('INSERT INTO part VALUES (?, ?, ?, ?)', (mid, 'session', t, json.dumps(data)))
    conn.commit(); conn.close()
    monkeypatch.setattr(main, f'_{agent}_db_for_session', lambda _: db)
    events = detail('session', agent)
    assert [(e['type'], e.get('tokens', {}).get('input')) for e in events] == [('assistant', 10), ('step_usage', 20), ('assistant', 30)]
