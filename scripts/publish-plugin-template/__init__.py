"""No-op register for the TokenTelemetry dashboard plugin.

The plugin ships only the dashboard layer (``dashboard/manifest.json`` +
``dashboard/dist/``). The root ``plugin.yaml`` makes Hermes register the
directory as a general plugin, and Hermes requires an ``__init__.py`` for
that; without one, every Hermes start logs ``Failed to load plugin
'tokentelemetry': No __init__.py``. This no-op ``register()`` keeps the
load clean.
"""


def register(ctx):
    pass
