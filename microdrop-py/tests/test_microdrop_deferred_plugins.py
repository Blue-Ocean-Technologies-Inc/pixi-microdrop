# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Launcher name resolution against fake ``examples.plugin_consts`` modules.

``microdrop.py`` reads ``examples.plugin_consts`` at import, so each test puts
a fake ``examples`` package in ``sys.modules`` first and then executes the
launcher file by path: no Microdrop source checkout is needed, and the source
layouts before and after deferred frontend plugins are both covered.
"""

# Standard library imports.
import importlib.util
import runpy
import sys
import types
from pathlib import Path

# Third-party imports.
import pytest

ENTRY_PATH = Path(__file__).resolve().parents[1] / "microdrop.py"

FRONTEND_APPLICATION = object()
BACKEND_APPLICATION = object()
SERVER_CONTEXT = [("redis_server_context", {})]
REQUIRED_CONTEXT = [("dramatiq_workers_context", {})]


class FakeDeferredPlugin:
    """Stand-in for ``microdrop_utils.deferred_plugins.DeferredPlugin``."""

    def __init__(self, spec):
        self.spec = spec

    @property
    def class_name(self):
        return self.spec.partition(":")[2]

    @property
    def __name__(self):
        return self.class_name

    def import_class(self):
        raise AssertionError("the launcher must not import a deferred plugin")


def _plugin_classes(*names):
    return [type(name, (), {}) for name in names]


def _fake_plugin_consts(with_deferred_plugins):
    """A plugin_consts module as src lays it out with or without deferral."""
    consts = types.ModuleType("examples.plugin_consts")

    consts.REQUIRED_PLUGINS = _plugin_classes("CorePlugin", "MessageRouterPlugin")
    consts.FRONTEND_PLUGINS = _plugin_classes(
        "MicrodropPlugin", "TasksPlugin", "DeviceViewerPlugin"
    )
    consts.DROPBOT_FRONTEND_PLUGINS = _plugin_classes("DropbotStatusPlugin")
    consts.PORTABLE_DROPBOT_FRONTEND_PLUGINS = _plugin_classes("PortableStatusPlugin")
    consts.OPENDROP_FRONTEND_PLUGINS = _plugin_classes("OpendropStatusPlugin")
    consts.MOCK_DROPBOT_FRONTEND_PLUGINS = _plugin_classes("MockDropbotStatusPlugin")
    consts.BACKEND_PLUGINS = _plugin_classes("ElectrodeControllerPlugin")
    consts.DROPBOT_BACKEND_PLUGINS = _plugin_classes("DropbotControllerPlugin")
    consts.OPENDROP_BACKEND_PLUGINS = _plugin_classes("OpenDropControllerPlugin")
    consts.MOCK_DROPBOT_BACKEND_PLUGINS = _plugin_classes("MockDropbotControllerPlugin")

    portable_backend = _plugin_classes("PortableDropbotControllerPlugin")
    consts._lazy_load_portable_dropbot_plugins = lambda: portable_backend

    if with_deferred_plugins:
        consts.SERVICE_PLUGINS = [
            FakeDeferredPlugin("ssh_controls.plugin:SSHControlsPlugin")
        ]
        consts.DEFERRED_FRONTEND_PLUGINS = [
            FakeDeferredPlugin("image_viewer.plugin:ImageViewerPlugin"),
            FakeDeferredPlugin("user_help_plugin.plugin:UserHelpPlugin"),
        ]
    else:
        consts.SERVICE_PLUGINS = _plugin_classes("SSHControlsPlugin")
        consts.FRONTEND_PLUGINS += _plugin_classes("ImageViewerPlugin")

    consts.REQUIRED_CONTEXT = REQUIRED_CONTEXT
    consts.SERVER_CONTEXT = SERVER_CONTEXT
    consts.FRONTEND_APPLICATION = FRONTEND_APPLICATION
    consts.BACKEND_APPLICATION = BACKEND_APPLICATION

    return consts


def _install_fake_source(monkeypatch, consts):
    """Put a fake ``examples`` package in sys.modules; return main's calls."""
    main_calls = []

    run_script = types.ModuleType("examples.run_device_viewer_pluggable")
    run_script.main = lambda **kwargs: main_calls.append(kwargs)

    examples = types.ModuleType("examples")
    examples.__path__ = []
    examples.plugin_consts = consts
    examples.run_device_viewer_pluggable = run_script

    monkeypatch.setitem(sys.modules, "examples", examples)
    monkeypatch.setitem(sys.modules, "examples.plugin_consts", consts)
    monkeypatch.setitem(sys.modules, "examples.run_device_viewer_pluggable", run_script)

    return main_calls


def _load_entry(monkeypatch, consts):
    _install_fake_source(monkeypatch, consts)

    spec = importlib.util.spec_from_file_location("microdrop_under_test", ENTRY_PATH)
    entry = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(entry)

    return entry


@pytest.fixture
def new_consts():
    return _fake_plugin_consts(with_deferred_plugins=True)


