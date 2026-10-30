# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Assemble an offline update bundle for a packed MicroDrop install.

A customer's hand-off install is a plain conda prefix (``env/``) unpacked
from a pixi-pack, with no pixi, no conda and no channel access. This bundle
brings it up to this workspace's locked environment without a reinstall: a
small local conda channel and micromamba to install from it offline, the
changed PyPI wheels (MicroDrop's own among them) for the environment's pip,
and the apply-update.bat that drives both.

The target versions come from this workspace's ``pixi.lock`` (relock first);
the bases are the packs customers installed. The bundle installs every
package the lock has that a base lacks or has at another version/build, and
its channel carries those plus every changed package of their dependency
closure - nothing a base already has is shipped again. With several bases
the bundle covers their union. ``--full`` ignores the bases and ships the
whole locked environment, for an install whose base is unknown.

A git hand-off links MicroDrop from its clone instead of the wheel; the
bundle only ships the wheel for bases that have it, and apply-update.bat
never installs it over a clone.

Usage: python tools/build_update.py [platform] [environment]
                                    [--base PATH ...] [--full] [--lock PATH]

``--base`` (repeatable) is a customer's pack: a pixi-pack ``.tar``, a
hand-off ``share-microdrop-*.zip`` holding one, a ``pixi.lock`` (read for the
same environment), or an installed MicroDrop folder (its ``env/conda-meta``
and ``site-packages``). It defaults to every slim pack and hand-off zip for
the platform in ``dist/``.
"""

# Standard library imports.
import argparse
import datetime
import functools
import hashlib
import json
import re
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
from build_share import (
    DIRTY_VERSION,
    DIST,
    HANDOFF_PLATFORM,
    download,
    write_windows_text,
)
from prune_pack import STRIPPED_PACKAGE_REGEX

TOOLS = Path(__file__).parent
WORKSPACE = TOOLS.parent
TEMPLATES = TOOLS / "share-update"

#: The pixi features whose dependencies are the plugin packages, whose
#: versions apply-update.bat shows before and after the update.
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

#: The MicroDrop app's PyPI name. A git hand-off has no such wheel installed:
#: it links the clone through ``MICRODROP_GIT_PTH`` in site-packages.
MICRODROP_DIST = "microdrop-py"
MICRODROP_GIT_PTH = "microdrop_git.pth"

#: hatch-vcs's version when `src` has no git history to read a version from.
FALLBACK_VERSION = "0.0.0"

#: One conda package. ``url``, ``sha256`` and ``depends`` are only known for
#: packages read from a lock.
Package = namedtuple(
    "Package",
    "name version build subdir url sha256 depends",
    defaults=(None, None, ()),
)

#: One PyPI package of a lock, by normalized name. A wheel from an index has
#: ``url`` and ``sha256``; a path dependency (a source tree built into a
#: wheel here) has ``path``, and its ``version`` only once built.
PypiPackage = namedtuple(
    "PypiPackage", "name version url sha256 path", defaults=(None, None, None, None)
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


def normalize_name(name):
    """The PEP 503 normalized form of a PyPI project name."""

    return re.sub(r"[-_.]+", "-", name).lower()


def distribution_name_version(filename):
    """Normalized name and version of a wheel or ``.dist-info`` file name.

    Both escape the name's dashes, so the first dash ends the name.
    """

    name, version = filename.removesuffix(".dist-info").split("-")[:2]

    return normalize_name(name), version


def pypi_spec(package):
    """The exact ``name==version`` requirement of a PyPI package."""

    return f"{package.name}=={package.version}"


@functools.cache
def load_lock(lock_path):
    with open(lock_path, encoding="utf-8") as stream:
        return yaml.load(stream, Loader=yaml.CSafeLoader)


def read_lock_entries(lock_path, environment, platform):
    """The package entries a ``pixi.lock`` resolves for one environment.

    Returns
    -------
    tuple
        (the environment's ``conda``/``pypi`` entries for the platform, the
        lock's package records)
    """

    lock = load_lock(lock_path)

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

    return environment_packages.get(platform_names[0], []), lock["packages"]


def read_lock_packages(lock_path, environment, platform):
    """The conda packages a ``pixi.lock`` resolves for one environment.

    Returns
    -------
    dict
        Package name -> Package, with URL, sha256 and dependencies.
    """

    entries, records = read_lock_entries(lock_path, environment, platform)
    records = {record["conda"]: record for record in records if "conda" in record}

    packages = {}

    for entry in entries:
        url = entry.get("conda")

        if url is None:
            continue

        record = records[url]
        package = package_from_url(url, record.get("sha256"), record.get("depends", ()))
        packages[package.name] = package

    return packages


def read_lock_pypi_packages(lock_path, environment, platform):
    """The PyPI packages a ``pixi.lock`` resolves for one environment.

    Returns
    -------
    dict
        Normalized name -> PypiPackage. Path dependencies have no version
        and their ``path`` resolved against the lock's folder.
    """

    entries, records = read_lock_entries(lock_path, environment, platform)
    records = {record["pypi"]: record for record in records if "pypi" in record}

    packages = {}

    for entry in entries:
        location = entry.get("pypi")

        if location is None:
            continue

        record = records[location]
        name = normalize_name(record["name"])

        if "://" in location:
            package = PypiPackage(
                name, record["version"], location, record.get("sha256")
            )
        else:
            package = PypiPackage(name, path=(Path(lock_path).parent / location))

        packages[name] = package

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
        (Package name -> Package, PyPI name -> version, identity dict)
    """

    packages = {}
    pypi = {}
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

        elif member.name.startswith("pypi/") and filename.endswith(".whl"):
            name, version = distribution_name_version(filename)
            pypi[name] = version

    if not packages:
        raise SystemExit("the pack has no channel repodata - is it a pixi-pack?")

    identity["microdrop_version"] = pypi.get(MICRODROP_DIST)

    return packages, pypi, identity


def read_install_packages(conda_meta):
    """The packages recorded in an installed environment's ``conda-meta``."""

    packages = {}

    for record_path in sorted(conda_meta.glob("*.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        packages[record["name"]] = Package(
            record["name"], record["version"], record["build"], record["subdir"]
        )

    return packages


def read_install_pypi_packages(env):
    """The Python distributions installed in an environment, by their
    ``.dist-info`` folders: PyPI name -> version.

    Conda's Python packages have one too; that is harmless, as the lock never
    lists a package both as conda and as PyPI.
    """

    site_packages = [
        env / "Lib" / "site-packages",
        *env.glob("lib/python*/site-packages"),
    ]

    return dict(
        distribution_name_version(path.name)
        for folder in site_packages
        for path in folder.glob("*.dist-info")
    )


def read_base(base_path, environment, platform):
    """The package set the customer has installed, from their pack.

    Returns
    -------
    tuple
        (Package name -> Package, PyPI name -> version (None where a lock
        does not know it), identity dict recorded in the manifest)
    """

    identity = {"source": base_path.name}

    if base_path.is_dir():
        env = base_path / "env"

        if not (env / "conda-meta").is_dir():
            env = base_path

        pypi = read_install_pypi_packages(env)
        git_linked = any(
            (folder / MICRODROP_GIT_PTH).exists()
            for folder in (env / "Lib" / "site-packages", env)
        )

        # A clone linked in shadows any wheel; the update must not install one.
        if git_linked:
            pypi.pop(MICRODROP_DIST, None)

        identity["kind"] = "install"
        identity["microdrop_version"] = (
            "git" if git_linked else pypi.get(MICRODROP_DIST)
        )

        return read_install_packages(env / "conda-meta"), pypi, identity

    if base_path.suffix == ".lock":
        identity["kind"] = "lock"
        pypi = {
            name: package.version
            for name, package in read_lock_pypi_packages(
                base_path, environment, platform
            ).items()
        }

        return read_lock_packages(base_path, environment, platform), pypi, identity

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
                packages, pypi, pack_identity = read_pack_packages(pack)

    else:
        identity["kind"] = "pack"
        identity["pack"] = base_path.name

        with tarfile.open(base_path, mode="r|") as pack:
            packages, pypi, pack_identity = read_pack_packages(pack)

    identity.update(pack_identity)

    return packages, pypi, identity


def default_bases(platform):
    """Every pack a customer may have installed for the platform, in ``dist/``.

    That is the slim packs and the hand-off zips (which hold slim packs):
    full packs keep the firmware toolchain, which no customer install has.
    """

    bases = sorted(DIST.glob(f"microdrop-*-slim-{platform}.tar"))
    bases += sorted(DIST.glob(f"share-microdrop-*-{platform}*.zip"))

    if not bases:
        raise SystemExit(
            f"no pack or hand-off zip for {platform} in {DIST} - pass --base with "
            f"the pack (or hand-off zip) the customer installed, or --full"
        )

    return bases


def package_changed(package, installed):
    """Whether an installed package (None: absent) differs from the target."""

    if installed is None:
        return True

    return (installed.version, installed.build) != (package.version, package.build)


def select_install_names(target, base):
    """The packages apply-update.bat installs for one base, sorted by name.

    That is every package the target environment has and the base lacks or
    has at another version/build. Toolchain packages stripped from slim
    packs stay out unless the base has them - the installed dependents never
    had them.
    """

    return sorted(
        name
        for name, package in target.items()
        if package_changed(package, base.get(name))
        and (name in base or not STRIPPED_PACKAGE_REGEX.match(name))
    )


def select_full_install_names(target):
    """Every package of the target environment but the stripped toolchain."""

    return sorted(name for name in target if not STRIPPED_PACKAGE_REGEX.match(name))


def select_held_back_names(target, base, install_names):
    """The install candidates micromamba cannot install into the base.

    A package that depends on a stripped toolchain package the base lacks
    (clang-helpers on clang, conda-helpers on git) fails micromamba's solve
    once it has to change: the toolchain is in no channel. Such packages keep
    their installed version, as they did in the slim pack.
    """

    return sorted(
        name
        for name in install_names
        if any(
            STRIPPED_PACKAGE_REGEX.match(dependency) and dependency not in base
            for dependency in (depend.split()[0] for depend in target[name].depends)
        )
    )


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

        if name not in install_names:
            if not package_changed(package, installed):
                continue

            if installed is None and STRIPPED_PACKAGE_REGEX.match(name):
                continue

        selected[name] = package
        pending.extend(depend.split()[0] for depend in package.depends)

    return sorted(selected.values())


def path_dependencies_to_build(target_pypi, base_pypis, full=False):
    """The path dependencies whose wheels must be built to compare or ship.

    A path dependency's version is only known once built, so build every one
    a base might lack or have at another version: all of them, except the
    MicroDrop wheel when no base has it (only git-linked installs).
    """

    return sorted(
        name
        for name, package in target_pypi.items()
        if package.path is not None
        and (full or name != MICRODROP_DIST or any(name in base for base in base_pypis))
    )


def select_pypi_names(target_pypi, base):
    """The PyPI packages one base lacks or has at another version.

    MicroDrop's own wheel only counts where the base has it: a base without
    it is a git hand-off, whose clone the wheel would shadow.
    """

    return sorted(
        name
        for name, package in target_pypi.items()
        if base.get(name) is None or base[name] != package.version
        if name in base or name != MICRODROP_DIST
    )


def build_path_wheel(package, out_dir):
    """Build a path dependency's wheel, as the pack's ``build-wheels`` does.

    Returns
    -------
    PypiPackage
        The package with its version, and ``path`` now the built wheel.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["pixi", "exec", "uv", "build", "--wheel", "-o", str(out_dir)]
        + [str(package.path)],
        check=True,
    )

    wheels = [
        path
        for path in out_dir.glob("*.whl")
        if distribution_name_version(path.name)[0] == package.name
    ]

    if len(wheels) != 1:
        raise SystemExit(f"building {package.path} left {len(wheels)} wheels")

    version = distribution_name_version(wheels[0].name)[1]

    # hatch-vcs appends .dYYYYMMDD when `src` has uncommitted changes, and
    # falls back to 0.0.0 with no git history: neither traces to a commit.
    if DIRTY_VERSION.search(version) or version == FALLBACK_VERSION:
        raise SystemExit(
            f"{package.name} {version} was built from {package.path} with "
            f"uncommitted changes or no git history - commit or stash the "
            f"changes (or check out the submodule) and re-run"
        )

    return package._replace(version=version, path=wheels[0])


def fetch_wheel(package, cache):
    """Return a cached, checksum-verified wheel of a lock PyPI package.

    The cache is pixi-pack's ``dist/pack-cache/pypi`` layout.
    """

    cached = cache / "pypi" / package.url.rsplit("/", 1)[-1]

    if cached.exists() and file_sha256(cached) == package.sha256:
        return cached

    download(package.url, cached)

    if file_sha256(cached) != package.sha256:
        cached.unlink()

        raise SystemExit(f"{package.url} does not match its pixi.lock sha256")

    return cached


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
    ``optional-specs.txt`` the stripped toolchain packages, installed only
    where the install already has them; ``plugins.txt`` the plugin package
    names, whose versions the script shows before and after.
    ``pypi-specs.txt`` holds the ``name==version`` PyPI requirements but
    MicroDrop's, which ``microdrop-spec.txt`` holds alone: the script skips
    it for a git-linked install.
    """

    (folder / "update.json").write_text(json.dumps(manifest, indent=2) + "\n")

    microdrop = f"{MICRODROP_DIST}=="
    lists = {
        "specs.txt": manifest["install"],
        "optional-specs.txt": manifest["optional"],
        "plugins.txt": [spec.split("=")[0] for spec in manifest["plugins"]],
        "pypi-specs.txt": [
            spec for spec in manifest["pypi"] if not spec.startswith(microdrop)
        ],
        "microdrop-spec.txt": [
            spec for spec in manifest["pypi"] if spec.startswith(microdrop)
        ],
    }

    for filename, lines in lists.items():
        write_windows_text(folder / filename, "".join(f"{line}\n" for line in lines))


def describe_base(identity, base, base_pypi, plugin_names):
    """A base's manifest entry: its identity, size and plugin versions."""

    plugins = {
        name: f"{base[name].version}={base[name].build}"
        for name in plugin_names
        if name in base
    }

    return identity | {
        "packages": len(base),
        "pypi_packages": len(base_pypi),
        "plugins": plugins,
    }


def build_manifest(
    date,
    platform,
    environment,
    bases,
    plugin_names,
    install,
    channel,
    pypi=(),
    full=False,
    held_back=(),
):
    """The ``update.json`` content.

    Parameters
    ----------
    bases
        The ``describe_base`` entry of every base the bundle covers.
    install
        The packages to install; the stripped toolchain among them goes to
        ``optional``.
    channel
        Every package the bundle's channel carries.
    pypi
        The PyPI packages whose wheels the bundle ships and installs.
    held_back
        The changed packages left at their installed version, as
        `select_held_back_names` explains.
    """

    return {
        "date": date,
        "platform": platform,
        "environment": environment,
        "full": full,
        "bases": bases,
        "plugins": [
            package_spec(package) for package in install if package.name in plugin_names
        ],
        "install": [
            package_spec(package)
            for package in install
            if not STRIPPED_PACKAGE_REGEX.match(package.name)
        ],
        "optional": [
            package_spec(package)
            for package in install
            if STRIPPED_PACKAGE_REGEX.match(package.name)
        ],
        "pypi": [pypi_spec(package) for package in pypi],
        "held_back": [package_spec(package) for package in held_back],
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


def describe_microdrop(pypi):
    """The README's paragraph on MicroDrop's own code."""

    versions = [package.version for package in pypi if package.name == MICRODROP_DIST]
    git_note = (
        "A MicroDrop installed with git keeps its own code: update that with\n"
        "update-microdrop.bat in your MicroDrop folder."
    )

    if not versions:
        return f"MicroDrop's own code is not part of this update.\n{git_note}"

    return f"MicroDrop itself is updated to {versions[0]}.\n{git_note}"


def build_update(platform, environment, base_paths=(), lock_path=None, full=False):
    if platform != HANDOFF_PLATFORM:
        raise SystemExit(
            f"apply-update.bat only exists for {HANDOFF_PLATFORM}, not {platform}"
        )

    lock_path = lock_path or WORKSPACE / "pixi.lock"
    cache = DIST / "pack-cache"
    print(f"lock: {lock_path}")

    target = read_lock_packages(lock_path, environment, platform)
    target_pypi = read_lock_pypi_packages(lock_path, environment, platform)
    plugin_names = read_plugin_names(lock_path.with_name("pyproject.toml"))
    base_paths = [] if full else list(base_paths) or default_bases(platform)
    bases = []

    for base_path in base_paths:
        print(f"base: {base_path}")
        bases.append((base_path, *read_base(base_path, environment, platform)))

    # Path dependencies have no locked version: build them to learn it.
    wheel_build = DIST / "update-wheels"

    if wheel_build.exists():
        shutil.rmtree(wheel_build)

    for name in path_dependencies_to_build(
        target_pypi, [base_pypi for _, _, base_pypi, _ in bases], full
    ):
        target_pypi[name] = build_path_wheel(target_pypi[name], wheel_build)

    install_names = set()
    held_back = set()
    pypi_names = set()

    # A full update cannot know the base, so it holds back as for a slim one.
    if full:
        install_names.update(select_full_install_names(target))
        held_back.update(select_held_back_names(target, {}, install_names))
        pypi_names.update(target_pypi)

    # The bundle covers every base: install the union of what each one lacks,
    # less the union of what any one cannot take.
    for _, base, base_pypi, _ in bases:
        names = select_install_names(target, base)
        install_names.update(names)
        held_back.update(select_held_back_names(target, base, names))
        pypi_names.update(select_pypi_names(target_pypi, base_pypi))

    install_names -= held_back
    selected = set()

    for base in [base for _, base, _, _ in bases] or [{}]:
        selected.update(select_update_packages(target, base, install_names))

    install = [target[name] for name in sorted(install_names)]
    selected = sorted(package for package in selected if package.name not in held_back)
    pypi = [target_pypi[name] for name in sorted(pypi_names)]

    if held_back:
        print(
            f"WARNING: holding back {', '.join(sorted(held_back))}: they need "
            f"toolchain packages stripped from slim installs"
        )

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

    wheels = folder / "wheels"
    wheels.mkdir(parents=True)

    for package in pypi:
        wheel = package.path if package.url is None else fetch_wheel(package, cache)
        shutil.copy2(wheel, wheels)

    print(
        f"install {len(install)} conda packages (the channel carries "
        f"{len(selected)}) and {len(pypi)} PyPI packages"
    )

    index_channel(channel, platform)
    shutil.copy2(fetch_micromamba(platform, cache), folder / "micromamba.exe")

    manifest = build_manifest(
        date,
        platform,
        environment,
        [
            describe_base(identity, base, base_pypi, plugin_names)
            for _, base, base_pypi, identity in bases
        ],
        plugin_names,
        install,
        selected,
        pypi,
        full,
        [target[name] for name in sorted(held_back)],
    )
    write_manifest(folder, manifest)

    for script in SCRIPTS:
        write_windows_text(folder / script, (TEMPLATES / script).read_text())

    title = f"MicroDrop update {date}"
    readme = (
        (TEMPLATES / "README.txt")
        .read_text()
        .format(
            title=title,
            title_rule="=" * len(title),
            folder_name=folder_name,
            count=len(install) + len(pypi),
            plugins="\n".join(f"    {spec}" for spec in manifest["plugins"]),
            microdrop=describe_microdrop(pypi),
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
    parser = argparse.ArgumentParser(description="Build an offline update bundle")
    parser.add_argument("platform", nargs="?", default=HANDOFF_PLATFORM)
    parser.add_argument("environment", nargs="?", default="prod")
    parser.add_argument(
        "--base",
        type=Path,
        action="append",
        default=[],
        help="a customer's pack, hand-off zip, pixi.lock or install (repeatable)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="ship the whole locked environment, for an install of unknown base",
    )
    parser.add_argument("--lock", type=Path, help="pixi.lock with the target versions")
    args = parser.parse_args()

    build_update(args.platform, args.environment, args.base, args.lock, args.full)
