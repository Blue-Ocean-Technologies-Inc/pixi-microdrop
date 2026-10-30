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
from pathlib import Path

# Third-party imports.
import build_update as bu
import pytest
import yaml

CF = "https://conda.anaconda.org/conda-forge"
PLUGINS = "https://prefix.dev/microdrop-plugins"
PYPI = "https://files.pythonhosted.org/packages/00/00"

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

#: url -> name of the target environment's PyPI wheels.
PYPI_TARGET = {
    f"{PYPI}/loguru-0.7.3-py3-none-any.whl": "loguru",
    f"{PYPI}/pyside6-6.11.2-cp310-abi3-win_amd64.whl": "pyside6",
}

#: The target's PyPI path dependencies: the MicroDrop app and the ICU preload.
PATH_DEPENDENCIES = {
    "./": "microdrop-py",
    "../pyside6-icu-preload": "pyside6-icu-preload",
}

#: The versions the faked wheel build gives the path dependencies.
BUILT_VERSIONS = {"microdrop-py": "1.33.0", "pyside6-icu-preload": "0.1.0"}

#: name -> (version, build, subdir) of the base pack the customer has.
BASE = {
    "heater-microdrop-plugin": ("1.10.1", "pyh4616a5c_0", "noarch"),
    "magnet-microdrop-plugin": ("1.2.1", "pyh4616a5c_0", "noarch"),
    "mpremote": ("1.25.0", "py_0", "noarch"),
    "python": ("3.13.15", "h254dcb4_103_cp313", "win-64"),
    # Changed build in the target: must ship.
    "libzlib": ("1.3.1", "h2466b09_2", "win-64"),
    # Changed version in the target: must ship.
    "numpy": ("2.2.0", "py313h_0", "win-64"),
    "ucrt": ("10.0.26100.0", "h57928b3_0", "win-64"),
}

#: The base pack's wheels: MicroDrop and PySide6 older than the target.
BASE_WHEELS = (
    "microdrop_py-1.24.2-py3-none-any.whl",
    "loguru-0.7.3-py3-none-any.whl",
    "pyside6-6.9.3-cp39-abi3-win_amd64.whl",
    "pyside6_icu_preload-0.1.0-py3-none-any.whl",
)

#: PyPI name -> version of BASE_WHEELS.
BASE_PYPI = {
    "microdrop-py": "1.24.2",
    "loguru": "0.7.3",
    "pyside6": "6.9.3",
    "pyside6-icu-preload": "0.1.0",
}

