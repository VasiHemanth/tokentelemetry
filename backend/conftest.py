import os
import pytest

_VARS = ("TOKENTELEMETRY_DATA_DIR", "TOKENTELEMETRY_HOME")


@pytest.fixture(autouse=True)
def _isolate_tt_data_dir():
    saved = {v: os.environ.get(v) for v in _VARS}
    yield
    for v, val in saved.items():
        if val is None:
            os.environ.pop(v, None)
        else:
            os.environ[v] = val
