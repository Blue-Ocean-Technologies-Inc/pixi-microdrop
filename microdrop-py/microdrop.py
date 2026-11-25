# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Parameterized Microdrop entry point.

Run from ``microdrop-py/`` (the pixi ``microdrop`` task does this)::

    pixi run microdrop --device dropbot \
        --plugins DeviceViewerPlugin DropbotControllerPlugin \
        --contexts redis_server dramatiq_workers

With no arguments this launches the full dropbot frontend + backend set.
"""

# Standard library imports.
import argparse
import sys

# Microdrop package imports.
from examples import plugin_consts
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
    PORTABLE_DROPBOT_FRONTEND_PLUGINS,
    REQUIRED_CONTEXT,
    REQUIRED_PLUGINS,
    SERVER_CONTEXT,
    SERVICE_PLUGINS,
)
from examples.run_device_viewer_pluggable import main

#: The portable backend plugins, known by name so they can be selected
#: without importing them: their module pulls in the dropbot_portable driver
#: stack, which only a portable run needs (src loads them lazily).
PORTABLE_DROPBOT_BACKEND_PLUGIN_NAMES = ("PortableDropbotControllerPlugin",)


def _load_portable_dropbot_backend_plugins():
    """Import the portable backend plugin classes on first use.

    Src before the lazy loader (the submodule the launcher pins until its
    next bump) still exports them as an eager list.
    """
    loader = getattr(plugin_consts, "_lazy_load_portable_dropbot_plugins", None)

    if loader is None:
        return plugin_consts.PORTABLE_DROPBOT_BACKEND_PLUGINS

    return loader()


def _plugin_name(plugin):
    """A plugin class's name; lazily loaded plugins are listed by name.

    A ``DeferredPlugin`` declaration gives its class's name as ``__name__``
    without importing it.
    """
    return plugin if isinstance(plugin, str) else plugin.__name__


#: Frontend plugins src starts only after the main window has painted, as
#: ``DeferredPlugin`` declarations passed to ``main`` as they are. Src before
#: the deferred loader lists them with the eager frontend plugins instead.
DEFERRED_FRONTEND_PLUGINS = getattr(plugin_consts, "DEFERRED_FRONTEND_PLUGINS", [])


# Canonical load order — plugin_consts order decides Envisage service
# priority, so user selections are re-sorted to this order.
_ORDERED_OPTIONAL_GROUPS = (
    FRONTEND_PLUGINS,
    DROPBOT_FRONTEND_PLUGINS,
    PORTABLE_DROPBOT_FRONTEND_PLUGINS,
    OPENDROP_FRONTEND_PLUGINS,
    MOCK_DROPBOT_FRONTEND_PLUGINS,
    SERVICE_PLUGINS,
    # After the service plugins, as src's own run script lists them: deferred
    # plugins load in list order, so a UI never runs before its service.
    DEFERRED_FRONTEND_PLUGINS,
    BACKEND_PLUGINS,
    DROPBOT_BACKEND_PLUGINS,
    PORTABLE_DROPBOT_BACKEND_PLUGIN_NAMES,
    OPENDROP_BACKEND_PLUGINS,
    MOCK_DROPBOT_BACKEND_PLUGINS,
)

_FRONTEND_PLUGIN_SET = frozenset(
    plugin
    for group in (
        FRONTEND_PLUGINS,
        DROPBOT_FRONTEND_PLUGINS,
        PORTABLE_DROPBOT_FRONTEND_PLUGINS,
        OPENDROP_FRONTEND_PLUGINS,
        MOCK_DROPBOT_FRONTEND_PLUGINS,
        DEFERRED_FRONTEND_PLUGINS,
    )
    for plugin in group
)

# name -> class (or DeferredPlugin declaration), in canonical order
# (setdefault keeps the first position of a plugin that appears in more than
# one group); None for a plugin imported only when selected (see
# _resolve_plugin)
OPTIONAL_PLUGINS = {}
for _group in _ORDERED_OPTIONAL_GROUPS:
    for _plugin in _group:
        OPTIONAL_PLUGINS.setdefault(
            _plugin_name(_plugin), None if isinstance(_plugin, str) else _plugin
        )

CONTEXTS = {
    "redis_server": SERVER_CONTEXT,
    "dramatiq_workers": REQUIRED_CONTEXT,
}

_DEVICE_FRONTEND_GROUPS = {
    "dropbot": [DROPBOT_FRONTEND_PLUGINS],
    "portable": [PORTABLE_DROPBOT_FRONTEND_PLUGINS],
    "opendrop": [OPENDROP_FRONTEND_PLUGINS],
    "mock": [MOCK_DROPBOT_FRONTEND_PLUGINS, DROPBOT_FRONTEND_PLUGINS],
}
_DEVICE_BACKEND_GROUPS = {
    "dropbot": [DROPBOT_BACKEND_PLUGINS],
    "portable": [PORTABLE_DROPBOT_BACKEND_PLUGIN_NAMES],
    "opendrop": [OPENDROP_BACKEND_PLUGINS],
    "mock": [MOCK_DROPBOT_BACKEND_PLUGINS],
}


def _default_plugin_names(device):
    groups = (
        [FRONTEND_PLUGINS]
        + _DEVICE_FRONTEND_GROUPS[device]
        + [SERVICE_PLUGINS, DEFERRED_FRONTEND_PLUGINS, BACKEND_PLUGINS]
        + _DEVICE_BACKEND_GROUPS[device]
    )

    return [_plugin_name(plugin) for group in groups for plugin in group]


def _known_plugin_names(plugin_names, device):
    """Drop the names this source does not know, with a warning on stderr.

    A saved selection outlives the source it was made for: a later Microdrop
    can rename, remove or re-declare a plugin. Starting without it beats not
    starting at all. When no known name is left, the device's default set
    runs instead.
    """
    unknown = [name for name in plugin_names if name not in OPTIONAL_PLUGINS]

    if not unknown:
        return plugin_names

    known = [name for name in plugin_names if name in OPTIONAL_PLUGINS]

    print(
        "Warning: skipping plugins this Microdrop version does not have: "
        f"{', '.join(unknown)}. Re-save the plugin selection in the Setup & "
        "Launcher to stop this warning.",
        file=sys.stderr,
    )

    if not known:
        print(
            "Warning: no known plugins left in the selection; starting the "
            f"default '{device}' plugin set.",
            file=sys.stderr,
        )

    return known


def _resolve_plugin(name):
    """The plugin class for a selected name, importing a lazy one now."""
    plugin = OPTIONAL_PLUGINS[name]

    if plugin is not None:
        return plugin

    return next(
        plugin
        for plugin in _load_portable_dropbot_backend_plugins()
        if plugin.__name__ == name
    )


def resolve_run_config(device="dropbot", plugin_names=None, context_names=None):
    """Resolve name-based selections into arguments for ``main``.

    Empty/None ``plugin_names`` means "the full default set for *device*";
    names this source does not know are skipped with a warning. Empty/None
    ``context_names`` means "infer from the selection" (redis + workers for a
    frontend, workers only for a backend-only selection).

    Deferred frontend plugins stay ``DeferredPlugin`` declarations in the
    returned plugin list; ``main`` starts them after the window has painted.
    """
    plugin_names = _known_plugin_names(plugin_names or [], device)

    if not plugin_names:
        plugin_names = _default_plugin_names(device)

    selected = set(plugin_names)
    optional = [_resolve_plugin(name) for name in OPTIONAL_PLUGINS if name in selected]
    has_frontend = any(plugin in _FRONTEND_PLUGIN_SET for plugin in optional)

    if not context_names:
        contexts = (
            SERVER_CONTEXT + REQUIRED_CONTEXT
            if has_frontend
            else list(REQUIRED_CONTEXT)
        )
    else:
        unknown = sorted(set(context_names) - CONTEXTS.keys())
        if unknown:
            raise ValueError(
                f"Unknown contexts: {', '.join(unknown)}. "
                f"Valid names: {', '.join(CONTEXTS)}"
            )
        selected_contexts = set(context_names)
        contexts = [
            ctx
            for name, group in CONTEXTS.items()
            if name in selected_contexts
            for ctx in group
        ]

    return {
        "plugins": list(dict.fromkeys(REQUIRED_PLUGINS + optional)),
        "contexts": contexts,
        "application": FRONTEND_APPLICATION if has_frontend else BACKEND_APPLICATION,
        "persist": not has_frontend,
    }


def microdrop(device="dropbot", plugin_names=None, context_names=None):
    main(**resolve_run_config(device, plugin_names, context_names))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run Microdrop with a custom plugin/context selection."
    )
    parser.add_argument(
        "--device",
        choices=["dropbot", "portable", "opendrop", "mock"],
        default="dropbot",
        help="Device whose default plugin set is used when --plugins is omitted.",
    )
    # No argparse choices: an unknown name, such as one saved for an older
    # Microdrop, is skipped with a warning instead of refusing to start.
    parser.add_argument(
        "--plugins",
        nargs="+",
        metavar="PLUGIN",
        help="Optional plugin class names to load (required plugins are "
        "always loaded; unknown names are skipped with a warning). Known: "
        f"{', '.join(sorted(OPTIONAL_PLUGINS))}.",
    )
    parser.add_argument(
        "--contexts",
        nargs="+",
        choices=sorted(CONTEXTS),
        help="Contexts to start (default: inferred from the selection).",
    )
    args = parser.parse_args()
    microdrop(args.device, args.plugins, args.contexts)
