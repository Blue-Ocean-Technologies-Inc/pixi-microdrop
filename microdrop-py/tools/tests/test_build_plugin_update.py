# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import datetime
import hashlib
import io
import json
import tarfile
import zipfile

# Third-party imports.
import build_plugin_update as bpu
import pytest
import yaml

CF = "https://conda.anaconda.org/conda-forge"
PLUGINS = "https://prefix.dev/microdrop-plugins"

PYPROJECT = """\
[tool.pixi.feature.plugins.dependencies]
magnet-microdrop-plugin = ">=1.2.0,<2"

[tool.pixi.feature.prod-plugins.dependencies]
heater-microdrop-plugin = ">=1.10.1,<2"

[tool.pixi.feature.dev.dependencies]
pytest = "*"
"""

#: url -> depends of the target environment (prod, win-64).
TARGET = {
    f"{PLUGINS}/noarch/heater-microdrop-plugin-1.12.0-pyh4616a5c_0.conda": [
        "mpremote >=1.20",
        "sympy >=1.13",
        "python >=3.11",
    ],
    f"{PLUGINS}/noarch/magnet-microdrop-plugin-1.2.1-pyh4616a5c_0.conda": [
        "python >=3.11",
    ],
    f"{CF}/noarch/mpremote-1.25.0-py_0.tar.bz2": ["python"],
    f"{CF}/noarch/sympy-1.14.0-pyh2585a3b_105.conda": ["mpmath >=0.19", "python"],
    f"{CF}/noarch/mpmath-1.3.0-pyhd8ed1ab_1.conda": ["python >=3.9"],
    # A workspace-level dependency no plugin declares: new to the base.
    f"{CF}/noarch/send2trash-1.8.3-pyh5737063_1.conda": ["python"],
    f"{CF}/win-64/python-3.13.15-h254dcb4_103_cp313.conda": [
        "libzlib >=1.3.2,<2.0a0",
        "ucrt >=10.0.20348.0",
    ],
    f"{CF}/win-64/libzlib-1.3.2-h2466b09_0.conda": ["ucrt"],
    f"{CF}/win-64/numpy-2.3.0-py313h_0.conda": ["python"],
    f"{CF}/win-64/clang-20.1.0-h_0.conda": [],
}

#: name -> (version, build, subdir) of the base pack the customer has.
BASE = {
    "heater-microdrop-plugin": ("1.10.1", "pyh4616a5c_0", "noarch"),
    "magnet-microdrop-plugin": ("1.2.1", "pyh4616a5c_0", "noarch"),
    "mpremote": ("1.25.0", "py_0", "noarch"),
    "python": ("3.13.15", "h254dcb4_103_cp313", "win-64"),
    # Changed build in the target: must ship.
    "libzlib": ("1.3.1", "h2466b09_2", "win-64"),
    # Changed in the target but not a plugin dependency: must not ship.
    "numpy": ("2.2.0", "py313h_0", "win-64"),
    "ucrt": ("10.0.26100.0", "h57928b3_0", "win-64"),
}


def archive_bytes(url):
    return f"fake archive {url}".encode()


def write_lock(path, environment="prod"):
    """A minimal pixi.lock (v7 layout) for the TARGET packages."""

    lock = {
        "version": 7,
        "platforms": [
            {"name": "p1", "subdir": "linux-aarch64"},
            {"name": "win-64"},
        ],
        "environments": {
            environment: {
                "packages": {
                    "win-64": [{"conda": url} for url in TARGET] + [{"pypi": "./"}],
                    "p1": [{"conda": f"{CF}/linux-aarch64/zlib-1-h_0.conda"}],
                }
            },
            "default": {"packages": {"win-64": []}},
        },
        "packages": [
            {
                "conda": url,
                "sha256": hashlib.sha256(archive_bytes(url)).hexdigest(),
                "depends": depends,
            }
            for url, depends in TARGET.items()
        ]
        + [
            {"conda": f"{CF}/linux-aarch64/zlib-1-h_0.conda", "sha256": "0"},
            {"pypi": "./", "name": "microdrop-py"},
        ],
    }
    path.write_text(yaml.safe_dump(lock))
    path.with_name("pyproject.toml").write_text(PYPROJECT)

    return path


def repodata(subdir):
    records = {
        f"{name}-{version}-{build}.conda": {
            "name": name,
            "version": version,
            "build": build,
            "subdir": record_subdir,
        }
        for name, (version, build, record_subdir) in BASE.items()
        if record_subdir == subdir
    }

    return {"info": {"subdir": subdir}, "packages": {}, "packages.conda": records}


