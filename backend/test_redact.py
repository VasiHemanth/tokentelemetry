"""Redaction tests. Every secret-shaped fixture is assembled at runtime so no
contiguous realistic credential appears in the source (push protection)."""
from redact import redact

GH = "gh" + "p_" + "a" * 36
GH_PAT = "github" + "_pat_" + "B" * 30
AWS = "AK" + "IA" + "B" * 16
ANT = "sk-" + "ant-" + "api03-" + "Z9" * 15
OAI = "sk-" + "proj-" + "Ab1" * 10
SLACK = "xo" + "xb-" + "1234567890-" + "abcdef"
GOOG = "AI" + "za" + "C" * 35
STRIPE = "sk_" + "live_" + "D" * 24
JWT = "ey" + "J" + "h" * 12 + "." + "ey" + "J" + "p" * 12 + "." + "s" * 12
PEM_BEGIN = "-----BEGIN " + "RSA PRIVATE KEY-----"
PEM_END = "-----END " + "RSA PRIVATE KEY-----"


def test_vendor_tokens():
    assert redact(f"key {GH} end") == "key [REDACTED:github_token] end"
    assert redact(GH_PAT) == "[REDACTED:github_token]"
    assert redact(AWS) == "[REDACTED:aws_access_key]"
    assert redact(ANT) == "[REDACTED:anthropic_key]"
    assert redact(OAI) == "[REDACTED:openai_key]"
    assert redact(SLACK) == "[REDACTED:slack_token]"
    assert redact(GOOG) == "[REDACTED:google_api_key]"
    assert redact(STRIPE) == "[REDACTED:stripe_key]"
    assert redact(JWT) == "[REDACTED:jwt]"


def test_anthropic_not_relabelled_openai():
    assert "openai" not in redact(ANT)


def test_pem_block_multiline_and_truncated():
    body = "MIIEow" + "A" * 40
    text = f"before\n{PEM_BEGIN}\n{body}\n{body}\n{PEM_END}\nafter"
    out = redact(text)
    assert out == "before\n[REDACTED:private_key]\nafter"
    # Chunk cut off before the END marker: everything after BEGIN goes.
    assert redact(f"x {PEM_BEGIN}\n{body}") == "x [REDACTED:private_key]"
    # Stray END marker from a split block.
    assert redact(f"{body}\n{PEM_END}") == f"{body}\n[REDACTED:private_key]"


def test_bearer_and_url_credentials():
    tok = "abcDEF0123456789xyz"
    assert redact(f"Authorization: Bearer {tok}") == "[REDACTED:bearer]"
    assert redact("curl -H 'x' https://user:" + "hunter2@" + "example.com/p") == \
        "curl -H 'x' https://[REDACTED:url_credentials]@example.com/p"


def test_assignment():
    assert redact("password=" + "hunter2hunter") == "password=[REDACTED:assignment]"
    assert redact("API_KEY: " + "abc123def456") == "API_KEY: [REDACTED:assignment]"
    assert redact('{"client_secret": "' + 'Xy9' * 4 + '"}') == '{"client_secret": "[REDACTED:assignment]"}'
    assert redact("OPENAI_API_KEY=" + "x1" * 8) == "OPENAI_API_KEY=[REDACTED:assignment]"


def test_prose_and_code_untouched():
    for s in [
        "the token count is high",
        "add a password field to the form",
        "password=short",
        "token = get_token_value",
        "api_key = os.environ.get",
        "max_tokens=4096",
        "tokens_used: 123456789",
        "secret: nothing",
        "commit " + "a1b2c3d4" * 5 + " fixes the bug",
        "see https://example.com/a/b and git@github.com:org/repo.git",
        "task-runner-with-a-long-kebab-name",
        "Bearer token handling in the proxy",
    ]:
        assert redact(s) == s, s


def test_non_string_input():
    assert redact(None) == ""
    assert redact(5) == "5"


def test_lowercase_passphrase_redacted_but_code_kept():
    assert "correcthorse" not in redact("password=" + "correcthorse" + "battery")
    assert redact("token = get_token_value") == "token = get_token_value"
    assert redact("secret: os.environ.get") == "secret: os.environ.get"
    assert redact("api_key=None") == "api_key=None"
    assert redact("max_tokens=4096") == "max_tokens=4096"


def test_basic_auth_redacted():
    value = "dXNlcjpw" + "YXNzd29yZDEyMzQ1Ng=="
    assert value not in redact("Authorization: Basic " + value)


def test_long_runs_stay_linear():
    import time
    for s in ("a" * 200000, "a-" * 100000, "sk-" * 66666, "password" * 25000, "a://" + "b" * 200000):
        t = time.monotonic()
        redact(s)
        assert time.monotonic() - t < 2.0
