# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Preload the system Pango stack so system GStreamer's libav plugin loads.

On Linux, Qt Multimedia uses the system GStreamer. Its ``libgstlibav.so``
(``avdec_h264``) links Pango through libavfilter. conda's Python carries a
DT_RPATH of ``$ORIGIN/../lib``, which applies to every library without its
own RUNPATH, so the plugin's ``libpangoft2-1.0.so.0`` resolves to the conda
copy. That copy needs ``FcConfigSetDefaultSubstitute`` (fontconfig >= 2.17),
but Qt has already bound the older system fontconfig, so the plugin load
fails: MicroDrop cannot play its own recordings, and the Qt recorder writes
files of only a few frames.

Loading the system freetype, fontconfig and Pango first, with RTLD_GLOBAL,
makes the loader reuse them by soname: Qt keeps the same system font stack
it would load anyway, and the plugin gets a consistent system Pango.

Runs at interpreter startup from ``gst_system_pango_preload.pth``, covering
``pixi run``, ``pixi shell``, IPython and IDE interpreters alike. Elsewhere
(Windows, macOS, envs without conda Pango, hosts without the system plugin)
it returns without loading anything.
"""

# Standard library imports.
import ctypes
import os
import sys

#: Load order matters: each library's own deps must already be system copies.
SYSTEM_LIBRARIES = (
    "libfreetype.so.6",
    "libfontconfig.so.1",
    "libpango-1.0.so.0",
    "libpangoft2-1.0.so.0",
    "libpangocairo-1.0.so.0",
)


def preload_system_pango():
    """Load the system Pango stack before conda's copy can be bound."""
    if sys.platform != "linux":
        return

    # Only a conda env that ships its own Pango has the clash.
    if not os.path.exists(os.path.join(sys.prefix, "lib", "libpangoft2-1.0.so.0")):
        return

    multiarch = getattr(sys.implementation, "_multiarch", "")
    system_lib_dir = os.path.join("/usr/lib", multiarch)
    gst_libav = os.path.join(system_lib_dir, "gstreamer-1.0", "libgstlibav.so")
    paths = [os.path.join(system_lib_dir, name) for name in SYSTEM_LIBRARIES]

    if not os.path.exists(gst_libav) or not all(map(os.path.exists, paths)):
        return

    try:
        for path in paths:
            ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)

    except OSError:
        # A partial preload leaves the plugin no worse off than before; never
        # let a startup hook stop the interpreter.
        pass


preload_system_pango()