def write_pack(path):
    """A pixi-pack style tar: channel repodata, metadata and a wheel."""

    members = {
        "pixi-pack.json": json.dumps({"pixi-pack-version": "0.7.11"}).encode(),
        "channel/noarch/repodata.json": json.dumps(repodata("noarch")).encode(),
        "channel/win-64/repodata.json": json.dumps(repodata("win-64")).encode(),
        "pypi/microdrop_py-1.24.2-py3-none-any.whl": b"wheel",
    }

    with tarfile.open(path, "w") as pack:
        for name, data in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            pack.addfile(member, io.BytesIO(data))

    return path


@pytest.fixture
def lock_path(tmp_path):
    return write_lock(tmp_path / "pixi.lock")


@pytest.fixture
def base_packages():
    return {
        name: bpu.Package(name, version, build, subdir)
        for name, (version, build, subdir) in BASE.items()
    }


def test_package_from_url_reads_name_version_build_and_subdir():
    package = bpu.package_from_url(
        f"{PLUGINS}/noarch/heater-microdrop-plugin-1.12.0-pyh4616a5c_0.conda"
    )

    assert package.name == "heater-microdrop-plugin"
    assert package.version == "1.12.0"
    assert package.build == "pyh4616a5c_0"
    assert package.subdir == "noarch"

    legacy = bpu.package_from_url(f"{CF}/noarch/mpremote-1.25.0-py_0.tar.bz2")

    assert (legacy.name, legacy.version, legacy.build) == ("mpremote", "1.25.0", "py_0")


def test_read_lock_packages_reads_one_environment_and_platform(lock_path):
    packages = bpu.read_lock_packages(lock_path, "prod", "win-64")

    assert set(packages) == {bpu.package_from_url(url).name for url in TARGET}

    python = packages["python"]

    assert python.subdir == "win-64"
    assert python.url.endswith("python-3.13.15-h254dcb4_103_cp313.conda")
    assert python.depends == ("libzlib >=1.3.2,<2.0a0", "ucrt >=10.0.20348.0")
    assert python.sha256 == hashlib.sha256(archive_bytes(python.url)).hexdigest()


def test_read_lock_packages_maps_a_named_platform_to_its_subdir(lock_path):
    packages = bpu.read_lock_packages(lock_path, "prod", "linux-aarch64")

    assert list(packages) == ["zlib"]


def test_read_plugin_names_takes_the_plugin_features(lock_path):
    names = bpu.read_plugin_names(lock_path.with_name("pyproject.toml"))

    assert names == ["heater-microdrop-plugin", "magnet-microdrop-plugin"]


def test_read_base_from_a_pack(tmp_path, base_packages):
    pack_path = write_pack(tmp_path / "microdrop-prod-slim-win-64.tar")

    packages, identity = bpu.read_base(pack_path, "prod", "win-64")

    assert packages == base_packages
    assert identity == {
        "source": "microdrop-prod-slim-win-64.tar",
        "kind": "pack",
        "pack": "microdrop-prod-slim-win-64.tar",
        "pixi_pack_version": "0.7.11",
        "microdrop_version": "1.24.2",
    }


def test_read_base_from_a_hand_off_zip(tmp_path, base_packages):
    pack_path = write_pack(tmp_path / "microdrop-prod-slim-win-64.tar")
    zip_path = tmp_path / "share-microdrop-1.24.2-win-64-AI-support.zip"

    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(pack_path, f"share-microdrop/{pack_path.name}")
        archive.writestr("share-microdrop/install.bat", "@echo off")

    packages, identity = bpu.read_base(zip_path, "prod", "win-64")

    assert packages == base_packages
    assert identity["kind"] == "hand-off zip"
    assert identity["pack"] == pack_path.name
    assert identity["source"] == zip_path.name


def test_read_base_from_an_install_folder(tmp_path, base_packages):
    conda_meta = tmp_path / "MicroDrop" / "env" / "conda-meta"
    conda_meta.mkdir(parents=True)

    for name, (version, build, subdir) in BASE.items():
        record = {"name": name, "version": version, "build": build, "subdir": subdir}
        (conda_meta / f"{name}-{version}-{build}.json").write_text(json.dumps(record))

    (conda_meta / "history").write_text("")

    packages, identity = bpu.read_base(tmp_path / "MicroDrop", "prod", "win-64")

    assert packages == base_packages
    assert identity["kind"] == "install"


