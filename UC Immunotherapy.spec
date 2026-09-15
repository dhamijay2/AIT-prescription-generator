# -*- mode: python ; coding: utf-8 -*-
import sys
import tkinter
from pathlib import Path

# Find Tcl/Tk data directory
tk_library = Path(tkinter.__file__).parent
tcl_root = tk_library / '../tcltk'

# Try to find tcl directory in Python installation
python_root = Path(sys.prefix)
possible_tcl_paths = [
    python_root / 'tcl',
    python_root / 'Library' / 'tcl',
]

tcl_data = None
for path in possible_tcl_paths:
    if path.exists():
        tcl_data = [(str(path), 'tcl')]
        break

# Fallback - let PyInstaller handle it
if not tcl_data:
    tcl_data = []

a = Analysis(
    ['ait gen.py'],
    pathex=[],
    binaries=[],
    datas=tcl_data,
    hiddenimports=['tkinter', 'tkcalendar', 'reportlab'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='UC Immunotherapy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['ait-generator.ico'],
)
