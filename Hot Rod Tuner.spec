# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['run_server.py'],
    pathex=['src'],
    binaries=[],
    datas=[('static', 'static'), ('assets', 'assets')],
    hiddenimports=['hotrod_tuner', 'hotrod_tuner.app', 'hotrod_tuner.metrics', 'hotrod_tuner.policies', 'hotrod_tuner.scheduler', 'hotrod_tuner.sensors', 'hotrod_tuner.sound', 'hotrod_tuner.splash', 'hotrod_tuner.telemetry_pipe', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto', 'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan', 'uvicorn.lifespan.on', 'uvicorn.lifespan.off', 'wmi', 'psutil', 'websockets'],
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
    name='Hot Rod Tuner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\HRT_ICON.ico'],
    uac_admin=True,
)