def test_read_base_from_a_lock(lock_path):
    packages, identity = bpu.read_base(lock_path, "prod", "win-64")

    assert "heater-microdrop-plugin" in packages
    assert identity == {"source": "pixi.lock", "kind": "lock"}


def select(lock_path, base_packages):
    target = bpu.read_lock_packages(lock_path, "prod", "win-64")
    plugins = ["heater-microdrop-plugin", "magnet-microdrop-plugin"]
    install = bpu.select_install_names(target, base_packages, plugins)

    return {
        package.name: package
        for package in bpu.select_update_packages(target, base_packages, install)
    }


def test_select_install_names_adds_packages_new_to_the_base(lock_path, base_packages):
    target = bpu.read_lock_packages(lock_path, "prod", "win-64")
    plugins = ["heater-microdrop-plugin", "magnet-microdrop-plugin"]

    names = bpu.select_install_names(target, base_packages, plugins)

    # The plugins, plus every package the base lacks by name - except the
    # toolchain a slim pack strips (clang). Changed numpy is not installed.
    assert names == [
        "heater-microdrop-plugin",
        "magnet-microdrop-plugin",
        "mpmath",
        "send2trash",
        "sympy",
    ]


def test_select_always_includes_the_plugins(lock_path, base_packages):
    selected = select(lock_path, base_packages)

    # magnet is unchanged from the base but still ships, so its spec installs.
    assert selected["magnet-microdrop-plugin"].version == "1.2.1"
    assert selected["heater-microdrop-plugin"].version == "1.12.0"


def test_select_ships_new_and_changed_dependencies_only(lock_path, base_packages):
    selected = select(lock_path, base_packages)

    # New, through the plugin and transitively through the new package.
    assert "sympy" in selected
    assert "mpmath" in selected

    # Unchanged dependencies the install already has.
    assert "mpremote" not in selected
    assert "python" not in selected
    assert "ucrt" not in selected

    # Changed in the lock but outside the plugins' dependency closure.
    assert "numpy" not in selected

    # A workspace-level dependency no plugin declares still ships.
    assert "send2trash" in selected

    assert sorted(selected) == [
        "heater-microdrop-plugin",
        "magnet-microdrop-plugin",
        "mpmath",
        "send2trash",
        "sympy",
    ]


def test_select_ships_a_dependency_whose_version_changed(lock_path, base_packages):
    base_packages["python"] = bpu.Package("python", "3.13.14", "h_0", "win-64")

    selected = select(lock_path, base_packages)

    # python changed, so it ships; walking through it reaches libzlib, whose
    # build changed too, while unchanged ucrt stays out.
    assert selected["python"].version == "3.13.15"
    assert selected["libzlib"].version == "1.3.2"
    assert "ucrt" not in selected


def test_select_keeps_platform_and_noarch_subdirs(lock_path, base_packages):
    base_packages["python"] = bpu.Package("python", "3.13.14", "h_0", "win-64")

    selected = select(lock_path, base_packages)

    assert selected["python"].subdir == "win-64"
    assert selected["sympy"].subdir == "noarch"
    assert selected["heater-microdrop-plugin"].subdir == "noarch"


def test_select_leaves_out_toolchain_packages_a_slim_base_stripped(
    lock_path, base_packages
):
    base_packages.pop("python")
    target = bpu.read_lock_packages(lock_path, "prod", "win-64")
    target["python"] = target["python"]._replace(depends=("clang",))

    selected = bpu.select_update_packages(
        target, base_packages, ["heater-microdrop-plugin"]
    )
    names = [package.name for package in selected]

    assert "python" in names
    assert "clang" not in names


def test_select_fails_when_the_lock_lacks_a_plugin(lock_path, base_packages):
    target = bpu.read_lock_packages(lock_path, "prod", "win-64")

    with pytest.raises(SystemExit, match="fluorescence-microdrop-plugin"):
        bpu.select_install_names(
            target, base_packages, ["fluorescence-microdrop-plugin"]
        )


