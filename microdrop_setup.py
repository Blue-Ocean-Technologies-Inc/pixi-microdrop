#!/usr/bin/env python3
"""Standalone Microdrop setup & launcher.

Stage 1 (pre-install): clones pixi-microdrop, installs pixi if needed,
prefetches the env. Runs once; state lives in the user's appdata dir.
Stage 2 (launcher): per-plugin launch configuration, repo branch/update
settings, desktop shortcut creation. ``--launch`` runs the saved
configuration headlessly (what desktop shortcuts invoke).

Python stdlib only — this must run before any project environment exists.
"""
import argparse
import ast
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import webbrowser
from collections import namedtuple
from pathlib import Path

IS_WINDOWS = os.name == "nt"
PIXI_REPO_URL = "https://github.com/Blue-Ocean-Technologies-Inc/pixi-microdrop.git"
SRC_REPO_URL = "https://github.com/Blue-Ocean-Technologies-Inc/Microdrop.git"
PIXI_MANUAL_INSTALL_URL = "https://pixi.prefix.dev/latest/installation/"
REPO_DIR_NAME = "pixi-microdrop"
SCRIPT_NAME = "microdrop_setup.py"
PIXI_PROJECT_RELDIR = "microdrop-py"
SRC_RELDIR = Path("microdrop-py/src")
PLUGIN_CONSTS_RELPATH = Path("microdrop-py/src/examples/plugin_consts.py")
REDIS_SETTINGS_RELPATH = Path("microdrop-py/src/redis_settings.json")
DRAMATIQ_SETTINGS_RELPATH = Path("microdrop-py/src/dramatiq_settings.json")
ICON_RELPATH = Path("microdrop-py/src/microdrop_style/icons/Microdrop_Icon.ico")
ICON_PNG_RELPATH = Path("microdrop-py/src/microdrop_style/icons/Microdrop_Icon.png")

DEFAULT_CONFIG = {
    "install_dir": "",
    "pixi_repo_branch": "master",
    "src_repo_branch": "main",
    "auto_update_pixi_repo": True,
    "auto_update_src_repo": True,
    "device": "dropbot",
    "mode": "dual",      # "dual" | "frontend" | "backend"
    "advanced_mode": False,
    "redis_host": "127.0.0.1",
    "redis_port": 6379,
    "worker_threads": 4,   # dramatiq worker threads to spawn
    "worker_timeout": 100,  # ms workers wake up after if the queue is idle
    "plugins": [],       # optional-plugin class names; empty = full default set
    "contexts": [],      # empty = let examples.microdrop infer
    "preinstall_done": False,
}

# List variables parsed out of plugin_consts.py for the launcher UI.
PLUGIN_CONSTS_VARS = (
    "REQUIRED_PLUGINS",
    "FRONTEND_PLUGINS",
    "DROPBOT_FRONTEND_PLUGINS",
    "OPENDROP_FRONTEND_PLUGINS",
    "MOCK_DROPBOT_FRONTEND_PLUGINS",
    "SERVICE_PLUGINS",
    "BACKEND_PLUGINS",
    "DROPBOT_BACKEND_PLUGINS",
    "OPENDROP_BACKEND_PLUGINS",
    "MOCK_DROPBOT_BACKEND_PLUGINS",
)

# FRONTEND_PLUGINS entries that must load whenever the frontend runs
# (locked on outside advanced mode).
FRONTEND_MANDATORY_PLUGINS = ("MicrodropPlugin", "TasksPlugin")
# FRONTEND_PLUGINS entries with this class-name substring are grouped
# separately under "Protocol".
PROTOCOL_PLUGIN_NAME_MARKER = "Protocol"

# Which plugin sides each launch mode enables.
MODE_PLUGIN_SIDES = {
    "dual": {"frontend", "backend"},
    "frontend": {"frontend"},
    "backend": {"backend"},
}
MODE_LABELS = (
    ("dual", "Frontend + Backend"),
    ("frontend", "Frontend only"),
    ("backend", "Backend only"),
)

# side: "frontend" / "backend"; None = informational only (required plugins).
# devices: None = all devices.
DisplayGroup = namedtuple("DisplayGroup", "key title plugins side devices")


def build_display_groups(parsed):
    """Partition the parsed plugin_consts lists into launcher display groups."""
    frontend = parsed["FRONTEND_PLUGINS"]
    mandatory = [p for p in frontend if p in FRONTEND_MANDATORY_PLUGINS]
    protocol = [p for p in frontend
                if PROTOCOL_PLUGIN_NAME_MARKER in p and p not in mandatory]
    recommended = [p for p in frontend
                   if p not in mandatory and p not in protocol]
    return [
        DisplayGroup("required", "Required (always loaded)",
                     parsed["REQUIRED_PLUGINS"], None, None),
        DisplayGroup("frontend_core", "Frontend — core (required with frontend)",
                     mandatory, "frontend", None),
        DisplayGroup("frontend_recommended", "Frontend — recommended",
                     recommended, "frontend", None),
        DisplayGroup("protocol", "Protocol",
                     protocol, "frontend", None),
        DisplayGroup("dropbot_frontend", "DropBot frontend",
                     parsed["DROPBOT_FRONTEND_PLUGINS"], "frontend",
                     {"dropbot", "mock"}),
        DisplayGroup("opendrop_frontend", "OpenDrop frontend",
                     parsed["OPENDROP_FRONTEND_PLUGINS"], "frontend",
                     {"opendrop"}),
        DisplayGroup("mock_frontend", "Mock DropBot frontend",
                     parsed["MOCK_DROPBOT_FRONTEND_PLUGINS"], "frontend",
                     {"mock"}),
        DisplayGroup("services", "Services (run with the frontend)",
                     parsed["SERVICE_PLUGINS"], "frontend", None),
        DisplayGroup("backend", "Backend",
                     parsed["BACKEND_PLUGINS"], "backend", None),
        DisplayGroup("dropbot_backend", "DropBot backend",
                     parsed["DROPBOT_BACKEND_PLUGINS"], "backend", {"dropbot"}),
        DisplayGroup("opendrop_backend", "OpenDrop backend",
                     parsed["OPENDROP_BACKEND_PLUGINS"], "backend",
                     {"opendrop"}),
        DisplayGroup("mock_backend", "Mock DropBot backend",
                     parsed["MOCK_DROPBOT_BACKEND_PLUGINS"], "backend",
                     {"mock"}),
    ]


