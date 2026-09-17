# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Assemble the offline hand-off folder and zip around a slim prod pack.

The hand-off is what a user without git receives: the packed environment,
the pixi-unpack binary that installs it, install/run scripts, a README, and
- for a pack that carries the AI stack - the default SAM model weights, so
AI ROI detection works without a first-use download.

Everything here is reproducible from the repo plus downloads, so the output
lives under the git-ignored ``dist/`` and can be deleted freely.

Usage: python build_share.py <platform> <environment>
"""

# Standard library imports.
import json
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
TEMPLATES = ROOT / "share"

#: The install/run scripts are Windows batch files; other platforms have no
#: hand-off scripts yet.
HANDOFF_PLATFORM = "win-64"

PIXI_UNPACK_URL = (
    "https://github.com/Quantco/pixi-pack/releases/download/"
    "v{version}/pixi-unpack-x86_64-pc-windows-msvc.exe"
)

#: Must match the fluorescence plugin's DEFAULT_AI_MODEL, or the bundled
#: weights are not the ones the app asks for.
DEFAULT_AI_MODEL = "efficientsam:latest"

NO_AI_NOTE = """
This build leaves out AI-assisted fluorescence ROI detection; those options
are disabled in the Image Viewer. The in-app "download AI support" action
does not work in an offline install - use the AI-support package instead.
"""

MODELS_ENTRY = """\
models\\             AI model weights (EfficientSAM, ~100 MB); install.bat
                    copies them to %USERPROFILE%\\.cache\\osam so AI ROI
                    detection works without internet. Other models picked
                    in Preferences download on first use.
"""


def read_pack_info(pack_path):
    """Read what the hand-off depends on out of the pack itself.

    Returns
    -------
    tuple
        (pixi-pack version, MicroDrop version, whether the AI stack is packed)
    """

    microdrop_version = None
    has_ai = False

    with tarfile.open(pack_path) as pack:
        metadata = json.load(pack.extractfile("pixi-pack.json"))
        pixi_pack_version = metadata["pixi-pack-version"]

        for member in pack:
            filename = member.name.removeprefix("pypi/")

            if filename.startswith("microdrop_py-"):
                microdrop_version = filename.split("-")[1]

            elif filename.startswith("osam-"):
                has_ai = True

    if microdrop_version is None:
        raise ValueError(f"{pack_path} contains no microdrop_py wheel")

    return pixi_pack_version, microdrop_version, has_ai


def fetch_pixi_unpack(version):
    """Return a cached pixi-unpack.exe matching the pack's pixi-pack version."""

    cached = DIST / "pack-cache" / f"pixi-unpack-{version}.exe"

    if cached.exists() and cached.stat().st_size > 0:
        return cached

    cached.parent.mkdir(parents=True, exist_ok=True)
    url = PIXI_UNPACK_URL.format(version=version)
    print(f"downloading {url}")

    # Download beside the target and rename, so an interrupted download never
    # leaves a truncated file that the size check above would accept.
    partial = cached.with_suffix(".part")

    with urllib.request.urlopen(url) as response, open(partial, "wb") as out:
        shutil.copyfileobj(response, out)

    partial.replace(cached)

    return cached


def collect_model_blobs(model_name):
    """Return the weight files of an osam model, downloading them if needed."""

    # osam lives in the `ai` feature; imported here so a no-AI hand-off can be
    # built from an environment without it.
    import osam

    model_type = osam.apis.get_model_type_by_name(model_name)
    model_type.pull()

    blobs = []

    for blob in model_type._blobs.values():
        blobs.append(Path(blob.path))
        blobs.extend(Path(attachment.path) for attachment in blob.attachments)

    return blobs


def write_windows_text(path, text):
    # cmd.exe mis-parses labels in LF-only batch files, and the checkout's
    # line endings depend on the builder's git config.
    normalized = text.replace("\r\n", "\n").replace("\n", "\r\n")
    path.write_bytes(normalized.encode("ascii"))


def build_share(platform, environment):
    if platform != HANDOFF_PLATFORM:
        raise SystemExit(
            f"hand-off scripts only exist for {HANDOFF_PLATFORM}, not {platform}"
        )

    pack_path = DIST / f"microdrop-{environment}-slim-{platform}.tar"
    pixi_pack_version, microdrop_version, has_ai = read_pack_info(pack_path)

    folder_name = "share-microdrop" if has_ai else "share-microdrop-no-ai"
    variant = "AI-support" if has_ai else "no-AI"
    folder = DIST / "share" / folder_name

    if folder.exists():
        shutil.rmtree(folder)

    folder.mkdir(parents=True)

    for script in ("install.bat", "run-microdrop.bat"):
        write_windows_text(folder / script, (TEMPLATES / script).read_text())

    title = "MicroDrop for Windows (64-bit)"

    if not has_ai:
        title += " - no AI support"

    readme = (
        (TEMPLATES / "README.txt")
        .read_text()
        .format(
            title=title,
            title_rule="=" * len(title),
            variant_note="" if has_ai else NO_AI_NOTE,
            pack_name=pack_path.name,
            models_entry=MODELS_ENTRY if has_ai else "",
            version=microdrop_version,
        )
    )
    write_windows_text(folder / "README.txt", readme)

    shutil.copy2(pack_path, folder / pack_path.name)
    shutil.copy2(fetch_pixi_unpack(pixi_pack_version), folder / "pixi-unpack.exe")

    if has_ai:
        models = folder / "models"
        models.mkdir()

        for blob in collect_model_blobs(DEFAULT_AI_MODEL):
            shutil.copy2(blob, models / blob.name)

    zip_path = DIST / f"share-microdrop-{microdrop_version}-{platform}-{variant}.zip"

    # Fastest deflate level: the payload is mostly already-compressed package
    # archives, so higher levels cost minutes for no gain; level 1 is nearly
    # free and still shrinks the binaries and wheels a little.
    with zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=1
    ) as archive:
        for path in sorted(folder.rglob("*")):
            archive.write(path, Path(folder_name) / path.relative_to(folder))

    print(f"folder: {folder}")
    print(f"zip:    {zip_path} ({zip_path.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    build_share(sys.argv[1], sys.argv[2])