#: What BASE lacks or has at another version/build: the changed plugin and
#: libzlib and numpy, the new sympy (with mpmath) and send2trash. Unchanged
#: magnet, mpremote and python stay out, and so does clang, the toolchain a
#: slim pack strips.
CHANGED_FROM_BASE = [
    "heater-microdrop-plugin",
    "libzlib",
    "mpmath",
    "numpy",
    "send2trash",
    "sympy",
]


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
                    "win-64": [{"conda": url} for url in TARGET]
                    + [{"pypi": url} for url in PYPI_TARGET]
                    + [{"pypi": location} for location in PATH_DEPENDENCIES],
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
        + [{"conda": f"{CF}/linux-aarch64/zlib-1-h_0.conda", "sha256": "0"}]
        + [
            {
                "pypi": url,
                "name": name,
                "version": url.rsplit("/", 1)[1].split("-")[1],
                "sha256": hashlib.sha256(archive_bytes(url)).hexdigest(),
            }
            for url, name in PYPI_TARGET.items()
        ]
        + [
            {"pypi": location, "name": name}
            for location, name in PATH_DEPENDENCIES.items()
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
    """A pixi-pack style tar: channel repodata, metadata and wheels."""

    members = {
        "pixi-pack.json": json.dumps({"pixi-pack-version": "0.7.11"}).encode(),
        "channel/noarch/repodata.json": json.dumps(repodata("noarch")).encode(),
        "channel/win-64/repodata.json": json.dumps(repodata("win-64")).encode(),
    }
    members.update({f"pypi/{wheel}": b"wheel" for wheel in BASE_WHEELS})

    with tarfile.open(path, "w") as pack:
        for name, data in members.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            pack.addfile(member, io.BytesIO(data))

    return path


def write_install(folder, git=False):
    """An installed MicroDrop folder of the BASE packages and wheels.

    A git install links MicroDrop's clone instead of its wheel.
    """

    conda_meta = folder / "env" / "conda-meta"
    conda_meta.mkdir(parents=True)

    for name, (version, build, subdir) in BASE.items():
        record = {"name": name, "version": version, "build": build, "subdir": subdir}
        (conda_meta / f"{name}-{version}-{build}.json").write_text(json.dumps(record))

    (conda_meta / "history").write_text("")

    site_packages = folder / "env" / "Lib" / "site-packages"

    for wheel in BASE_WHEELS:
        if git and wheel.startswith("microdrop_py-"):
            continue

        name, version = wheel.split("-")[:2]
        (site_packages / f"{name}-{version}.dist-info").mkdir(parents=True)

    # Conda's Python packages have a .dist-info too.
    (site_packages / "mpremote-1.25.0.dist-info").mkdir()

    if git:
        (site_packages / "microdrop_git.pth").write_text(str(folder / "microdrop"))

    return folder


@pytest.fixture
def lock_path(tmp_path):
    return write_lock(tmp_path / "pixi.lock")


@pytest.fixture
def base_packages():
    return {
        name: bu.Package(name, version, build, subdir)
        for name, (version, build, subdir) in BASE.items()
    }


def test_package_from_url_reads_name_version_build_and_subdir():
    package = bu.package_from_url(
        f"{PLUGINS}/noarch/heater-microdrop-plugin-1.12.0-pyh4616a5c_0.conda"
    )

    assert package.name == "heater-microdrop-plugin"
    assert package.version == "1.12.0"
    assert package.build == "pyh4616a5c_0"
    assert package.subdir == "noarch"

    legacy = bu.package_from_url(f"{CF}/noarch/mpremote-1.25.0-py_0.tar.bz2")

    assert (legacy.name, legacy.version, legacy.build) == ("mpremote", "1.25.0", "py_0")


def test_distribution_name_version_reads_wheels_and_dist_info():
    assert bu.distribution_name_version(
        "pyside6_icu_preload-0.1.0-py3-none-any.whl"
    ) == ("pyside6-icu-preload", "0.1.0")
    assert bu.distribution_name_version("PySocks-1.7.1.dist-info") == (
        "pysocks",
        "1.7.1",
    )


def test_read_lock_packages_reads_one_environment_and_platform(lock_path):
    packages = bu.read_lock_packages(lock_path, "prod", "win-64")

    assert set(packages) == {bu.package_from_url(url).name for url in TARGET}

    python = packages["python"]

    assert python.subdir == "win-64"
    assert python.url.endswith("python-3.13.15-h254dcb4_103_cp313.conda")
    assert python.depends == ("libzlib >=1.3.2,<2.0a0", "ucrt >=10.0.20348.0")
    assert python.sha256 == hashlib.sha256(archive_bytes(python.url)).hexdigest()


def test_read_lock_packages_maps_a_named_platform_to_its_subdir(lock_path):
    packages = bu.read_lock_packages(lock_path, "prod", "linux-aarch64")

    assert list(packages) == ["zlib"]


def test_read_lock_pypi_packages_reads_wheels_and_path_dependencies(lock_path):
    packages = bu.read_lock_pypi_packages(lock_path, "prod", "win-64")

    assert sorted(packages) == [
        "loguru",
        "microdrop-py",
        "pyside6",
        "pyside6-icu-preload",
    ]

    pyside6 = packages["pyside6"]

    assert pyside6.version == "6.11.2"
    assert pyside6.sha256 == hashlib.sha256(archive_bytes(pyside6.url)).hexdigest()

    microdrop = packages["microdrop-py"]

    assert microdrop.version is None
    assert microdrop.url is None
    assert microdrop.path == lock_path.parent / "./"
    assert packages["pyside6-icu-preload"].path == (
        lock_path.parent / "../pyside6-icu-preload"
    )


def test_read_plugin_names_takes_the_plugin_features(lock_path):
    names = bu.read_plugin_names(lock_path.with_name("pyproject.toml"))

    assert names == ["heater-microdrop-plugin", "magnet-microdrop-plugin"]


def test_read_base_from_a_pack(tmp_path, base_packages):
    pack_path = write_pack(tmp_path / "microdrop-prod-slim-win-64.tar")

    packages, pypi, identity = bu.read_base(pack_path, "prod", "win-64")

    assert packages == base_packages
    assert pypi == BASE_PYPI
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

    packages, pypi, identity = bu.read_base(zip_path, "prod", "win-64")

    assert packages == base_packages
    assert pypi == BASE_PYPI
    assert identity["kind"] == "hand-off zip"
    assert identity["pack"] == pack_path.name
    assert identity["source"] == zip_path.name


def test_read_base_from_an_install_folder(tmp_path, base_packages):
    folder = write_install(tmp_path / "MicroDrop")

    packages, pypi, identity = bu.read_base(folder, "prod", "win-64")

    assert packages == base_packages
    assert pypi == BASE_PYPI | {"mpremote": "1.25.0"}
    assert identity == {
        "source": "MicroDrop",
        "kind": "install",
        "microdrop_version": "1.24.2",
    }


def test_read_base_from_a_git_install_leaves_out_microdrop(tmp_path):
    folder = write_install(tmp_path / "MicroDrop", git=True)

    _, pypi, identity = bu.read_base(folder, "prod", "win-64")

    assert "microdrop-py" not in pypi
    assert identity["microdrop_version"] == "git"


def test_read_base_from_a_lock(lock_path):
    packages, pypi, identity = bu.read_base(lock_path, "prod", "win-64")

    assert "heater-microdrop-plugin" in packages
    assert pypi["loguru"] == "0.7.3"
    assert pypi["microdrop-py"] is None
    assert identity == {"source": "pixi.lock", "kind": "lock"}


def select(lock_path, base_packages):
    target = bu.read_lock_packages(lock_path, "prod", "win-64")
    install = bu.select_install_names(target, base_packages)

    return {
        package.name: package
        for package in bu.select_update_packages(target, base_packages, install)
    }


def test_select_install_names_takes_every_changed_package(lock_path, base_packages):
    target = bu.read_lock_packages(lock_path, "prod", "win-64")

    names = bu.select_install_names(target, base_packages)

    assert names == CHANGED_FROM_BASE


def test_select_install_names_keeps_toolchain_packages_the_base_has(
    lock_path, base_packages
):
    target = bu.read_lock_packages(lock_path, "prod", "win-64")
    base_packages["clang"] = bu.Package("clang", "19.1.0", "h_0", "win-64")

    names = bu.select_install_names(target, base_packages)

    assert "clang" in names


def test_select_ships_exactly_the_changed_packages(lock_path, base_packages):
    selected = select(lock_path, base_packages)

    assert sorted(selected) == CHANGED_FROM_BASE


def test_select_ships_a_dependency_whose_version_changed(lock_path, base_packages):
    base_packages["python"] = bu.Package("python", "3.13.14", "h_0", "win-64")

    selected = select(lock_path, base_packages)

    # python changed, so it ships; walking through it reaches libzlib, whose
    # build changed too, while unchanged ucrt stays out.
    assert selected["python"].version == "3.13.15"
    assert selected["libzlib"].version == "1.3.2"
    assert "ucrt" not in selected


def test_select_keeps_platform_and_noarch_subdirs(lock_path, base_packages):
    base_packages["python"] = bu.Package("python", "3.13.14", "h_0", "win-64")

    selected = select(lock_path, base_packages)

    assert selected["python"].subdir == "win-64"
    assert selected["sympy"].subdir == "noarch"
    assert selected["heater-microdrop-plugin"].subdir == "noarch"


def test_select_leaves_out_toolchain_packages_a_slim_base_stripped(
    lock_path, base_packages
):
    base_packages.pop("python")
    target = bu.read_lock_packages(lock_path, "prod", "win-64")
    target["python"] = target["python"]._replace(depends=("clang",))

    selected = bu.select_update_packages(
        target, base_packages, ["heater-microdrop-plugin"]
    )
    names = [package.name for package in selected]

    assert "python" in names
    assert "clang" not in names


def test_select_full_install_names_takes_all_but_the_toolchain(lock_path):
    target = bu.read_lock_packages(lock_path, "prod", "win-64")

    names = bu.select_full_install_names(target)

    assert names == sorted(set(target) - {"clang"})


def built_target_pypi(lock_path):
    """The lock's PyPI packages, the path dependencies at BUILT_VERSIONS."""

    packages = bu.read_lock_pypi_packages(lock_path, "prod", "win-64")

    for name, version in BUILT_VERSIONS.items():
        packages[name] = packages[name]._replace(version=version)

    return packages


def test_select_pypi_names_takes_changed_and_missing_packages(lock_path):
    target = built_target_pypi(lock_path)

    # loguru and the ICU preload are unchanged.
    assert bu.select_pypi_names(target, BASE_PYPI) == ["microdrop-py", "pyside6"]

    assert bu.select_pypi_names(target, {"microdrop-py": "1.33.0"}) == [
        "loguru",
        "pyside6",
        "pyside6-icu-preload",
    ]


def test_select_pypi_names_skips_microdrop_for_a_base_without_it(lock_path):
    target = built_target_pypi(lock_path)
    git_base = dict(BASE_PYPI)
    git_base.pop("microdrop-py")

    assert bu.select_pypi_names(target, git_base) == ["pyside6"]


def test_select_pypi_names_takes_unknown_base_versions_as_changed(lock_path):
    target = built_target_pypi(lock_path)
    lock_base = BASE_PYPI | {"microdrop-py": None, "pyside6": "6.11.2"}

    assert bu.select_pypi_names(target, lock_base) == ["microdrop-py"]


def test_path_dependencies_to_build_skips_microdrop_for_git_bases(lock_path):
    target = bu.read_lock_pypi_packages(lock_path, "prod", "win-64")
    git_base = {"loguru": "0.7.3"}

    assert bu.path_dependencies_to_build(target, [git_base]) == ["pyside6-icu-preload"]
    assert bu.path_dependencies_to_build(target, [git_base, BASE_PYPI]) == [
        "microdrop-py",
        "pyside6-icu-preload",
    ]
    assert bu.path_dependencies_to_build(target, [], full=True) == [
        "microdrop-py",
        "pyside6-icu-preload",
    ]


def fake_uv_build(wheel_name, commands=None):
    """A ``subprocess.run`` stand-in that "builds" one wheel into ``-o``."""

    def run(command, check):
        if commands is not None:
            commands.append(command)

        out_dir = command[command.index("-o") + 1]
        (Path(out_dir) / wheel_name).write_bytes(b"")

    return run


@pytest.mark.parametrize(
    "version", ["1.33.0.post2+gc7d3c40e3.d20261030", bu.FALLBACK_VERSION]
)
def test_build_path_wheel_refuses_untraceable_versions(
    tmp_path, monkeypatch, lock_path, version
):
    microdrop = bu.read_lock_pypi_packages(lock_path, "prod", "win-64")["microdrop-py"]
    wheel_name = f"microdrop_py-{version}-py3-none-any.whl"
    monkeypatch.setattr(bu.subprocess, "run", fake_uv_build(wheel_name))

    with pytest.raises(SystemExit, match="uncommitted changes or no git history"):
        bu.build_path_wheel(microdrop, tmp_path / "wheels")


def test_build_path_wheel_returns_the_version_and_wheel(
    tmp_path, monkeypatch, lock_path
):
    microdrop = bu.read_lock_pypi_packages(lock_path, "prod", "win-64")["microdrop-py"]
    wheel_name = "microdrop_py-1.33.0.post2+gc7d3c40e3-py3-none-any.whl"
    commands = []
    monkeypatch.setattr(bu.subprocess, "run", fake_uv_build(wheel_name, commands))

    built = bu.build_path_wheel(microdrop, tmp_path / "wheels")

    assert commands[0][:5] == ["pixi", "exec", "uv", "build", "--wheel"]
    assert commands[0][-1] == str(microdrop.path)
    assert built.version == "1.33.0.post2+gc7d3c40e3"
    assert built.path == tmp_path / "wheels" / wheel_name


def test_default_bases_takes_the_environments_slim_packs_and_hand_off_zips(
    tmp_path, monkeypatch
):
    for name in (
        "microdrop-prod-win-64.tar",
        "microdrop-prod-slim-win-64.tar",
        "microdrop-prod-no-ai-slim-win-64.tar",
        "share-microdrop-1.23.0-win-64-AI-support.zip",
        "share-microdrop-1.23.0-win-64-no-AI.zip",
        "share-microdrop-git-v1.24.2-8-g684be6ba-win-64.zip",
        "share-microdrop-1.23.0-linux-64.zip",
        "microdrop-update-2026-10-30-win-64.zip",
    ):
        (tmp_path / name).write_text("")

    monkeypatch.setattr(bu, "DIST", tmp_path)

    names = [path.name for path in bu.default_bases("prod", "win-64")]

    assert names == [
        "microdrop-prod-slim-win-64.tar",
        "share-microdrop-1.23.0-win-64-AI-support.zip",
        "share-microdrop-git-v1.24.2-8-g684be6ba-win-64.zip",
    ]

    names = [path.name for path in bu.default_bases("prod-no-ai", "win-64")]

    assert names == [
        "microdrop-prod-no-ai-slim-win-64.tar",
        "share-microdrop-1.23.0-win-64-no-AI.zip",
    ]


def test_write_manifest_writes_the_spec_lists(tmp_path, lock_path):
    target = bu.read_lock_packages(lock_path, "prod", "win-64")
    target_pypi = built_target_pypi(lock_path)
    base = {
        name: bu.Package(name, version, build, subdir)
        for name, (version, build, subdir) in BASE.items()
    }
    plugin_names = ["heater-microdrop-plugin", "magnet-microdrop-plugin"]
    bases = [bu.describe_base({"source": "x.tar"}, base, BASE_PYPI, plugin_names)]
    install = [target[name] for name in ("clang", "heater-microdrop-plugin", "sympy")]
    channel = [target["heater-microdrop-plugin"], target["sympy"]]
    pypi = [target_pypi["microdrop-py"], target_pypi["pyside6"]]

    manifest = bu.build_manifest(
        "2026-10-29", "win-64", "prod", bases, plugin_names, install, channel, pypi
    )
    bu.write_manifest(tmp_path, manifest)

    assert manifest["plugins"] == ["heater-microdrop-plugin=1.12.0=pyh4616a5c_0"]
    assert manifest["install"] == [
        "heater-microdrop-plugin=1.12.0=pyh4616a5c_0",
        "sympy=1.14.0=pyh2585a3b_105",
    ]
    assert manifest["optional"] == ["clang=20.1.0=h_0"]
    assert manifest["pypi"] == ["microdrop-py==1.33.0", "pyside6==6.11.2"]
    assert manifest["bases"][0]["plugins"] == {
        "heater-microdrop-plugin": "1.10.1=pyh4616a5c_0",
        "magnet-microdrop-plugin": "1.2.1=pyh4616a5c_0",
    }
    assert manifest["bases"][0]["packages"] == len(BASE)
    assert manifest["bases"][0]["pypi_packages"] == len(BASE_PYPI)
    assert json.loads((tmp_path / "update.json").read_text()) == manifest

    assert (tmp_path / "specs.txt").read_bytes() == (
        b"heater-microdrop-plugin=1.12.0=pyh4616a5c_0\r\n"
        b"sympy=1.14.0=pyh2585a3b_105\r\n"
    )
    assert (tmp_path / "optional-specs.txt").read_bytes() == b"clang=20.1.0=h_0\r\n"
    assert (tmp_path / "plugins.txt").read_bytes() == b"heater-microdrop-plugin\r\n"

    # MicroDrop's wheel is listed apart, so a git install can skip it.
    assert (tmp_path / "pypi-specs.txt").read_bytes() == b"pyside6==6.11.2\r\n"
    assert (tmp_path / "microdrop-spec.txt").read_bytes() == (
        b"microdrop-py==1.33.0\r\n"
    )


@pytest.fixture
def fake_dist(tmp_path, monkeypatch):
    """Point the builder at an empty dist/ with stubbed downloads, wheel
    builds and indexer.

    Returns the dist folder, the downloaded URLs, the indexer commands run
    and the path dependencies built.
    """

    dist = tmp_path / "dist"
    downloads = []
    commands = []
    built = []

    def fake_download(url, target):
        downloads.append(url)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive_bytes(url))

    def fake_build_path_wheel(package, out_dir):
        built.append(package.name)
        version = BUILT_VERSIONS[package.name]
        wheel = out_dir / f"{package.name.replace('-', '_')}-{version}-py3-none-any.whl"
        wheel.parent.mkdir(parents=True, exist_ok=True)
        wheel.write_bytes(b"built")

        return package._replace(version=version, path=wheel)

    monkeypatch.setattr(bu, "DIST", dist)
    monkeypatch.setattr(bu, "download", fake_download)
    monkeypatch.setattr(bu, "build_path_wheel", fake_build_path_wheel)
    monkeypatch.setattr(bu.subprocess, "run", lambda *a, **k: commands.append(a))

    return dist, downloads, commands, built


