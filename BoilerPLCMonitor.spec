# -*- mode: python ; coding: utf-8 -*-
# SETEX 797TCE Monitor — Modbus TCP via pymodbus (CoDeSys V2)
from PyInstaller.utils.hooks import collect_all

datas = [
    ('plc_client.py', '.'),
    ('ui_main.py',    '.'),
    ('config.json',   '.'),   # machine config deployed beside exe
]
binaries = []
hiddenimports = [
    'pymodbus',
    'pymodbus.client',
    'pymodbus.client.tcp',
    'pymodbus.framer',
    'pymodbus.framer.socket_framer',
    'pyqtgraph',
    'numpy',
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
]
for pkg in ('pyqtgraph', 'pymodbus'):
    tmp = collect_all(pkg)
    datas     += tmp[0]
    binaries  += tmp[1]
    hiddenimports += tmp[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PyQt6', 'snap7', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SETEX_Monitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SETEX_Monitor',
)