@pytest.fixture
def entry(monkeypatch, new_consts):
    return _load_entry(monkeypatch, new_consts)


def _names(plugins):
    return [plugin.__name__ for plugin in plugins]


def test_saved_deferred_name_passes_its_declaration_through(entry, new_consts):
    image_viewer = new_consts.DEFERRED_FRONTEND_PLUGINS[0]

    cfg = entry.resolve_run_config(
        plugin_names=["ImageViewerPlugin", "MicrodropPlugin", "TasksPlugin"]
    )

    assert cfg["plugins"][-1] is image_viewer
    assert _names(cfg["plugins"]) == [
        "CorePlugin",
        "MessageRouterPlugin",
        "MicrodropPlugin",
        "TasksPlugin",
        "ImageViewerPlugin",
    ]
    assert cfg["application"] is FRONTEND_APPLICATION


def test_default_set_matches_src_cli_order(entry, new_consts):
    c = new_consts

    cfg = entry.resolve_run_config()

    assert cfg["plugins"] == (
        c.REQUIRED_PLUGINS
        + c.FRONTEND_PLUGINS
        + c.DROPBOT_FRONTEND_PLUGINS
        + c.SERVICE_PLUGINS
        + c.DEFERRED_FRONTEND_PLUGINS
        + c.BACKEND_PLUGINS
        + c.DROPBOT_BACKEND_PLUGINS
    )
    assert cfg["contexts"] == SERVER_CONTEXT + REQUIRED_CONTEXT


@pytest.mark.parametrize("device", ["dropbot", "portable", "opendrop", "mock"])
def test_every_device_default_starts_the_deferred_plugins(entry, new_consts, device):
    plugins = entry.resolve_run_config(device=device)["plugins"]

    deferred = new_consts.DEFERRED_FRONTEND_PLUGINS
    start = plugins.index(deferred[0])

    assert plugins[start : start + len(deferred)] == deferred
    assert plugins[start - 1] is new_consts.SERVICE_PLUGINS[-1]


def test_deferred_only_selection_runs_the_frontend(entry):
    assert "UserHelpPlugin" in entry.OPTIONAL_PLUGINS

    cfg = entry.resolve_run_config(plugin_names=["UserHelpPlugin"])

    assert cfg["application"] is FRONTEND_APPLICATION
    assert cfg["persist"] is False
    assert cfg["contexts"] == SERVER_CONTEXT + REQUIRED_CONTEXT


def test_source_without_deferred_plugins_still_resolves(monkeypatch):
    consts = _fake_plugin_consts(with_deferred_plugins=False)
    entry = _load_entry(monkeypatch, consts)

    cfg = entry.resolve_run_config(plugin_names=["ImageViewerPlugin"])

    assert entry.DEFERRED_FRONTEND_PLUGINS == []
    assert cfg["plugins"][-1] is consts.FRONTEND_PLUGINS[-1]
    assert cfg["application"] is FRONTEND_APPLICATION
    assert entry.resolve_run_config()["plugins"] == (
        consts.REQUIRED_PLUGINS
        + consts.FRONTEND_PLUGINS
        + consts.DROPBOT_FRONTEND_PLUGINS
        + consts.SERVICE_PLUGINS
        + consts.BACKEND_PLUGINS
        + consts.DROPBOT_BACKEND_PLUGINS
    )


def test_unknown_saved_name_is_skipped_with_a_warning(entry, capsys):
    cfg = entry.resolve_run_config(plugin_names=["NopePlugin", "DeviceViewerPlugin"])

    assert _names(cfg["plugins"]) == [
        "CorePlugin",
        "MessageRouterPlugin",
        "DeviceViewerPlugin",
    ]
    assert "NopePlugin" in capsys.readouterr().err


def test_only_unknown_names_fall_back_to_the_device_default(entry, capsys):
    cfg = entry.resolve_run_config(device="mock", plugin_names=["NopePlugin"])

    assert cfg == entry.resolve_run_config(device="mock")
    assert "default 'mock' plugin set" in capsys.readouterr().err


def test_command_line_accepts_deferred_and_unknown_names(
    monkeypatch, new_consts, capsys
):
    main_calls = _install_fake_source(monkeypatch, new_consts)
    monkeypatch.setattr(
        sys,
        "argv",
        ["microdrop.py", "--plugins", "MicrodropPlugin", "ImageViewerPlugin", "Gone"],
    )

    runpy.run_path(str(ENTRY_PATH), run_name="__main__")

    [call] = main_calls
    assert new_consts.DEFERRED_FRONTEND_PLUGINS[0] in call["plugins"]
    assert "Gone" in capsys.readouterr().err


def test_help_lists_the_known_plugin_names(monkeypatch, new_consts, capsys):
    _install_fake_source(monkeypatch, new_consts)
    monkeypatch.setattr(sys, "argv", ["microdrop.py", "--help"])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(ENTRY_PATH), run_name="__main__")

    assert exit_info.value.code == 0
    assert "ImageViewerPlugin" in capsys.readouterr().out