def bundle_folder(dist):
    return dist / "share" / f"microdrop-update-{datetime.date.today()}-win-64"


def bundle_files(dist, subfolder):
    folder = bundle_folder(dist) / subfolder

    return sorted(
        path.relative_to(folder).as_posix()
        for path in folder.rglob("*")
        if path.is_file()
    )


def test_build_update_smoke(tmp_path, fake_dist, lock_path):
    dist, downloads, commands, built = fake_dist
    pack_path = write_pack(tmp_path / "microdrop-prod-slim-win-64.tar")

    zip_path = bu.build_update("win-64", "prod", [pack_path], lock_path)

    folder = bundle_folder(dist)
    folder_name = folder.name

    assert zip_path == dist / f"{folder_name}.zip"

    # The indexer is stubbed, so both indexes are the empty fallbacks.
    assert bundle_files(dist, "channel") == [
        "noarch/heater-microdrop-plugin-1.12.0-pyh4616a5c_0.conda",
        "noarch/mpmath-1.3.0-pyhd8ed1ab_1.conda",
        "noarch/repodata.json",
        "noarch/send2trash-1.8.3-pyh5737063_1.conda",
        "noarch/sympy-1.14.0-pyh2585a3b_105.conda",
        "win-64/libzlib-1.3.2-h2466b09_0.conda",
        "win-64/numpy-2.3.0-py313h_0.conda",
        "win-64/repodata.json",
    ]
    assert commands[0][0][:4] == ["pixi", "exec", "--spec", bu.RATTLER_INDEX_SPEC]

    # The path dependencies are built to learn their versions; only the
    # changed MicroDrop and PySide6 wheels ship.
    assert sorted(built) == ["microdrop-py", "pyside6-icu-preload"]
    assert bundle_files(dist, "wheels") == [
        "microdrop_py-1.33.0-py3-none-any.whl",
        "pyside6-6.11.2-cp310-abi3-win_amd64.whl",
    ]

    # Downloads land in the pack-cache layout; micromamba is fetched once.
    cache = dist / "pack-cache"

    assert (cache / "noarch" / "sympy-1.14.0-pyh2585a3b_105.conda").exists()
    assert (cache / "pypi" / "pyside6-6.11.2-cp310-abi3-win_amd64.whl").exists()
    assert sum("micromamba" in url for url in downloads) == 1

    manifest = json.loads((folder / "update.json").read_text())

    assert manifest["full"] is False
    assert manifest["bases"][0]["pack"] == pack_path.name
    assert manifest["bases"][0]["microdrop_version"] == "1.24.2"
    assert len(manifest["channel"]) == 6
    assert "send2trash=1.8.3=pyh5737063_1" in manifest["install"]
    assert manifest["pypi"] == ["microdrop-py==1.33.0", "pyside6==6.11.2"]

    for name in (
        "apply-update.bat",
        "fix-conda-meta.py",
        "README.txt",
        "specs.txt",
        "optional-specs.txt",
        "plugins.txt",
        "pypi-specs.txt",
        "microdrop-spec.txt",
        "micromamba.exe",
    ):
        assert (folder / name).exists()

    assert b"\r\n" in (folder / "apply-update.bat").read_bytes()

    readme = (folder / "README.txt").read_bytes()

    assert b"It installs 8 packages" in readme
    assert b"heater-microdrop-plugin=1.12.0" in readme
    assert b"MicroDrop itself is updated to 1.33.0" in readme

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()

    assert f"{folder_name}/apply-update.bat" in names
    assert f"{folder_name}/channel/noarch/sympy-1.14.0-pyh2585a3b_105.conda" in names
    assert f"{folder_name}/wheels/microdrop_py-1.33.0-py3-none-any.whl" in names

    # A second build reuses the verified cache instead of downloading again.
    downloads.clear()
    bu.build_update("win-64", "prod", [pack_path], lock_path)

    assert downloads == []


