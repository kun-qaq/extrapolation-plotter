# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Extrapolation Plotter (WinUI3 / PyWinRT).

Run with the project venv:
    .venv\\Scripts\\python.exe -m PyInstaller --noconfirm --clean build_exe.spec

Set EXTRAP_ONEFILE=1 for a single-file build (slower cold start).
PyWinRT ships its own PyInstaller hook (winrt.__pyinstaller) that collects
all _table.pywinrt projection files and the Windows App SDK bootstrap DLL,
so do NOT manually collect_all('winrt') here -- that would duplicate files.
"""
import os
from pathlib import Path

ROOT = Path(SPECPATH)
NAME = "ExtrapolationPlotter"
ONEFILE = os.environ.get("EXTRAP_ONEFILE", "0") == "1"

datas = [
    (str(ROOT / "ui.xaml"), "."),
    (str(ROOT / "sakura.ico"), "."),          # AppWindow.set_icon at runtime
    (str(ROOT / "samples" / "calorimetry_demo.csv"), "samples"),
]

# matplotlib loads its backends by name at runtime; Agg/SVG/PDF must be present
# or preview / vector export fails only in the frozen build.
hiddenimports = [
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_svg",
    "matplotlib.backends.backend_pdf",
    "winrt.microsoft.ui.xaml.xamltypeinfo",
    "winrt.windows.foundation",
    "winrt.windows.graphics",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The venv uses --system-site-packages, so PyInstaller would otherwise
    # drag in torch (291 MB torch_cpu.dll), scipy, pandas, sympy etc. None
    # of them are used by this project (only numpy + matplotlib + winrt).
    excludes=[
        "torch", "torchvision", "torchaudio", "scipy", "pandas", "sympy",
        "sklearn", "skimage", "cv2", "networkx", "numba", "statsmodels",
        "IPython", "jupyter", "notebook", "pytest", "matplotlib.tests",
        "numpy.testing", "PIL.tests",
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe_kwargs = dict(
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,               # UPX breaks WinRT projection DLLs
    console=False,           # GUI app, no console window
    icon=str(ROOT / "sakura.ico"),   # sakura icon on the exe itself
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

if ONEFILE:
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], **exe_kwargs)
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_kwargs)
    coll = COLLECT(
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=False, upx_exclude=[], name=NAME,
    )
