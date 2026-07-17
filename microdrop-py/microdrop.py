"""Parameterized Microdrop entry point.

Run from ``microdrop-py/`` (the pixi ``microdrop`` task does this)::

    pixi run microdrop --device dropbot \
        --plugins DeviceViewerPlugin DropbotControllerPlugin \
        --contexts redis_server dramatiq_workers

With no arguments this launches the full dropbot frontend + backend set.
"""
import argparse

from examples.plugin_consts import (
    BACKEND_APPLICATION,
    BACKEND_PLUGINS,
    DROPBOT_BACKEND_PLUGINS,
    DROPBOT_FRONTEND_PLUGINS,
    FRONTEND_APPLICATION,
    FRONTEND_PLUGINS,
    MOCK_DROPBOT_BACKEND_PLUGINS,
    MOCK_DROPBOT_FRONTEND_PLUGINS,
    OPENDROP_BACKEND_PLUGINS,
    OPENDROP_FRONTEND_PLUGINS,
    REQUIRED_CONTEXT,
    REQUIRED_PLUGINS,
    SERVER_CONTEXT,
    SERVICE_PLUGINS,
)
from examples.run_device_viewer_pluggable import main

# Canonical load order — plugin_consts order decides Envisage service
# priority, so user selections are re-sorted to this order.
_ORDERED_OPTIONAL_GROUPS = (
    FRONTEND_PLUGINS,
    DROPBOT_FRONTEND_PLUGINS,
    OPENDROP_FRONTEND_PLUGINS,
    MOCK_DROPBOT_FRONTEND_PLUGINS,
    SERVICE_PLUGINS,
    BACKEND_PLUGINS,
    DROPBOT_BACKEND_PLUGINS,
    OPENDROP_BACKEND_PLUGINS,
    MOCK_DROPBOT_BACKEND_PLUGINS,
)

_FRONTEND_PLUGIN_SET = frozenset(
    plugin
    for group in (FRONTEND_PLUGINS, DROPBOT_FRONTEND_PLUGINS,
                  OPENDROP_FRONTEND_PLUGINS, MOCK_DROPBOT_FRONTEND_PLUGINS)
    for plugin in group
)

# name -> class, in canonical order (setdefault keeps the first position of
# a plugin that appears in more than one group)
OPTIONAL_PLUGINS = {}
for _group in _ORDERED_OPTIONAL_GROUPS:
    for _plugin in _group:
        OPTIONAL_PLUGINS.setdefault(_plugin.__name__, _plugin)

CONTEXTS = {
    "redis_server": SERVER_CONTEXT,
    "dramatiq_workers": REQUIRED_CONTEXT,
}

_DEVICE_FRONTEND_GROUPS = {
    "dropbot": [DROPBOT_FRONTEND_PLUGINS],
    "opendrop": [OPENDROP_FRONTEND_PLUGINS],
    "mock": [MOCK_DROPBOT_FRONTEND_PLUGINS, DROPBOT_FRONTEND_PLUGINS],
}
_DEVICE_BACKEND_GROUPS = {
    "dropbot": [DROPBOT_BACKEND_PLUGINS],
    "opendrop": [OPENDROP_BACKEND_PLUGINS],
    "mock": [MOCK_DROPBOT_BACKEND_PLUGINS],
}


def _default_plugin_names(device):
    groups = ([FRONTEND_PLUGINS] + _DEVICE_FRONTEND_GROUPS[device]
              + [SERVICE_PLUGINS, BACKEND_PLUGINS]
              + _DEVICE_BACKEND_GROUPS[device])
    return [plugin.__name__ for group in groups for plugin in group]


def resolve_run_config(device="dropbot", plugin_names=None, context_names=None):
    """Resolve name-based selections into arguments for ``main``.

    Empty/None ``plugin_names`` means "the full default set for *device*";
    empty/None ``context_names`` means "infer from the selection" (redis +
    workers for a frontend, workers only for a backend-only selection).
    """
    if not plugin_names:
        plugin_names = _default_plugin_names(device)
    unknown = sorted(set(plugin_names) - OPTIONAL_PLUGINS.keys())
    if unknown:
        raise ValueError(f"Unknown plugins: {', '.join(unknown)}. "
                         f"Valid names: {', '.join(OPTIONAL_PLUGINS)}")
    selected = set(plugin_names)
    optional = [plugin for name, plugin in OPTIONAL_PLUGINS.items()
                if name in selected]
    has_frontend = any(plugin in _FRONTEND_PLUGIN_SET for plugin in optional)

    if not context_names:
        contexts = (SERVER_CONTEXT + REQUIRED_CONTEXT if has_frontend
                    else list(REQUIRED_CONTEXT))
    else:
        unknown = sorted(set(context_names) - CONTEXTS.keys())
        if unknown:
            raise ValueError(f"Unknown contexts: {', '.join(unknown)}. "
                             f"Valid names: {', '.join(CONTEXTS)}")
        selected_contexts = set(context_names)
        contexts = [ctx for name, group in CONTEXTS.items()
                    if name in selected_contexts for ctx in group]

    return {
        "plugins": list(dict.fromkeys(REQUIRED_PLUGINS + optional)),
        "contexts": contexts,
        "application": FRONTEND_APPLICATION if has_frontend
        else BACKEND_APPLICATION,
        "persist": not has_frontend,
    }


def microdrop(device="dropbot", plugin_names=None, context_names=None):
    main(**resolve_run_config(device, plugin_names, context_names))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Microdrop with a custom plugin/context selection.")
    parser.add_argument(
        "--device", choices=["dropbot", "opendrop", "mock"], default="dropbot",
        help="Device whose default plugin set is used when --plugins is "
             "omitted.")
    parser.add_argument(
        "--plugins", nargs="+", metavar="PLUGIN",
        choices=sorted(OPTIONAL_PLUGINS),
        help="Optional plugin class names to load (required plugins are "
             "always loaded).")
    parser.add_argument(
        "--contexts", nargs="+", choices=sorted(CONTEXTS),
        help="Contexts to start (default: inferred from the selection).")
    args = parser.parse_args()
    microdrop(args.device, args.plugins, args.contexts)