# --------------------------------------------------------------------------
# Config persistence
# --------------------------------------------------------------------------

# Machine-global keys never stored in a profile — always inherited from the
# global config so profiles stay portable and survive a missing install.
GLOBAL_ONLY_KEYS = ("install_dir", "preinstall_done")
# Dropdown entry that represents the global working config (no named profile).
DEFAULT_PROFILE_LABEL = "(default)"
# Characters not allowed in a profile name (filesystem- and PS-command-unsafe).
_INVALID_PROFILE_CHARS = '<>:"/\\|?*\''


def config_path():
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        return base / "Sci-Bots" / "Microdrop-Launch" / "setup_config.json"
    return Path.home() / ".config" / "microdrop_launch" / "setup_config.json"


def profiles_dir():
    return config_path().parent / "profiles"


def sanitize_profile_name(name):
    """Filesystem- and shell-safe form of a profile name (may be empty)."""
    return "".join(
        "_" if ch in _INVALID_PROFILE_CHARS else ch for ch in name).strip()


def profile_path(name):
    return profiles_dir() / f"{sanitize_profile_name(name)}.json"


def list_profiles():
    try:
        return sorted(path.stem for path in profiles_dir().glob("*.json"))
    except OSError:
        return []


def load_config(profile=None):
    """Load the global config, optionally overlaid with a named *profile*.

    A missing/corrupt profile falls back to just the global config, so a
    deleted profile still launches with sensible machine-global settings.
    """
    cfg = dict(DEFAULT_CONFIG)
    for path in (config_path(), profile_path(profile) if profile else None):
        if path is None:
            continue
        try:
            cfg.update(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # missing/corrupt -> keep what we have (=> pre-install runs)
    return cfg


def save_config(cfg, profile=None):
    """Persist *cfg* to the global config, or to a named *profile* file
    (profiles omit the machine-global keys)."""
    if profile:
        path = profile_path(profile)
        data = {k: v for k, v in cfg.items() if k not in GLOBAL_ONLY_KEYS}
    else:
        path = config_path()
        data = cfg
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def mark_preinstall_needed():
    """Flag the global config so the next run re-runs pre-install."""
    global_cfg = load_config()
    global_cfg["preinstall_done"] = False
    save_config(global_cfg)


def _needs_preinstall(cfg):
    if not cfg["preinstall_done"] or not cfg["install_dir"]:
        return True
    return not (Path(cfg["install_dir"]) / PIXI_PROJECT_RELDIR).is_dir()


# --------------------------------------------------------------------------
# Subprocess / tool discovery helpers
# --------------------------------------------------------------------------

def run_streamed(cmd, log, cwd=None):
    """Run *cmd*, streaming combined stdout/stderr lines through log()."""
    log(f"$ {' '.join(str(part) for part in cmd)}")
    try:
        proc = subprocess.Popen(
            [str(part) for part in cmd], cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace")
    except OSError as exc:
        log(f"ERROR: {exc}")
        return 1
    for line in proc.stdout:
        log(line.rstrip())
    return proc.wait()


def run_capture(cmd, cwd=None):
    """Run *cmd* silently; return (returncode, stdout)."""
    try:
        proc = subprocess.run(
            [str(part) for part in cmd], cwd=str(cwd) if cwd else None,
            capture_output=True, text=True, errors="replace")
    except OSError as exc:
        return 1, str(exc)
    return proc.returncode, proc.stdout


def find_git():
    return shutil.which("git")


def find_pixi():
    found = shutil.which("pixi")
    if found:
        return found
    # Default install location of the official installer (PATH only updates
    # in new shells, so a just-installed pixi is invisible to which()).
    candidate = Path.home() / ".pixi" / "bin" / ("pixi.exe" if IS_WINDOWS else "pixi")
    return str(candidate) if candidate.exists() else None


def auto_install_pixi(log):
    """Run the official pixi installer for this OS. True on success."""
    if IS_WINDOWS:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-Command", "iwr -useb https://pixi.sh/install.ps1 | iex"]
    else:
        cmd = ["sh", "-c", "curl -fsSL https://pixi.sh/install.sh | sh"]
    return run_streamed(cmd, log) == 0 and find_pixi() is not None


# --------------------------------------------------------------------------
# plugin_consts.py static parsing (no imports — the pixi env may not exist)
# --------------------------------------------------------------------------

def parse_plugin_groups(consts_path):
    """Map each PLUGIN_CONSTS_VARS name to its plugin class names via ast."""
    wanted = set(PLUGIN_CONSTS_VARS)
    tree = ast.parse(Path(consts_path).read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in wanted
                and isinstance(node.value, ast.List)):
            found[node.targets[0].id] = [
                elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
    return {name: found.get(name, []) for name in PLUGIN_CONSTS_VARS}


# --------------------------------------------------------------------------
# Git + launch
# --------------------------------------------------------------------------

def list_repo_branches(repo_dir):
    """Local + remote branch names for the checkout at *repo_dir*, deduped."""
    code, out = run_capture(
        ["git", "branch", "-a", "--format=%(refname:short)"], cwd=repo_dir)
    if code != 0:
        return []
    branches = []
    for line in out.splitlines():
        name = line.strip()
        if name.startswith("origin/"):
            name = name[len("origin/"):]
        # refname:short renders the origin/HEAD symref as just "origin".
        if name and name not in ("HEAD", "origin") and name not in branches:
            branches.append(name)
    return branches


def list_remote_branches(repo_url):
    """Branch names on *repo_url* via ls-remote (network call; may be slow)."""
    code, out = run_capture(["git", "ls-remote", "--heads", repo_url])
    if code != 0:
        return []
    branches = []
    for line in out.splitlines():
        _sha, _sep, ref = line.partition("refs/heads/")
        name = ref.strip()
        if name and name not in branches:
            branches.append(name)
    return branches


def git_update_repo(repo_dir, branch, log):
    """Best-effort checkout of *branch* (resolves detached HEAD) then pull.

    Failures are warnings — launching with the current checkout beats not
    launching (matches the old run_microdrop.ps1 behavior).
    """
    code, current = run_capture(["git", "branch", "--show-current"], cwd=repo_dir)
    if code != 0:
        log(f"Warning: {repo_dir} is not a usable git repo; skipping update.")
        return
    current = current.strip()
    if branch and current != branch:
        if run_streamed(["git", "checkout", branch], log, cwd=repo_dir) != 0:
            log(f"Warning: could not check out '{branch}' in {repo_dir}; "
                f"staying on '{current or 'detached HEAD'}'.")
    if run_streamed(["git", "pull"], log, cwd=repo_dir) != 0:
        log(f"Warning: could not pull {repo_dir}; continuing with current state.")


def _merge_settings_file(path, updates, log):
    """Update *path* (a flat json settings file) with *updates*, preserving
    any extra keys already present."""
    settings = {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            settings = loaded
    except (OSError, ValueError):
        pass  # missing/corrupt file -> rewrite from the saved config
    settings.update(updates)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    log(f"Wrote {path}")


def write_server_settings(cfg, log):
    """Write redis + dramatiq worker settings where the app reads them.

    Both files in the source tree are gitignored host-specific config.
    """
    if not (Path(cfg["install_dir"]) / SRC_RELDIR).is_dir():
        log("Warning: source tree missing; skipping server settings write.")
        return
    _merge_settings_file(
        Path(cfg["install_dir"]) / REDIS_SETTINGS_RELPATH,
        {"host": cfg["redis_host"], "port": cfg["redis_port"]}, log)
    _merge_settings_file(
        Path(cfg["install_dir"]) / DRAMATIQ_SETTINGS_RELPATH,
        {"worker_threads": cfg["worker_threads"],
         "worker_timeout": cfg["worker_timeout"]}, log)


def build_run_args(cfg):
    run_args = ["--device", cfg["device"]]
    if cfg["plugins"]:
        run_args += ["--plugins", *cfg["plugins"]]
    if cfg["contexts"]:
        run_args += ["--contexts", *cfg["contexts"]]
    return run_args


def do_launch(cfg, log=print):
    """Run the saved configuration. False if the install dir is gone."""
    install_dir = Path(cfg["install_dir"])
    if not (install_dir / PIXI_PROJECT_RELDIR).is_dir():
        return False

    pixi = find_pixi()
    if pixi:
        # A just-auto-installed pixi is not on PATH in this process yet, and
        # the launch_microdrop.* scripts require it there.
        os.environ["PATH"] = (str(Path(pixi).parent) + os.pathsep
                              + os.environ.get("PATH", ""))
        if run_streamed([pixi, "self-update"], log) != 0:
            log("Warning: pixi self-update failed. "
                "Continuing with the current version...")
    else:
        log("Warning: pixi not found; the launcher script will report the error.")

    if cfg["auto_update_pixi_repo"]:
        git_update_repo(install_dir, cfg["pixi_repo_branch"], log)
    if cfg["auto_update_src_repo"]:
        git_update_repo(install_dir / SRC_RELDIR, cfg["src_repo_branch"], log)

    write_server_settings(cfg, log)

    run_args = build_run_args(cfg)
    if IS_WINDOWS:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(install_dir / "launch_microdrop.ps1"), *run_args]
    else:
        cmd = ["bash", str(install_dir / "launch_microdrop.sh"), *run_args]
    run_streamed(cmd, log)
    return True


# --------------------------------------------------------------------------
# Desktop shortcuts
# --------------------------------------------------------------------------

def desktop_dir():
    if IS_WINDOWS:
        # Resolve via the shell API — the Desktop is often redirected
        # (OneDrive), so %USERPROFILE%\Desktop is only a fallback.
        code, out = run_capture([
            "powershell", "-NoProfile", "-Command",
            "[Environment]::GetFolderPath('Desktop')"])
        if code == 0 and out.strip():
            return Path(out.strip())
    return Path.home() / "Desktop"


def shortcut_path(name):
    return desktop_dir() / (f"{name}.lnk" if IS_WINDOWS else f"{name}.desktop")


def create_shortcut(cfg, name, profile=None):
    """Create/overwrite a desktop shortcut launching *profile*; return its path.

    When *profile* is given the shortcut runs ``--launch --profile <profile>``
    so each shortcut carries its own saved configuration.
    """
    install_dir = Path(cfg["install_dir"])
    script = install_dir / SCRIPT_NAME
    path = shortcut_path(name)
    profile_arg = f" --profile \"{profile}\"" if profile else ""
    if IS_WINDOWS:
        icon = install_dir / ICON_RELPATH
        ps = (
            "$W = New-Object -ComObject WScript.Shell; "
            f"$S = $W.CreateShortcut('{path}'); "
            f"$S.TargetPath = '{sys.executable}'; "
            f"$S.Arguments = '\"{script}\" --launch{profile_arg}'; "
            f"$S.WorkingDirectory = '{install_dir}'; "
            f"$S.IconLocation = '{icon}'; "
            "$S.Save()"
        )
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    else:
        # Prefer the .png where present — many Linux desktops won't render
        # .ico — otherwise fall back to the requested .ico.
        icon = install_dir / ICON_PNG_RELPATH
        if not icon.exists():
            icon = install_dir / ICON_RELPATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={name}\n"
            f'Exec={sys.executable} "{script}" --launch{profile_arg}\n'
            f"Icon={icon}\n"
            "Terminal=true\n",
            encoding="utf-8")
        path.chmod(0o755)
    return path


# --------------------------------------------------------------------------
# GUI (tkinter imports stay function-local so --launch works without Tk)
# --------------------------------------------------------------------------

class LogPane:
    """Thread-safe scrolled log: worker threads call it, the GUI polls."""

    def __init__(self, parent, height=18):
        import tkinter as tk
        self._tcl_error = tk.TclError
        self.queue = queue.Queue()
        self.text = tk.Text(parent, height=height, width=100, state="disabled")
        self.text.pack(fill="both", expand=True, padx=8, pady=8)
        self._poll()

    def __call__(self, line):
        self.queue.put(str(line))

    def _poll(self):
        try:
            while True:
                line = self.queue.get_nowait()
                self.text.configure(state="normal")
                self.text.insert("end", f"{line}\n")
                self.text.see("end")
                self.text.configure(state="disabled")
        except queue.Empty:
            pass
        except self._tcl_error:
            return  # widget destroyed (e.g. Back to configuration) — stop polling
        self.text.after(100, self._poll)


def populate_branch_choices(combobox, local_repo_dir, remote_url):
    """Fill a read-only branch *combobox* without blocking the GUI.

    The current selection and the local checkout's branches (when
    *local_repo_dir* holds one) appear immediately; branches on the remote
    are fetched with ls-remote on a worker thread and merged in on arrival.
    """
    import tkinter as tk
    branches = []
    if combobox.get():
        branches.append(combobox.get())
    if local_repo_dir is not None:
        branches += [name for name in list_repo_branches(local_repo_dir)
                     if name not in branches]
    combobox["values"] = branches

    def fetch_remote():
        remote = list_remote_branches(remote_url)
        if not remote:
            return

        def merge():
            try:
                existing = list(combobox["values"])
                combobox["values"] = existing + [
                    name for name in remote if name not in existing]
            except tk.TclError:
                pass  # combobox destroyed while the merge was queued

        try:
            combobox.after(0, merge)
        except (RuntimeError, tk.TclError):
            pass  # window closed before the remote list arrived

    threading.Thread(target=fetch_remote, daemon=True).start()


class ScrollableFrame:
    """Vertically scrollable container; pack content into ``.inner``."""

    def __init__(self, parent):
        import tkinter as tk
        from tkinter import ttk
        self._tcl_error = tk.TclError
        self.container = ttk.Frame(parent)
        self.canvas = tk.Canvas(self.container, highlightthickness=0,
                                borderwidth=0)
        scrollbar = ttk.Scrollbar(self.container, orient="vertical",
                                  command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda _e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")))
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        # Windows/macOS deliver <MouseWheel>; X11 delivers Button-4/5.
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.bind_all(sequence, self._on_mousewheel)

    def _on_mousewheel(self, event):
        step = {4: -1, 5: 1}.get(event.num, 0) or (-1 if event.delta > 0 else 1)
        try:
            self.canvas.yview_scroll(step, "units")
        except self._tcl_error:
            pass  # canvas destroyed (e.g. after Launch swapped in the log pane)


class CollapsibleGroup:
    """Collapsible titled section with an optional select-all checkbox."""

    def __init__(self, parent, title, select_all_command=None, collapsed=False):
        import tkinter as tk
        from tkinter import ttk
        self.frame = ttk.Frame(parent, relief="groove", borderwidth=1,
                               padding=2)
        header = ttk.Frame(self.frame)
        header.pack(fill="x")
        self.collapsed = collapsed
        self._arrow = ttk.Label(header, width=2, cursor="hand2")
        self._arrow.pack(side="left")
        title_label = ttk.Label(header, text=title, cursor="hand2")
        title_label.pack(side="left")
        self.select_all_var = tk.BooleanVar(value=True)
        self.select_all_button = None
        if select_all_command is not None:
            self.select_all_button = ttk.Checkbutton(
                header, text="all", variable=self.select_all_var,
                command=select_all_command)
            self.select_all_button.pack(side="right")
        self.body = ttk.Frame(self.frame, padding=(16, 0, 2, 2))
        for widget in (self._arrow, title_label):
            widget.bind("<Button-1>", self.toggle_collapsed)
        self._apply_collapsed()

    def toggle_collapsed(self, _event=None):
        self.collapsed = not self.collapsed
        self._apply_collapsed()

    def _apply_collapsed(self):
        self._arrow.configure(text="▶" if self.collapsed else "▼")
        if self.collapsed:
            self.body.pack_forget()
        else:
            self.body.pack(fill="x")


class PreInstallWizard:
    """Stage 1: choose install dir + branches, clone, pixi install."""

    def __init__(self, root, cfg, on_done):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
        self.root, self.cfg, self.on_done = root, cfg, on_done
        self.filedialog, self.messagebox = filedialog, messagebox

        root.title("Microdrop Setup")
        self.frame = ttk.Frame(root, padding=12)
        self.frame.pack(fill="both", expand=True)

        self.dir_var = tk.StringVar(
            value=cfg["install_dir"] or str(Path.home() / REPO_DIR_NAME))
        self.pixi_branch_var = tk.StringVar(value=cfg["pixi_repo_branch"])
        self.src_branch_var = tk.StringVar(value=cfg["src_repo_branch"])

        form = ttk.Frame(self.frame)
        form.pack(fill="x")
        ttk.Label(form, text="Install Microdrop into:").grid(
            row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.dir_var, width=60).grid(
            row=0, column=1, padx=4)
        ttk.Button(form, text="Browse…", command=self._browse).grid(
            row=0, column=2)
        install_dir = Path(self.dir_var.get())
        has_checkout = (install_dir / ".git").exists()
        branch_rows = (
            (1, "pixi-microdrop branch:", self.pixi_branch_var,
             install_dir if has_checkout else None, PIXI_REPO_URL),
            (2, "Microdrop source branch:", self.src_branch_var,
             install_dir / SRC_RELDIR if has_checkout else None, SRC_REPO_URL))
        for row, label, branch_var, repo_dir, repo_url in branch_rows:
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w")
            branch_box = ttk.Combobox(form, textvariable=branch_var,
                                      state="readonly")
            branch_box.grid(row=row, column=1, sticky="w", padx=4)
            ttk.Button(form, text="⟳", width=3,
                       command=lambda box=branch_box, box_repo_dir=repo_dir,
                       box_repo_url=repo_url: populate_branch_choices(
                           box, box_repo_dir, box_repo_url)).grid(
                row=row, column=2, sticky="w")
            populate_branch_choices(branch_box, repo_dir, repo_url)

        self.install_btn = ttk.Button(
            self.frame, text="Install", command=self._start)
        self.install_btn.pack(pady=6)
        self.log = LogPane(self.frame)

    def _browse(self):
        chosen = self.filedialog.askdirectory(parent=self.root)
        if chosen:
            chosen = Path(chosen)
            if chosen.name != REPO_DIR_NAME:
                chosen = chosen / REPO_DIR_NAME
            self.dir_var.set(str(chosen))

    def _start(self):
        if not find_git():
            self.messagebox.showerror(
                "Git required",
                "Git was not found on PATH.\n\nInstall it (e.g. from "
                "https://git-scm.com/downloads), then press Install again.",
                parent=self.root)
            return
        if not find_pixi():
            auto = self.messagebox.askyesno(
                "Pixi not found",
                "Pixi is not installed.\n\n"
                "Yes — auto-install it now with the official installer.\n"
                "No — open the manual install guide in your browser; press "
                "Install again once pixi is installed.",
                parent=self.root)
            if not auto:
                webbrowser.open(PIXI_MANUAL_INSTALL_URL)
                return
        self.install_btn.configure(state="disabled")
        threading.Thread(target=self._steps, daemon=True).start()

    def _fail(self, message):
        self.log(f"ERROR: {message}")

        def show():
            self.install_btn.configure(state="normal")
            self.messagebox.showerror("Setup failed", message, parent=self.root)

        self.root.after(0, show)

    def _steps(self):
        log = self.log
        try:
            if not find_pixi():
                log("Installing pixi…")
                if not auto_install_pixi(log):
                    webbrowser.open(PIXI_MANUAL_INSTALL_URL)
                    self._fail(
                        "Pixi auto-install failed — install it manually from "
                        "the guide just opened, then press Install again.")
                    return

            install_dir = Path(self.dir_var.get()).expanduser()
            if (install_dir / ".git").exists():
                log("Existing checkout detected — skipping clone.")
            else:
                install_dir.parent.mkdir(parents=True, exist_ok=True)
                if run_streamed(["git", "clone", "--recurse-submodules",
                                 PIXI_REPO_URL, str(install_dir)], log) != 0:
                    self._fail("git clone failed — see log.")
                    return

            for repo_dir, branch in (
                    (install_dir, self.pixi_branch_var.get().strip()),
                    (install_dir / SRC_RELDIR, self.src_branch_var.get().strip())):
                if branch and run_streamed(
                        ["git", "checkout", branch], log, cwd=repo_dir) != 0:
                    self._fail(f"Could not check out '{branch}' in {repo_dir}.")
                    return

            if run_streamed([find_pixi(), "install"], log,
                            cwd=install_dir / PIXI_PROJECT_RELDIR) != 0:
                self._fail("pixi install failed — see log.")
                return

            target = install_dir / SCRIPT_NAME
            script = Path(__file__).resolve()
            if target.resolve() != script:
                shutil.copyfile(script, target)
                log(f"Copied setup script to {target}")

            self.cfg.update(
                install_dir=str(install_dir),
                pixi_repo_branch=self.pixi_branch_var.get().strip() or "master",
                src_repo_branch=self.src_branch_var.get().strip() or "main",
                preinstall_done=True)
            save_config(self.cfg)
            log("Pre-install complete.")
            self.root.after(0, self._finish)
        except Exception as exc:
            self._fail(str(exc))

    def _finish(self):
        self.frame.destroy()
        self.on_done()


class LauncherWindow:
    """Stage 2: mode/device/plugin/context selection, repo settings, actions.

    Plugin groups are gated by launch mode (frontend / backend / dual) and
    device; Options > Advanced mode unlocks every gated checkbox.
    """

    def __init__(self, root, cfg, profile=None):
        import tkinter as tk
        from tkinter import messagebox, simpledialog, ttk
        self.root, self.cfg = root, cfg
        self.profile = profile  # active profile name, or None for (default)
        self.messagebox, self.simpledialog = messagebox, simpledialog

        root.title("Microdrop Launcher")
        root.geometry("900x780")
        root.minsize(700, 500)
        self.frame = ttk.Frame(root, padding=12)
        self.frame.pack(fill="both", expand=True)

        consts_path = Path(cfg["install_dir"]) / PLUGIN_CONSTS_RELPATH
        try:
            parsed = parse_plugin_groups(consts_path)
        except (OSError, SyntaxError) as exc:
            messagebox.showerror(
                "Microdrop", f"Could not read {consts_path}: {exc}",
                parent=root)
            parsed = {name: [] for name in PLUGIN_CONSTS_VARS}
        self.display_groups = build_display_groups(parsed)

        # Options menu — advanced mode unlocks every gated checkbox
        self.advanced_var = tk.BooleanVar(value=cfg["advanced_mode"])
        menubar = tk.Menu(root)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_checkbutton(
            label="Advanced mode (toggle every plugin)",
            variable=self.advanced_var, command=self._apply_gating)
        menubar.add_cascade(label="Options", menu=options_menu)
        root.configure(menu=menubar)

        # Actions stay pinned at the bottom; the tabs fill everything above.
        buttons_row = ttk.Frame(self.frame)
        buttons_row.pack(side="bottom", pady=6)
        ttk.Button(buttons_row, text="Launch",
                   command=self._launch).pack(side="left", padx=4)
        ttk.Button(buttons_row, text="Create Desktop Shortcut",
                   command=self._create_shortcut).pack(side="left", padx=4)
        ttk.Button(buttons_row, text="Save & Close",
                   command=self._save_close).pack(side="left", padx=4)

        # Profile bar — pick a saved config profile; each shortcut gets one.
        profile_bar = ttk.Frame(self.frame)
        profile_bar.pack(side="top", fill="x", pady=(0, 4))
        ttk.Label(profile_bar, text="Profile:").pack(side="left")
        self.profile_var = tk.StringVar(
            value=self.profile or DEFAULT_PROFILE_LABEL)
        self.profile_combo = ttk.Combobox(
            profile_bar, textvariable=self.profile_var, state="readonly",
            width=24, values=[DEFAULT_PROFILE_LABEL] + list_profiles())
        self.profile_combo.pack(side="left", padx=4)
        self.profile_combo.bind("<<ComboboxSelected>>", self._on_profile_selected)
        self.shortcut_status_var = tk.StringVar()
        ttk.Label(profile_bar, textvariable=self.shortcut_status_var,
                  foreground="gray40").pack(side="left", padx=8)

        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill="both", expand=True, pady=6)
        launch_tab = ttk.Frame(notebook)
        notebook.add(launch_tab, text="Launch")
        git_tab = ttk.Frame(notebook, padding=8)
        notebook.add(git_tab, text="Git settings")
        server_tab = ttk.Frame(notebook, padding=8)
        notebook.add(server_tab, text="Server Settings")

        self.scroll = ScrollableFrame(launch_tab)
        self.scroll.container.pack(fill="both", expand=True)
        content = self.scroll.inner

        # Mode
        self.mode_var = tk.StringVar(value=cfg["mode"])
        mode_row = ttk.Frame(content)
        mode_row.pack(fill="x", pady=(4, 0))
        ttk.Label(mode_row, text="Mode:").pack(side="left")
        for value, label in MODE_LABELS:
            ttk.Radiobutton(mode_row, text=label, value=value,
                            variable=self.mode_var,
                            command=self._apply_gating).pack(side="left", padx=4)

        # Device
        self.device_var = tk.StringVar(value=cfg["device"])
        device_row = ttk.Frame(content)
        device_row.pack(fill="x", pady=(0, 4))
        ttk.Label(device_row, text="Device:").pack(side="left")
        for device in ("dropbot", "opendrop", "mock"):
            ttk.Radiobutton(device_row, text=device, value=device,
                            variable=self.device_var,
                            command=self._apply_gating).pack(side="left", padx=4)

        # Plugin groups: frontend column | backend column, collapsible,
        # each with a select-all checkbox.
        self.plugin_vars = {}    # plugin name -> BooleanVar (shared if reused)
        self.group_sections = {}  # group key -> CollapsibleGroup
        self.group_buttons = {}   # group key -> [(plugin name, Checkbutton)]
        stored = set(cfg["plugins"])
        use_stored = bool(cfg["plugins"])
        columns_frame = ttk.Frame(content)
        columns_frame.pack(fill="x")
        columns = []
        for index in range(2):
            column = ttk.Frame(columns_frame)
            column.grid(row=0, column=index, sticky="new", padx=4)
            columns_frame.columnconfigure(index, weight=1, uniform="plugins")
            columns.append(column)
        for group in self.display_groups:
            column = columns[1 if group.side == "backend" else 0]
            section = CollapsibleGroup(
                column, group.title,
                select_all_command=(
                    None if group.side is None
                    else lambda key=group.key: self._toggle_group(key)),
                collapsed=group.key == "required")
            section.frame.pack(fill="x", pady=2)
            buttons = []
            for plugin in group.plugins:
                if group.side is None:
                    var = tk.BooleanVar(value=True)
                else:
                    var = self.plugin_vars.setdefault(plugin, tk.BooleanVar(
                        value=True if not use_stored else plugin in stored))
                    var.trace_add(
                        "write",
                        lambda *_a, key=group.key: self._sync_select_all(key))
                button = ttk.Checkbutton(section.body, text=plugin,
                                         variable=var)
                button.pack(anchor="w")
                buttons.append((plugin, button))
            self.group_sections[group.key] = section
            self.group_buttons[group.key] = buttons
            self._sync_select_all(group.key)

        # Contexts
        ctx_box = ttk.LabelFrame(content, text="Contexts", padding=4)
        ctx_box.pack(fill="x", pady=2)
        self.ctx_auto_var = tk.BooleanVar(value=not cfg["contexts"])
        self.ctx_vars = {name: tk.BooleanVar(value=name in cfg["contexts"])
                         for name in ("redis_server", "dramatiq_workers")}
        ttk.Checkbutton(ctx_box, text="Auto (recommended)",
                        variable=self.ctx_auto_var,
                        command=self._apply_ctx_mode).pack(anchor="w")
        self.ctx_buttons = [
            ttk.Checkbutton(ctx_box, text=name, variable=var)
            for name, var in self.ctx_vars.items()]
        for btn in self.ctx_buttons:
            btn.pack(anchor="w")

        # Git settings tab
        ttk.Label(
            git_tab,
            text="Note: if you have external plugins installed, changing the "
                 "pixi-microdrop repo (branch switch, pull, or reset) may "
                 "require reinstalling those plugins.",
            foreground="#b00").pack(anchor="w", pady=(0, 6))

        # Repositories
        repo_box = ttk.LabelFrame(git_tab, text="Repositories", padding=4)
        repo_box.pack(fill="x", anchor="n", pady=2)
        self.pixi_branch_var = tk.StringVar(value=cfg["pixi_repo_branch"])
        self.src_branch_var = tk.StringVar(value=cfg["src_repo_branch"])
        self.update_pixi_var = tk.BooleanVar(value=cfg["auto_update_pixi_repo"])
        self.update_src_var = tk.BooleanVar(value=cfg["auto_update_src_repo"])
        install_dir = Path(cfg["install_dir"])
        rows = (("pixi-microdrop", self.pixi_branch_var, self.update_pixi_var,
                 install_dir, PIXI_REPO_URL),
                ("Microdrop source", self.src_branch_var, self.update_src_var,
                 install_dir / SRC_RELDIR, SRC_REPO_URL))
        for row, (label, branch_var, update_var, repo_dir,
                  repo_url) in enumerate(rows):
            ttk.Label(repo_box, text=f"{label} branch:").grid(
                row=row, column=0, sticky="w")
            branch_box = ttk.Combobox(repo_box, textvariable=branch_var,
                                      state="readonly")
            branch_box.grid(row=row, column=1, padx=4)
            ttk.Button(repo_box, text="⟳", width=3,
                       command=lambda box=branch_box, box_repo_dir=repo_dir,
                       box_repo_url=repo_url: populate_branch_choices(
                           box, box_repo_dir, box_repo_url)).grid(
                row=row, column=2, sticky="w", padx=(0, 4))
            populate_branch_choices(branch_box, repo_dir, repo_url)
            ttk.Checkbutton(repo_box, text="update on launch",
                            variable=update_var).grid(row=row, column=3)

        # Repository maintenance — discard/stash local changes per repo
        maint_box = ttk.LabelFrame(git_tab, text="Repository maintenance",
                                   padding=4)
        maint_box.pack(fill="x", anchor="n", pady=2)
        maint_repos = (("pixi-microdrop", install_dir),
                       ("Microdrop source", install_dir / SRC_RELDIR))
        for row, (label, repo_dir) in enumerate(maint_repos):
            ttk.Label(maint_box, text=f"{label}:").grid(
                row=row, column=0, sticky="w", padx=(0, 4))
            ttk.Button(
                maint_box, text="Reset (discard changes)",
                command=lambda name=label, path=repo_dir: self._git_maintenance(
                    name, path, ["reset", "--hard"],
                    confirm=f"Discard ALL uncommitted changes in {name} "
                            f"(git reset --hard)?\n\nThis cannot be undone.")
            ).grid(row=row, column=1, padx=2, pady=1)
            ttk.Button(
                maint_box, text="Stash",
                command=lambda name=label, path=repo_dir: self._git_maintenance(
                    name, path, ["stash", "push", "--include-untracked"])
            ).grid(row=row, column=2, padx=2, pady=1)
            ttk.Button(
                maint_box, text="Stash pop",
                command=lambda name=label, path=repo_dir: self._git_maintenance(
                    name, path, ["stash", "pop"])
            ).grid(row=row, column=3, padx=2, pady=1)
            ttk.Button(
                maint_box, text="Pull",
                command=lambda name=label, path=repo_dir: self._git_maintenance(
                    name, path, ["pull"])
            ).grid(row=row, column=4, padx=2, pady=1)
        ttk.Label(git_tab, text="Git output:").pack(anchor="w", pady=(6, 0))
        self.git_log = LogPane(git_tab, height=8)

        # Server Settings tab — written to src/redis_settings.json at launch
        self.redis_host_var = tk.StringVar(value=cfg["redis_host"])
        self.redis_port_var = tk.StringVar(value=str(cfg["redis_port"]))
        self.worker_threads_var = tk.StringVar(value=str(cfg["worker_threads"]))
        self.worker_timeout_var = tk.StringVar(value=str(cfg["worker_timeout"]))
        self._validate_int_command = (
            root.register(lambda text: text == "" or text.isdigit()), "%P")

        redis_section = CollapsibleGroup(server_tab, "Redis server")
        redis_section.frame.pack(fill="x", pady=2)
        ttk.Label(redis_section.body,
                  text="Connection for the Redis message server. Saved to "
                       "src/redis_settings.json at launch; the app falls back "
                       "to 127.0.0.1:6379 without it.",
                  foreground="gray40", wraplength=560).pack(anchor="w")
        self._add_server_setting(
            redis_section.body, "host (str):", self.redis_host_var,
            "Hostname or IP address of the Redis server (localhost, LAN, "
            "or cloud).")
        self._add_server_setting(
            redis_section.body, "port (int):", self.redis_port_var,
            "TCP port the Redis server listens on.", int_only=True)

        dramatiq_section = CollapsibleGroup(server_tab, "Dramatiq broker")
        dramatiq_section.frame.pack(fill="x", pady=2)
        ttk.Label(dramatiq_section.body,
                  text="Dramatiq worker options. Saved to "
                       "src/dramatiq_settings.json at launch; the app falls "
                       "back to 4 threads / 100 ms without it.",
                  foreground="gray40", wraplength=560).pack(anchor="w")
        self._add_server_setting(
            dramatiq_section.body, "worker_threads (int):",
            self.worker_threads_var,
            "The number of worker threads to spawn.", int_only=True)
        self._add_server_setting(
            dramatiq_section.body, "worker_timeout (int):",
            self.worker_timeout_var,
            "The number of milliseconds workers should wake up after if the "
            "queue is idle.", int_only=True)

        self._apply_gating()
        self._apply_ctx_mode()
        self._refresh_shortcut_status()

    def _refresh_shortcut_status(self):
        if self.profile is None:
            self.shortcut_status_var.set(
                "default config — create a shortcut to save it as a profile")
        elif shortcut_path(self.profile).exists():
            self.shortcut_status_var.set(
                f"✓ desktop shortcut exists for '{self.profile}'")
        else:
            self.shortcut_status_var.set(
                f"no desktop shortcut for '{self.profile}' yet")

    def _refresh_profiles(self):
        self.profile_combo["values"] = (
            [DEFAULT_PROFILE_LABEL] + list_profiles())
        self.profile_var.set(self.profile or DEFAULT_PROFILE_LABEL)
        self._refresh_shortcut_status()

    def _on_profile_selected(self, _event=None):
        chosen = self.profile_var.get()
        target = None if chosen == DEFAULT_PROFILE_LABEL else chosen
        if target == self.profile:
            return
        self._save()  # persist current edits to their own target first
        self._rebuild(load_config(target), target)

    def _rebuild(self, cfg, profile):
        self.root.configure(menu="")
        self.frame.destroy()
        LauncherWindow(self.root, cfg, profile=profile)

    def _add_server_setting(self, body, label_text, var, description,
                            int_only=False):
        from tkinter import ttk
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(4, 0))
        ttk.Label(row, text=label_text).pack(side="left")
        entry_kwargs = ({"validate": "key",
                         "validatecommand": self._validate_int_command}
                        if int_only else {})
        ttk.Entry(row, textvariable=var, width=18, **entry_kwargs).pack(
            side="left", padx=4)
        ttk.Label(body, text=description, foreground="gray40",
                  wraplength=560).pack(anchor="w", padx=(16, 0))

    def _group_active(self, group):
        """Whether *group*'s plugins count toward the launch selection."""
        if group.side is None:
            return False  # required plugins are always loaded, never editable
        if self.advanced_var.get():
            return True
        if group.side not in MODE_PLUGIN_SIDES[self.mode_var.get()]:
            return False
        return not group.devices or self.device_var.get() in group.devices

    def _apply_gating(self):
        advanced = self.advanced_var.get()
        for group in self.display_groups:
            active = self._group_active(group)
            lock_mandatory = group.key == "frontend_core" and not advanced
            if lock_mandatory:
                # Locked state mirrors reality: checked exactly when the
                # frontend (and thus the mandatory plugins) will load.
                for plugin, _button in self.group_buttons[group.key]:
                    self.plugin_vars[plugin].set(active)
            state = "normal" if active and not lock_mandatory else "disabled"
            for _plugin, button in self.group_buttons[group.key]:
                button.configure(state=state)
            select_all_button = self.group_sections[group.key].select_all_button
            if select_all_button is not None:
                select_all_button.configure(state=state)

    def _toggle_group(self, group_key):
        value = self.group_sections[group_key].select_all_var.get()
        for plugin, _button in self.group_buttons[group_key]:
            self.plugin_vars[plugin].set(value)

    def _sync_select_all(self, group_key):
        section = self.group_sections.get(group_key)
        if section is None or section.select_all_button is None:
            return
        buttons = self.group_buttons[group_key]
        section.select_all_var.set(
            bool(buttons)
            and all(self.plugin_vars[plugin].get() for plugin, _b in buttons))

    def _apply_ctx_mode(self):
        state = "disabled" if self.ctx_auto_var.get() else "normal"
        for btn in self.ctx_buttons:
            btn.configure(state=state)

    def _selected_plugins(self):
        plugins = []
        for group in self.display_groups:
            if not self._group_active(group):
                continue
            for plugin in group.plugins:
                var = self.plugin_vars.get(plugin)
                if var is not None and var.get() and plugin not in plugins:
                    plugins.append(plugin)
        return plugins

    @staticmethod
    def _int_setting(var, default):
        text = var.get().strip()
        return max(1, int(text)) if text.isdigit() else default

    def _save(self):
        self.cfg.update(
            mode=self.mode_var.get(),
            advanced_mode=self.advanced_var.get(),
            device=self.device_var.get(),
            plugins=self._selected_plugins(),
            contexts=[] if self.ctx_auto_var.get() else [
                name for name, var in self.ctx_vars.items() if var.get()],
            pixi_repo_branch=self.pixi_branch_var.get().strip() or "master",
            src_repo_branch=self.src_branch_var.get().strip() or "main",
            auto_update_pixi_repo=self.update_pixi_var.get(),
            auto_update_src_repo=self.update_src_var.get(),
            redis_host=self.redis_host_var.get().strip()
                or DEFAULT_CONFIG["redis_host"],
            redis_port=self._int_setting(
                self.redis_port_var, DEFAULT_CONFIG["redis_port"]),
            worker_threads=self._int_setting(
                self.worker_threads_var, DEFAULT_CONFIG["worker_threads"]),
            worker_timeout=self._int_setting(
                self.worker_timeout_var, DEFAULT_CONFIG["worker_timeout"]))
        save_config(self.cfg, self.profile)

    def _git_maintenance(self, name, repo_dir, git_args, confirm=None):
        """Run a maintenance git command against *repo_dir*, streaming to the
        Git-tab output pane on a worker thread."""
        if confirm and not self.messagebox.askyesno(
                "Confirm", confirm, parent=self.root):
            return
        if not Path(repo_dir).is_dir():
            self.git_log(f"[{name}] {repo_dir} not found — is it installed?")
            return

        def worker():
            self.git_log(f"[{name}] git {' '.join(git_args)}")
            run_streamed(["git", *git_args], self.git_log, cwd=repo_dir)

        threading.Thread(target=worker, daemon=True).start()

    def _launch(self):
        from tkinter import ttk
        self._save()
        if not self.cfg["plugins"]:
            self.messagebox.showerror(
                "Microdrop",
                "No plugins selected — enable at least one plugin for the "
                "chosen mode before launching.", parent=self.root)
            return
        self.root.configure(menu="")
        self.frame.destroy()
        self.root.title("Microdrop — launching…")

        launch_frame = ttk.Frame(self.root, padding=12)
        launch_frame.pack(fill="both", expand=True)
        ttk.Button(launch_frame, text="← Back to configuration",
                   command=lambda: self._back_to_config(launch_frame)).pack(
            anchor="w")
        ttk.Label(
            launch_frame,
            text="Microdrop runs in a separate process; closing it or coming "
                 "back here does not stop it.",
            foreground="gray40").pack(anchor="w", pady=(2, 4))
        log = LogPane(launch_frame)

        def worker():
            if not do_launch(self.cfg, log):
                mark_preinstall_needed()
                log("Install directory missing — run this script again "
                    "to reinstall.")

        threading.Thread(target=worker, daemon=True).start()

    def _back_to_config(self, launch_frame):
        launch_frame.destroy()
        LauncherWindow(self.root, self.cfg, profile=self.profile)

    def _create_shortcut(self):
        self._save()
        name = self.profile or "Microdrop"
        while True:
            name = self.simpledialog.askstring(
                "Shortcut & profile name",
                "Name for this config profile and its desktop shortcut:",
                initialvalue=name, parent=self.root)
            if not name:
                return
            name = sanitize_profile_name(name)
            if not name:
                self.messagebox.showerror(
                    "Invalid name", "Please enter a valid profile name.",
                    parent=self.root)
                continue
            existing = shortcut_path(name)
            if existing.exists() and not self.messagebox.askyesno(
                    "Shortcut exists",
                    f"'{existing.name}' already exists on the Desktop.\n\n"
                    "Replace it? (No — choose another name)",
                    parent=self.root):
                continue
            break
        # Save the current configuration as this named profile, then point a
        # shortcut at it so it launches with exactly this config.
        self.profile = name
        save_config(self.cfg, name)
        try:
            created = create_shortcut(self.cfg, name, profile=name)
        except (OSError, subprocess.CalledProcessError) as exc:
            self.messagebox.showerror(
                "Shortcut failed", str(exc), parent=self.root)
            return
        self._refresh_profiles()
        self.messagebox.showinfo(
            "Shortcut created",
            f"Created {created}.\nIt launches the '{name}' profile. Edit this "
            "profile here and recreate the shortcut to update it.",
            parent=self.root)

    def _save_close(self):
        self._save()
        self.root.destroy()


def run_gui(cfg, profile=None):
    import tkinter as tk
    root = tk.Tk()

    def open_launcher():
        LauncherWindow(root, cfg, profile=profile)

    if _needs_preinstall(cfg):
        PreInstallWizard(root, cfg, on_done=open_launcher)
    else:
        open_launcher()
    root.mainloop()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Standalone Microdrop setup & launcher.")
    parser.add_argument(
        "--launch", action="store_true",
        help="Launch the saved configuration without the GUI (what desktop "
             "shortcuts run).")
    parser.add_argument(
        "--profile", metavar="NAME",
        help="Named config profile to load (per-shortcut configs). Falls back "
             "to the global config when the profile is missing.")
    args = parser.parse_args(argv)

    cfg = load_config(args.profile)
    if args.launch:
        if not _needs_preinstall(cfg):
            do_launch(cfg)
            try:
                input("Done. Press Enter to exit…")
            except (EOFError, RuntimeError):
                pass
            return
        # Appdata/install dir went missing: pre-install must run again.
        mark_preinstall_needed()
    run_gui(cfg, profile=args.profile)


if __name__ == "__main__":
    main()