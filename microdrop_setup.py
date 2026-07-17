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
ICON_RELPATH = Path("microdrop-py/src/microdrop_style/icons/Microdrop_Icon.ico")
ICON_PNG_RELPATH = Path("microdrop-py/src/microdrop_style/icons/Microdrop_Icon.png")

DEFAULT_CONFIG = {
    "install_dir": "",
    "pixi_repo_branch": "master",
    "src_repo_branch": "main",
    "auto_update_pixi_repo": True,
    "auto_update_src_repo": True,
    "device": "dropbot",
    "plugins": [],       # optional-plugin class names; empty = full default set
    "contexts": [],      # empty = let examples.microdrop infer
    "preinstall_done": False,
}

# (var name in plugin_consts, UI title, devices the group applies to; None = all)
PLUGIN_GROUPS = [
    ("REQUIRED_PLUGINS", "Required (always loaded)", None),
    ("FRONTEND_PLUGINS", "Frontend", None),
    ("DROPBOT_FRONTEND_PLUGINS", "DropBot frontend", {"dropbot", "mock"}),
    ("OPENDROP_FRONTEND_PLUGINS", "OpenDrop frontend", {"opendrop"}),
    ("MOCK_DROPBOT_FRONTEND_PLUGINS", "Mock DropBot frontend", {"mock"}),
    ("SERVICE_PLUGINS", "Services", None),
    ("BACKEND_PLUGINS", "Backend", None),
    ("DROPBOT_BACKEND_PLUGINS", "DropBot backend", {"dropbot"}),
    ("OPENDROP_BACKEND_PLUGINS", "OpenDrop backend", {"opendrop"}),
    ("MOCK_DROPBOT_BACKEND_PLUGINS", "Mock DropBot backend", {"mock"}),
]


# --------------------------------------------------------------------------
# Config persistence
# --------------------------------------------------------------------------

