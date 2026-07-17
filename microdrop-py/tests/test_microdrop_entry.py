import pytest

import microdrop as entry
from examples.plugin_consts import (
    BACKEND_APPLICATION,
    BACKEND_PLUGINS,
    DROPBOT_BACKEND_PLUGINS,
    DROPBOT_FRONTEND_PLUGINS,
    FRONTEND_APPLICATION,
    FRONTEND_PLUGINS,
    REQUIRED_CONTEXT,
    REQUIRED_PLUGINS,
    SERVER_CONTEXT,
    SERVICE_PLUGINS,
)


def test_default_matches_full_dropbot_set():
    cfg = entry.resolve_run_config()
    expected = list(dict.fromkeys(
        REQUIRED_PLUGINS + FRONTEND_PLUGINS + DROPBOT_FRONTEND_PLUGINS
        + SERVICE_PLUGINS + BACKEND_PLUGINS + DROPBOT_BACKEND_PLUGINS))
    assert cfg["plugins"] == expected
    assert cfg["application"] is FRONTEND_APPLICATION
    assert cfg["persist"] is False
    assert cfg["contexts"] == SERVER_CONTEXT + REQUIRED_CONTEXT


def test_selection_is_reordered_to_consts_order():
    # Passed backend-first on purpose; load order must follow plugin_consts.
    cfg = entry.resolve_run_config(plugin_names=[
        "DropbotControllerPlugin", "DeviceViewerPlugin", "TasksPlugin"])
    optional = [p for p in cfg["plugins"] if p not in REQUIRED_PLUGINS]
    assert [p.__name__ for p in optional] == [
        "TasksPlugin", "DeviceViewerPlugin", "DropbotControllerPlugin"]
    assert cfg["plugins"][:len(REQUIRED_PLUGINS)] == REQUIRED_PLUGINS


def test_backend_only_selection_runs_headless():
    cfg = entry.resolve_run_config(plugin_names=[
        "ElectrodeControllerPlugin", "DropbotControllerPlugin"])
    assert cfg["application"] is BACKEND_APPLICATION
    assert cfg["persist"] is True
    assert cfg["contexts"] == REQUIRED_CONTEXT


def test_contexts_override_beats_inference():
    cfg = entry.resolve_run_config(context_names=["dramatiq_workers"])
    assert cfg["contexts"] == REQUIRED_CONTEXT


def test_unknown_plugin_raises():
    with pytest.raises(ValueError, match="NopePlugin"):
        entry.resolve_run_config(plugin_names=["NopePlugin"])


def test_unknown_context_raises():
    with pytest.raises(ValueError, match="nope_ctx"):
        entry.resolve_run_config(context_names=["nope_ctx"])