def test_build_update_covers_the_union_of_several_bases(tmp_path, fake_dist, lock_path):
    dist, _, _, _ = fake_dist
    pack_path = write_pack(tmp_path / "microdrop-prod-slim-win-64.tar")

    # A git install that is current but for an older magnet plugin.
    folder = write_install(tmp_path / "MicroDrop", git=True)
    conda_meta = folder / "env" / "conda-meta"

    for record_path in conda_meta.glob("*.json"):
        record_path.unlink()

    for url in TARGET:
        package = bu.package_from_url(url)

        if package.name == "magnet-microdrop-plugin":
            package = package._replace(version="1.2.0")

        record = package._asdict() | {"depends": []}
        (conda_meta / f"{bu.package_stem(package)}.json").write_text(json.dumps(record))

    bu.build_update("win-64", "prod", [pack_path, folder], lock_path)

    manifest = json.loads((bundle_folder(dist) / "update.json").read_text())

    assert [base["kind"] for base in manifest["bases"]] == ["pack", "install"]
    assert manifest["bases"][1]["microdrop_version"] == "git"
    assert "magnet-microdrop-plugin=1.2.1=pyh4616a5c_0" in manifest["install"]
    assert "heater-microdrop-plugin=1.12.0=pyh4616a5c_0" in manifest["install"]
    assert len(manifest["install"]) == len(CHANGED_FROM_BASE) + 1

    # The pack base has the MicroDrop wheel, so it ships for it.
    assert "microdrop-py==1.33.0" in manifest["pypi"]


