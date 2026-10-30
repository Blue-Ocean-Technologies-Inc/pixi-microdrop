# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Assemble an offline plugin update bundle for a packed MicroDrop install.

A customer's hand-off install is a plain conda prefix (``env/``) unpacked
from a pixi-pack, with no pixi, no conda and no channel access. This bundle
brings newer plugin packages to it without a full reinstall: a small local
conda channel, micromamba to install from it offline, and the
apply-update.bat that drives micromamba.

The target versions come from this workspace's ``pixi.lock`` (bump the plugin
pins and relock first); the base is the pack the customer installed. The
bundle installs the plugins plus any package the base lacks entirely (a
dependency added to the workspace), and its channel carries those plus every
package of their dependency closure that the base has at a different
version/build - nothing the customer already has is shipped again. Only conda
packages change: the MicroDrop wheel or git clone is never touched.

Usage: python tools/build_update.py [platform] [environment]
                                           [--base PATH] [--lock PATH]

``--base`` is the customer's pack: a pixi-pack ``.tar``, a hand-off
``share-microdrop-*.zip`` holding one, a ``pixi.lock`` (read for the same
environment), or an installed MicroDrop folder (its ``env/conda-meta``).
"""

# Standard library imports.
import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
import tarfile
import tomllib
import zipfile
from collections import namedtuple
from pathlib import Path

# Third-party imports.
import yaml

# Local imports.
from build_share import DIST, HANDOFF_PLATFORM, download, write_windows_text
from prune_pack import STRIPPED_PACKAGE_REGEX

TOOLS = Path(__file__).parent
WORKSPACE = TOOLS.parent
TEMPLATES = TOOLS / "share-update"

#: The pixi features whose dependencies are the plugin packages to update.
PLUGIN_FEATURES = ("plugins", "prod-plugins")

#: micromamba release that apply-update.bat runs (mamba-org/micromamba-releases).
MICROMAMBA_VERSION = "2.9.0-0"
MICROMAMBA_URL = (
    "https://github.com/mamba-org/micromamba-releases/releases/download/"
    "{version}/micromamba-{platform}.exe"
)

#: Indexes the bundle's channel (``pixi exec``, conda-forge).
RATTLER_INDEX_SPEC = "rattler-index==0.33.1"

CONDA_SUFFIXES = (".conda", ".tar.bz2")

SCRIPTS = ("apply-update.bat", "fix-conda-meta.py")

#: One conda package. ``url``, ``sha256`` and ``depends`` are only known for
#: packages read from a lock.
Package = namedtuple(
    "Package",
    "name version build subdir url sha256 depends",
    defaults=(None, None, ()),
)


def package_from_url(url, sha256=None, depends=()):
    """Read name, version, build and subdir out of a conda package URL."""

    subdir, filename = url.rsplit("/", 2)[-2:]
    stem = archive_stem(filename)
    name, version, build = stem.rsplit("-", 2)

    return Package(name, version, build, subdir, url, sha256, tuple(depends))


def archive_stem(filename):
    """``name-version-build`` of a conda archive file name."""

    for suffix in CONDA_SUFFIXES:
        if filename.endswith(suffix):
            return filename.removesuffix(suffix)

    raise ValueError(f"{filename} is not a conda package archive")


def package_spec(package):
    """The exact ``name=version=build`` match spec of a package."""

    return f"{package.name}={package.version}={package.build}"


def package_stem(package):
    """``name-version-build``, the file name of its ``conda-meta`` record."""

    return f"{package.name}-{package.version}-{package.build}"


def read_lock_packages(lock_path, environment, platform):
    """The conda packages a ``pixi.lock`` resolves for one environment.

    Returns
    -------
    dict
        Package name -> Package, with URL, sha256 and dependencies.
    """

    with open(lock_path, encoding="utf-8") as stream:
        lock = yaml.load(stream, Loader=yaml.CSafeLoader)

    # Lock platform entries are named; a custom name (e.g. `p1`) carries its
    # conda subdir separately.
    platform_names = [
        entry["name"]
        for entry in lock["platforms"]
        if entry.get("subdir", entry["name"]) == platform
    ]

    if not platform_names:
        raise SystemExit(f"{lock_path} has no {platform} platform")

    environment_packages = lock["environments"][environment]["packages"]
    records = {entry["conda"]: entry for entry in lock["packages"] if "conda" in entry}

    packages = {}

    for entry in environment_packages.get(platform_names[0], []):
        url = entry.get("conda")

        if url is None:
            continue

        record = records[url]
        package = package_from_url(url, record.get("sha256"), record.get("depends", ()))
        packages[package.name] = package

    return packages


def read_plugin_names(pyproject_path):
    """The plugin package names: the dependencies of ``PLUGIN_FEATURES``."""

    with open(pyproject_path, "rb") as stream:
        features = tomllib.load(stream)["tool"]["pixi"]["feature"]

    names = set()

    for feature in PLUGIN_FEATURES:
        names.update(features[feature].get("dependencies", {}))

    return sorted(names)


def read_pack_packages(pack):
    """The packages and identity of a pixi-pack archive.

    Parameters
    ----------
    pack
        An open ``tarfile.TarFile``, possibly in streaming mode.

    Returns
    -------
    tuple
        (Package name -> Package, identity dict)
    """

    packages = {}
    identity = {"pixi_pack_version": None, "microdrop_version": None}

    for member in pack:
        filename = member.name.rsplit("/", 1)[-1]

        if member.name == "pixi-pack.json":
            metadata = json.load(pack.extractfile(member))
            identity["pixi_pack_version"] = metadata.get("pixi-pack-version")

        elif filename == "repodata.json":
            repodata = json.load(pack.extractfile(member))

            for section in ("packages", "packages.conda"):
                for record in repodata.get(section, {}).values():
                    packages[record["name"]] = Package(
                        record["name"],
                        record["version"],
                        record["build"],
                        record["subdir"],
                    )

        elif filename.startswith("microdrop_py-"):
            identity["microdrop_version"] = filename.split("-")[1]

    if not packages:
        raise SystemExit("the pack has no channel repodata - is it a pixi-pack?")

    return packages, identity


def read_install_packages(conda_meta):
    """The packages recorded in an installed environment's ``conda-meta``."""

    packages = {}

    for record_path in sorted(conda_meta.glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        packages[record["name"]] = Package(
            record["name"], record["version"], record["build"], record["subdir"]
        )

    return packages


def read_base(base_path, environment, platform):
    """The package set the customer has installed, from their pack.

    Returns
    -------
    tuple
        (Package name -> Package, identity dict recorded in the manifest)
    """

    identity = {"source": base_path.name}

    if base_path.is_dir():
        conda_meta = base_path / "env" / "conda-meta"

        if not conda_meta.is_dir():
            conda_meta = base_path / "conda-meta"

        identity["kind"] = "install"

        return read_install_packages(conda_meta), identity

    if base_path.suffix == ".lock":
        identity["kind"] = "lock"

        return read_lock_packages(base_path, environment, platform), identity

    if base_path.suffix == ".zip":
        with zipfile.ZipFile(base_path) as archive:
            packs = [name for name in archive.namelist() if name.endswith(".tar")]

            if len(packs) != 1:
                raise SystemExit(f"{base_path} holds {len(packs)} packs, not one")

            identity["kind"] = "hand-off zip"
            identity["pack"] = packs[0].rsplit("/", 1)[-1]

            # Stream the pack out of the zip: it is ~1 GB, and only the
            # small metadata members are read.
            with (
                archive.open(packs[0]) as stream,
                tarfile.open(fileobj=stream, mode="r|") as pack,
            ):
                packages, pack_identity = read_pack_packages(pack)

    else:
        identity["kind"] = "pack"
        identity["pack"] = base_path.name

        with tarfile.open(base_path, mode="r|") as pack:
            packages, pack_identity = read_pack_packages(pack)

    identity.update(pack_identity)

    return packages, identity


def default_base(environment, platform):
    """The newest pack of this environment in ``dist/``."""

    names = [
        f"microdrop-{environment}-slim-{platform}.tar",
        f"microdrop-{environment}-{platform}.tar",
        f"microdrop-{environment}-git-slim-{platform}.tar",
        f"microdrop-{environment}-git-{platform}.tar",
    ]
    packs = [DIST / name for name in names if (DIST / name).exists()]

    if not packs:
        raise SystemExit(
            f"no {environment} pack for {platform} in {DIST} - pass --base with "
            f"the pack (or hand-off zip) the customer installed"
        )

    return max(packs, key=lambda path: path.stat().st_mtime)


def select_install_names(target, base, plugin_names):
    """The packages apply-update.bat installs, sorted by name.

    That is the plugins, plus every package the target environment has and
    the base lacks entirely: those come from dependencies added to the
    workspace rather than to a plugin package (e.g. sympy for the heater's
    nonlinear compensation), so no plugin's dependency list would pull them
    in. Toolchain packages stripped from slim packs stay out - the installed
    dependents never had them.
    """

    missing = [name for name in plugin_names if name not in target]

    if missing:
        raise SystemExit(f"the lock has no {', '.join(missing)} for this environment")

    added = [
        name
        for name in target
        if name not in base and not STRIPPED_PACKAGE_REGEX.match(name)
    ]

    return sorted(set(plugin_names) | set(added))


def select_update_packages(target, base, install_names):
    """The packages the bundle's channel must carry.

    That is every package to install at its target version, plus each package
    of their dependency closure that the base lacks or has at another
    version/build. The walk stops at packages the base already has unchanged:
    the installed copy satisfies them. Stripped toolchain packages stay out
    unless the base kept them, as in `select_install_names`.

    Returns
    -------
    list
        Packages sorted by name.
    """

    selected = {}
    pending = list(install_names)

    while pending:
        name = pending.pop()

        if name in selected or name not in target:
            continue

        package = target[name]
        installed = base.get(name)
        changed = installed is None or (installed.version, installed.build) != (
            package.version,
            package.build,
        )

        if name not in install_names:
            if not changed:
                continue

            if installed is None and STRIPPED_PACKAGE_REGEX.match(name):
                continue

        selected[name] = package
        pending.extend(depend.split()[0] for depend in package.depends)

    return sorted(selected.values())


def fetch_package(package, cache):
    """Return a cached, checksum-verified archive of a lock package.

    The cache is pixi-pack's ``dist/pack-cache`` layout (``<subdir>/<file>``),
    so a recent pack has usually downloaded the package already.
    """

    cached = cache / package.subdir / package.url.rsplit("/", 1)[-1]

    if cached.exists() and file_sha256(cached) == package.sha256:
        return cached

    download(package.url, cached)

    if file_sha256(cached) != package.sha256:
        cached.unlink()

        raise SystemExit(f"{package.url} does not match its pixi.lock sha256")

    return cached


def file_sha256(path):
    digest = hashlib.sha256()

    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)

    return digest.hexdigest()