def config_path():
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
        return base / "Sci-Bots" / "Microdrop-Launch" / "setup_config.json"
    return Path.home() / ".config" / "microdrop_launch" / "setup_config.json"


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        cfg.update(json.loads(config_path().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass  # missing/corrupt config -> fresh defaults (=> pre-install runs)
    return cfg


def save_config(cfg):
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


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
    """Map each PLUGIN_GROUPS var name to its plugin class names via ast."""
    wanted = {name for name, _, _ in PLUGIN_GROUPS}
    tree = ast.parse(Path(consts_path).read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in wanted
                and isinstance(node.value, ast.List)):
            found[node.targets[0].id] = [
                elt.id for elt in node.value.elts if isinstance(elt, ast.Name)]
    return {name: found.get(name, []) for name, _, _ in PLUGIN_GROUPS}


# --------------------------------------------------------------------------
# Git + launch
# --------------------------------------------------------------------------

def list_remote_branches(url):
    """Branch names available on the remote (git ls-remote --heads).

    Queries the remote directly, so it works before anything is cloned.
    Returns [] on failure (offline, bad URL) — callers keep their default.
    """
    code, out = run_capture(["git", "ls-remote", "--heads", url])
    if code != 0:
        return []
    return sorted(line.split("refs/heads/", 1)[1].strip()
                  for line in out.splitlines() if "refs/heads/" in line)


def git_checkout(repo_dir, branch, log):
    """Check out *branch*, fetching once if it only exists on the remote."""
    if run_streamed(["git", "checkout", branch], log, cwd=repo_dir) == 0:
        return True
    # Branch may have been created on the remote after this clone was made.
    run_streamed(["git", "fetch", "--prune"], log, cwd=repo_dir)
    return run_streamed(["git", "checkout", branch], log, cwd=repo_dir) == 0


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
        if not git_checkout(repo_dir, branch, log):
            log(f"Warning: could not check out '{branch}' in {repo_dir}; "
                f"staying on '{current or 'detached HEAD'}'.")
    if run_streamed(["git", "pull"], log, cwd=repo_dir) != 0:
        log(f"Warning: could not pull {repo_dir}; continuing with current state.")


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
        if run_streamed([pixi, "self-update"], log, cwd=install_dir) != 0:
            log("Warning: pixi self-update failed. "
                "Continuing with the current version...")
    else:
        log("Warning: pixi not found; the launcher script will report the error.")

    if cfg["auto_update_pixi_repo"]:
        git_update_repo(install_dir, cfg["pixi_repo_branch"], log)
    if cfg["auto_update_src_repo"]:
        git_update_repo(install_dir / SRC_RELDIR, cfg["src_repo_branch"], log)

    run_args = build_run_args(cfg)
    if IS_WINDOWS:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
               "-File", str(install_dir / "launch_microdrop.ps1"), *run_args]
    else:
        cmd = ["bash", str(install_dir / "launch_microdrop.sh"), *run_args]
    # cwd from the saved appdata config — the shortcut/console this runs in
    # may have any working directory.
    run_streamed(cmd, log, cwd=install_dir)
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


def create_shortcut(cfg, name):
    """Create/overwrite the desktop shortcut; returns its path."""
    install_dir = Path(cfg["install_dir"])
    script = install_dir / SCRIPT_NAME
    path = shortcut_path(name)
    if IS_WINDOWS:
        icon = install_dir / ICON_RELPATH
        ps = (
            "$W = New-Object -ComObject WScript.Shell; "
            f"$S = $W.CreateShortcut('{path}'); "
            f"$S.TargetPath = '{sys.executable}'; "
            f"$S.Arguments = '\"{script}\" --launch'; "
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
            f'Exec={sys.executable} "{script}" --launch\n'
            f"Icon={icon}\n"
            "Terminal=true\n",
            encoding="utf-8")
        path.chmod(0o755)
    return path


# --------------------------------------------------------------------------
# GUI (tkinter imports stay function-local so --launch works without Tk)
# --------------------------------------------------------------------------

def populate_branch_combos(root, combos):
    """Fill branch dropdowns from the remotes without blocking the GUI.

    *combos* is a list of ``(combobox, repo_url, repo_dir, string_var)``.
    ``repo_dir`` may be None or not cloned yet; an existing checkout is
    ``git fetch --prune``d first so newly listed branches are also locally
    checkout-able. Until the background query finishes (or if it fails —
    offline, bad URL), each dropdown keeps its current value.
    """
    def worker():
        for combo, url, repo_dir, var in combos:
            if repo_dir and (Path(repo_dir) / ".git").exists():
                run_capture(["git", "fetch", "--prune"], cwd=repo_dir)
            branches = list_remote_branches(url)

            def apply(combo=combo, var=var, branches=branches):
                if branches:
                    combo.configure(values=branches)
                    if var.get() not in branches:
                        var.set(branches[0])

            root.after(0, apply)

    threading.Thread(target=worker, daemon=True).start()


class LogPane:
    """Thread-safe scrolled log: worker threads call it, the GUI polls."""

    def __init__(self, parent):
        import tkinter as tk
        self.queue = queue.Queue()
        self.text = tk.Text(parent, height=18, width=100, state="disabled")
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
        self.text.after(100, self._poll)


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
        ttk.Label(form, text="pixi-microdrop branch:").grid(
            row=1, column=0, sticky="w")
        self.pixi_branch_combo = ttk.Combobox(
            form, textvariable=self.pixi_branch_var, state="readonly",
            values=[cfg["pixi_repo_branch"]])
        self.pixi_branch_combo.grid(row=1, column=1, sticky="w", padx=4)
        ttk.Label(form, text="Microdrop source branch:").grid(
            row=2, column=0, sticky="w")
        self.src_branch_combo = ttk.Combobox(
            form, textvariable=self.src_branch_var, state="readonly",
            values=[cfg["src_repo_branch"]])
        self.src_branch_combo.grid(row=2, column=1, sticky="w", padx=4)
        ttk.Button(form, text="Refresh branches",
                   command=self._refresh_branches).grid(
            row=1, column=2, rowspan=2, padx=4)
        self._refresh_branches()

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

    def _refresh_branches(self):
        install_dir = Path(self.dir_var.get()).expanduser()
        populate_branch_combos(self.root, [
            (self.pixi_branch_combo, PIXI_REPO_URL, install_dir,
             self.pixi_branch_var),
            (self.src_branch_combo, SRC_REPO_URL, install_dir / SRC_RELDIR,
             self.src_branch_var)])

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
                if branch and not git_checkout(repo_dir, branch, log):
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
    """Stage 2: plugin/device/context selection, repo settings, actions."""

    def __init__(self, root, cfg):
        import tkinter as tk
        from tkinter import messagebox, simpledialog, ttk
        self.root, self.cfg = root, cfg
        self.messagebox, self.simpledialog = messagebox, simpledialog

        root.title("Microdrop Launcher")
        self.frame = ttk.Frame(root, padding=12)
        self.frame.pack(fill="both", expand=True)

        consts_path = Path(cfg["install_dir"]) / PLUGIN_CONSTS_RELPATH
        try:
            self.groups = parse_plugin_groups(consts_path)
        except (OSError, SyntaxError) as exc:
            messagebox.showerror(
                "Microdrop", f"Could not read {consts_path}: {exc}",
                parent=root)
            self.groups = {name: [] for name, _, _ in PLUGIN_GROUPS}

        # Device
        self.device_var = tk.StringVar(value=cfg["device"])
        device_row = ttk.Frame(self.frame)
        device_row.pack(fill="x")
        ttk.Label(device_row, text="Device:").pack(side="left")
        for device in ("dropbot", "opendrop", "mock"):
            ttk.Radiobutton(device_row, text=device, value=device,
                            variable=self.device_var,
                            command=self._apply_device).pack(side="left", padx=4)

        # Plugin checkboxes, grouped, two columns
        self.plugin_vars = {}    # plugin name -> BooleanVar (shared if reused)
        self.group_buttons = {}  # group var name -> [Checkbutton, ...]
        stored = set(cfg["plugins"])
        use_stored = bool(cfg["plugins"])
        plugins_frame = ttk.Frame(self.frame)
        plugins_frame.pack(fill="both", expand=True, pady=6)
        for column, half in enumerate((PLUGIN_GROUPS[:6], PLUGIN_GROUPS[6:])):
            col = ttk.Frame(plugins_frame)
            col.grid(row=0, column=column, sticky="nw", padx=4)
            for name, title, _devices in half:
                box = ttk.LabelFrame(col, text=title, padding=4)
                box.pack(fill="x", pady=2)
                buttons = []
                for plugin in self.groups[name]:
                    required = name == "REQUIRED_PLUGINS"
                    if required:
                        var = tk.BooleanVar(value=True)
                    else:
                        var = self.plugin_vars.setdefault(plugin, tk.BooleanVar(
                            value=True if not use_stored else plugin in stored))
                    btn = ttk.Checkbutton(box, text=plugin, variable=var)
                    btn.pack(anchor="w")
                    if required:
                        btn.configure(state="disabled")
                    else:
                        buttons.append(btn)
                self.group_buttons[name] = buttons

        # Contexts
        ctx_box = ttk.LabelFrame(self.frame, text="Contexts", padding=4)
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

        # Repositories
        repo_box = ttk.LabelFrame(self.frame, text="Repositories", padding=4)
        repo_box.pack(fill="x", pady=2)
        self.pixi_branch_var = tk.StringVar(value=cfg["pixi_repo_branch"])
        self.src_branch_var = tk.StringVar(value=cfg["src_repo_branch"])
        self.update_pixi_var = tk.BooleanVar(value=cfg["auto_update_pixi_repo"])
        self.update_src_var = tk.BooleanVar(value=cfg["auto_update_src_repo"])
        install_dir = Path(cfg["install_dir"])
        rows = (("pixi-microdrop", self.pixi_branch_var, self.update_pixi_var,
                 PIXI_REPO_URL, install_dir),
                ("Microdrop source", self.src_branch_var, self.update_src_var,
                 SRC_REPO_URL, install_dir / SRC_RELDIR))
        self.branch_combos = []
        for row, (label, branch_var, update_var, url, repo_dir) in enumerate(rows):
            ttk.Label(repo_box, text=f"{label} branch:").grid(
                row=row, column=0, sticky="w")
            combo = ttk.Combobox(repo_box, textvariable=branch_var,
                                 state="readonly", values=[branch_var.get()])
            combo.grid(row=row, column=1, padx=4)
            ttk.Checkbutton(repo_box, text="update on launch",
                            variable=update_var).grid(row=row, column=2)
            self.branch_combos.append((combo, url, repo_dir, branch_var))
        ttk.Button(repo_box, text="Refresh branches",
                   command=self._refresh_branches).grid(
            row=0, column=3, rowspan=2, padx=4)
        self._refresh_branches()

        # Actions
        buttons_row = ttk.Frame(self.frame)
        buttons_row.pack(pady=6)
        ttk.Button(buttons_row, text="Launch",
                   command=self._launch).pack(side="left", padx=4)
        ttk.Button(buttons_row, text="Create Desktop Shortcut",
                   command=self._create_shortcut).pack(side="left", padx=4)
        ttk.Button(buttons_row, text="Save & Close",
                   command=self._save_close).pack(side="left", padx=4)

        self._apply_device()
        self._apply_ctx_mode()

    def _active_group_names(self):
        device = self.device_var.get()
        return [name for name, _, devices in PLUGIN_GROUPS
                if name != "REQUIRED_PLUGINS"
                and (devices is None or device in devices)]

    def _apply_device(self):
        active = set(self._active_group_names())
        for name, _, devices in PLUGIN_GROUPS:
            if devices is None:
                continue
            state = "normal" if name in active else "disabled"
            for btn in self.group_buttons[name]:
                btn.configure(state=state)

    def _apply_ctx_mode(self):
        state = "disabled" if self.ctx_auto_var.get() else "normal"
        for btn in self.ctx_buttons:
            btn.configure(state=state)

    def _refresh_branches(self):
        populate_branch_combos(self.root, self.branch_combos)

    def _save(self):
        plugins = []
        for name in self._active_group_names():
            for plugin in self.groups[name]:
                var = self.plugin_vars.get(plugin)
                if var is not None and var.get() and plugin not in plugins:
                    plugins.append(plugin)
        self.cfg.update(
            device=self.device_var.get(),
            plugins=plugins,
            contexts=[] if self.ctx_auto_var.get() else [
                name for name, var in self.ctx_vars.items() if var.get()],
            pixi_repo_branch=self.pixi_branch_var.get().strip() or "master",
            src_repo_branch=self.src_branch_var.get().strip() or "main",
            auto_update_pixi_repo=self.update_pixi_var.get(),
            auto_update_src_repo=self.update_src_var.get())
        save_config(self.cfg)

    def _launch(self):
        self._save()
        self.frame.destroy()
        self.root.title("Microdrop — launching…")
        log = LogPane(self.root)

        def worker():
            if not do_launch(self.cfg, log):
                self.cfg["preinstall_done"] = False
                save_config(self.cfg)
                log("Install directory missing — run this script again "
                    "to reinstall.")

        threading.Thread(target=worker, daemon=True).start()

    def _create_shortcut(self):
        self._save()
        name = "Microdrop"
        while True:
            name = self.simpledialog.askstring(
                "Shortcut name", "Name for the desktop shortcut:",
                initialvalue=name, parent=self.root)
            if not name:
                return
            existing = shortcut_path(name)
            if existing.exists() and not self.messagebox.askyesno(
                    "Shortcut exists",
                    f"'{existing.name}' already exists on the Desktop.\n\n"
                    "Replace it? (No — choose another name)",
                    parent=self.root):
                continue
            break
        try:
            created = create_shortcut(self.cfg, name)
        except (OSError, subprocess.CalledProcessError) as exc:
            self.messagebox.showerror(
                "Shortcut failed", str(exc), parent=self.root)
            return
        self.messagebox.showinfo(
            "Shortcut created",
            f"Created {created}.\nIt always launches the last saved "
            "configuration; rerun this script to change it.",
            parent=self.root)

    def _save_close(self):
        self._save()
        self.root.destroy()


def run_gui(cfg):
    import tkinter as tk
    root = tk.Tk()

    def open_launcher():
        LauncherWindow(root, cfg)

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
    args = parser.parse_args(argv)

    cfg = load_config()
    if args.launch:
        if not _needs_preinstall(cfg):
            do_launch(cfg)
            try:
                input("Done. Press Enter to exit…")
            except (EOFError, RuntimeError):
                pass
            return
        # Appdata/install dir went missing: pre-install must run again.
        cfg["preinstall_done"] = False
        save_config(cfg)
    run_gui(cfg)


if __name__ == "__main__":
    main()