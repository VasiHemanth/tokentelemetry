"""Keep backend tests independent from a developer's local app configuration."""

import os

import pytest


_CONFIG_ENV = ("TOKENTELEMETRY_DATA_DIR", "TOKENTELEMETRY_HOME")


for _name in _CONFIG_ENV:
    os.environ.pop(_name, None)


@pytest.fixture(autouse=True)
def _isolate_config_env(monkeypatch):
    """Undo direct environment writes made by legacy tests between test cases."""
    for name in _CONFIG_ENV:
        monkeypatch.delenv(name, raising=False)