def test_write_manifest_writes_specs_and_base_plugins(tmp_path, lock_path):
    target = bpu.read_lock_packages(lock_path, "prod", "win-64")
    base = {
        name: bpu.Package(name, version, build, subdir)
        for name, (version, build, subdir) in BASE.items()
    }
    plugin_names = ["heater-microdrop-plugin", "magnet-microdrop-plugin"]
    install = [target[name] for name in plugin_names + ["sympy"]]
    channel = [target["heater-microdrop-plugin"], target["sympy"]]

    manifest = bpu.build_manifest(
        "2026-10-29",
        "win-64",
        "prod",
        {"source": "x.tar"},
        base,
        plugin_names,
        install,
        channel,
    )
    bpu.write_manifest(tmp_path, manifest)

    assert manifest["plugins"] == [
        "heater-microdrop-plugin=1.12.0=pyh4616a5c_0",
        "magnet-microdrop-plugin=1.2.1=pyh4616a5c_0",
    ]
    assert manifest["install"] == manifest["plugins"] + ["sympy=1.14.0=pyh2585a3b_105"]
    assert manifest["base"]["plugins"] == {
        "heater-microdrop-plugin": "1.10.1=pyh4616a5c_0",
        "magnet-microdrop-plugin": "1.2.1=pyh4616a5c_0",
    }
    assert manifest["base"]["packages"] == len(BASE)
    assert json.loads((tmp_path / "update.json").read_text()) == manifest

    assert (tmp_path / "specs.txt").read_bytes() == (
        b"heater-microdrop-plugin=1.12.0=pyh4616a5c_0\r\n"
        b"magnet-microdrop-plugin=1.2.1=pyh4616a5c_0\r\n"
        b"sympy=1.14.0=pyh2585a3b_105\r\n"
    )
    assert (tmp_path / "base-plugins.txt").read_bytes() == (
        b"heater-microdrop-plugin-1.10.1-pyh4616a5c_0\r\n"
        b"magnet-microdrop-plugin-1.2.1-pyh4616a5c_0\r\n"
    )


def test_build_plugin_update_smoke(tmp_path, monkeypatch, lock_path):
    dist = tmp_path / "dist"
    pack_path = write_pack(tmp_path / "microdrop-prod-slim-win-64.tar")
    downloads = []
    commands = []

    def fake_download(url, target):
        downloads.append(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive_bytes(url))

    monkeypatch.setattr(bpu, "DIST", dist)
    monkeypatch.setattr(bpu, "download", fake_download)
    monkeypatch.setattr(bpu.subprocess, "run", lambda *a, **k: commands.append(a))

    zip_path = bpu.build_plugin_update("win-64", "prod", pack_path, lock_path)

    date = datetime.date.today().isoformat()
    folder_name = f"microdrop-plugins-update-{date}-win-64"
    folder = dist / "share" / folder_name

    assert zip_path == dist / f"{folder_name}.zip"

    channel_files = sorted(
        path.relative_to(folder / "channel").as_posix()
        for path in (folder / "channel").rglob("*")
        if path.is_file()
    )

    # The indexer is stubbed, so both indexes are the empty fallbacks.
    assert channel_files == [
        "noarch/heater-microdrop-plugin-1.12.0-pyh4616a5c_0.conda",
        "noarch/magnet-microdrop-plugin-1.2.1-pyh4616a5c_0.conda",
        "noarch/mpmath-1.3.0-pyhd8ed1ab_1.conda",
        "noarch/repodata.json",
        "noarch/send2trash-1.8.3-pyh5737063_1.conda",
        "noarch/sympy-1.14.0-pyh2585a3b_105.conda",
        "win-64/repodata.json",
    ]
    assert commands[0][0][:4] == ["pixi", "exec", "--spec", bpu.RATTLER_INDEX_SPEC]

    # Downloads land in the pack-cache layout; micromamba is fetched once.
    assert (
        dist / "pack-cache" / "noarch" / "sympy-1.14.0-pyh2585a3b_105.conda"
    ).exists()
    assert sum("micromamba" in url for url in downloads) == 1

    manifest = json.loads((folder / "update.json").read_text())

    assert manifest["base"]["pack"] == pack_path.name
    assert manifest["base"]["microdrop_version"] == "1.24.2"
    assert len(manifest["channel"]) == 5
    assert "send2trash=1.8.3=pyh5737063_1" in manifest["install"]

    for name in (
        "update-plugins.bat",
        "fix-conda-meta.py",
        "README.txt",
        "specs.txt",
        "micromamba.exe",
    ):
        assert (folder / name).exists()

    assert b"\r\n" in (folder / "update-plugins.bat").read_bytes()
    assert b"heater-microdrop-plugin=1.12.0" in (folder / "README.txt").read_bytes()

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

    assert f"{folder_name}/update-plugins.bat" in names
    assert f"{folder_name}/channel/noarch/sympy-1.14.0-pyh2585a3b_105.conda" in names

    # A second build reuses the verified cache instead of downloading again.
    downloads.clear()
    bpu.build_plugin_update("win-64", "prod", pack_path, lock_path)

    assert downloads == []