def fetch_micromamba(platform, cache):
    """Return a cached micromamba executable for the platform."""

    cached = cache / f"micromamba-{MICROMAMBA_VERSION}-{platform}.exe"

    if cached.exists() and cached.stat().st_size > 0:
        return cached

    download(
        MICROMAMBA_URL.format(version=MICROMAMBA_VERSION, platform=platform), cached
    )

    return cached


def index_channel(channel, platform):
    """Write ``repodata.json`` for the channel's platform and noarch subdirs."""

    subprocess.run(
        ["pixi", "exec", "--spec", RATTLER_INDEX_SPEC, "--"]
        + ["rattler-index", "fs", "--force", str(channel)],
        check=True,
    )

    # micromamba reads both subdirs of a channel; one without packages still
    # needs an (empty) index.
    for subdir in (platform, "noarch"):
        repodata = channel / subdir / "repodata.json"

        if not repodata.exists():
            repodata.parent.mkdir(parents=True, exist_ok=True)
            empty = {
                "info": {"subdir": subdir},
                "packages": {},
                "packages.conda": {},
                "repodata_version": 1,
            }
            repodata.write_text(json.dumps(empty, indent=1))


def write_manifest(folder, manifest):
    """Write ``update.json`` and the plain-text lists apply-update.bat reads.

    ``specs.txt`` holds one ``name=version=build`` spec to install per line;
    ``base-plugins.txt`` the ``conda-meta`` record names of the plugins the
    base pack installed, so the script can warn on a different install.
    """

    (folder / "update.json").write_text(json.dumps(manifest, indent=2) + "\n")
    write_windows_text(folder / "specs.txt", "\n".join(manifest["install"]) + "\n")

    base_plugins = [
        f"{name}-{version_build.replace('=', '-')}"
        for name, version_build in manifest["base"]["plugins"].items()
    ]
    write_windows_text(folder / "base-plugins.txt", "\n".join(base_plugins) + "\n")


