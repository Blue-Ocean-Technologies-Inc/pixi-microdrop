# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Preload Windows' system ICU so the PyPI PySide6 wheel imports in conda envs.

PyPI PySide6 >= 6.10 links ``Qt6Core.dll`` against the unversioned Windows ICU,
``icuuc.dll``. conda-forge ``icu`` also ships an ``icuuc.dll`` in
``Library/bin`` whose exports carry a version suffix (``ucnv_open_78``), and
conda's Python puts that directory on the DLL search path ahead of System32, so
``import PySide6.QtCore`` fails with "The specified procedure could not be
found". Every conda binary links the versioned ``icuuc78.dll`` instead, so
loading the system copy first is safe: the loader reuses it for Qt by name.

Runs at interpreter startup from ``pyside6_icu_preload.pth``, covering
``pixi run``, ``pixi shell``, IPython and IDE interpreters alike.
"""

# Standard library imports.
import ctypes
import os
import sys


def preload_system_icu():
    """Load System32's ``icuuc.dll`` before Qt can bind conda's copy."""
    if sys.platform != "win32":
        return

    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    system_icu = os.path.join(system_root, "System32", "icuuc.dll")

    try:
        ctypes.WinDLL(system_icu)
    except OSError:
        # Windows older than 1703 has no system ICU. There is nothing to
        # preload, and Qt reports its own load error if it needs one.
        pass


preload_system_icu()