def test_build_update_for_a_git_install_ships_no_microdrop_wheel(
    tmp_path, fake_dist, lock_path
):
    dist, _, _, built = fake_dist
    folder = write_install(tmp_path / "MicroDrop", git=True)

    bu.build_update("win-64", "prod", [folder], lock_path)

    manifest = json.loads((bundle_folder(dist) / "update.json").read_text())

    assert built == ["pyside6-icu-preload"]
    assert manifest["pypi"] == ["pyside6==6.11.2"]
    assert (bundle_folder(dist) / "microdrop-spec.txt").read_bytes() == b""
    assert (
        b"not part of this update" in (bundle_folder(dist) / "README.txt").read_bytes()
    )


def test_build_update_full_ships_the_whole_environment(fake_dist, lock_path):
    dist, _, _, built = fake_dist

    bu.build_update("win-64", "prod", [], lock_path, full=True)

    manifest = json.loads((bundle_folder(dist) / "update.json").read_text())

    assert manifest["full"] is True
    assert manifest["bases"] == []
    assert len(manifest["install"]) == len(TARGET) - 1
    assert manifest["optional"] == []
    assert not any("clang" in path for path in bundle_files(dist, "channel"))
    assert sorted(built) == ["microdrop-py", "pyside6-icu-preload"]
    assert len(manifest["pypi"]) == len(PYPI_TARGET) + len(PATH_DEPENDENCIES)


def test_select_held_back_names_takes_packages_needing_a_stripped_toolchain(
    lock_path, base_packages
):
    target = bu.read_lock_packages(lock_path, "prod", "win-64")
    target["numpy"] = target["numpy"]._replace(depends=("clang >=20", "python"))
    names = bu.select_install_names(target, base_packages)

    # micromamba could not solve numpy without clang, which the base lacks.
    assert bu.select_held_back_names(target, base_packages, names) == ["numpy"]

    base_packages["clang"] = bu.Package("clang", "20.1.0", "h_0", "win-64")

    assert bu.select_held_back_names(target, base_packages, names) == []