def build_manifest(
    date, platform, environment, base_identity, base, plugin_names, install, channel
):
    """The ``update.json`` content.

    Parameters
    ----------
    install
        The packages to install: the plugins and the packages new to the base.
    channel
        Every package the bundle's channel carries.
    """

    base_plugins = {
        name: f"{base[name].version}={base[name].build}"
        for name in plugin_names
        if name in base
    }

    return {
        "date": date,
        "platform": platform,
        "environment": environment,
        "base": base_identity | {"packages": len(base), "plugins": base_plugins},
        "plugins": [
            package_spec(package) for package in install if package.name in plugin_names
        ],
        "install": [package_spec(package) for package in install],
        "channel": [
            {
                "name": package.name,
                "version": package.version,
                "build": package.build,
                "subdir": package.subdir,
            }
            for package in channel
        ],
    }


def build_update(platform, environment, base_path=None, lock_path=None):
    if platform != HANDOFF_PLATFORM:
        raise SystemExit(
            f"apply-update.bat only exists for {HANDOFF_PLATFORM}, not {platform}"
        )

    base_path = base_path or default_base(environment, platform)
    lock_path = lock_path or WORKSPACE / "pixi.lock"
    cache = DIST / "pack-cache"
    print(f"base: {base_path}")
    print(f"lock: {lock_path}")

    base, base_identity = read_base(base_path, environment, platform)
    target = read_lock_packages(lock_path, environment, platform)
    plugin_names = read_plugin_names(lock_path.with_name("pyproject.toml"))
    install_names = select_install_names(target, base, plugin_names)
    selected = select_update_packages(target, base, install_names)
    install = [target[name] for name in install_names]

    date = datetime.date.today().isoformat()
    folder_name = f"microdrop-update-{date}-{platform}"
    folder = DIST / "share" / folder_name

    if folder.exists():
        shutil.rmtree(folder)

    channel = folder / "channel"

    for package in selected:
        subdir = channel / package.subdir
        subdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fetch_package(package, cache), subdir)

        installed = base.get(package.name)
        was = f"{installed.version}={installed.build}" if installed else "new"
        role = "install" if package.name in install_names else "dependency"
        print(f"  {package_spec(package)}  ({role}; base: {was})")

    index_channel(channel, platform)
    shutil.copy2(fetch_micromamba(platform, cache), folder / "micromamba.exe")

    manifest = build_manifest(
        date,
        platform,
        environment,
        base_identity,
        base,
        plugin_names,
        install,
        selected,
    )
    write_manifest(folder, manifest)

    for script in SCRIPTS:
        write_windows_text(folder / script, (TEMPLATES / script).read_text())

    title = f"MicroDrop plugin update {date}"
    readme = (
        (TEMPLATES / "README.txt")
        .read_text()
        .format(
            title=title,
            title_rule="=" * len(title),
            folder_name=folder_name,
            install="\n".join(f"    {spec}" for spec in manifest["install"]),
            base=base_identity.get("pack", base_identity["source"]),
        )
    )
    write_windows_text(folder / "README.txt", readme)

    zip_path = DIST / f"{folder_name}.zip"

    # Fastest deflate level, as for the hand-offs: the payload is mostly
    # already-compressed package archives.
    with zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1
    ) as archive:
        for path in sorted(folder.rglob("*")):
            archive.write(path, Path(folder_name) / path.relative_to(folder))

    print(f"folder: {folder}")
    print(f"zip:    {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")

    return zip_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a plugin update bundle")
    parser.add_argument("platform", nargs="?", default=HANDOFF_PLATFORM)
    parser.add_argument("environment", nargs="?", default="prod")
    parser.add_argument("--base", type=Path, help="the customer's pack or hand-off")
    parser.add_argument("--lock", type=Path, help="pixi.lock with the target versions")
    args = parser.parse_args()

    build_update(args.platform, args.environment, args.base, args.lock)
