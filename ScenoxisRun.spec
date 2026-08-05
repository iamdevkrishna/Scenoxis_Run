# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('ui/styles.qss', 'ui'), ('README.md', '.')],
    hiddenimports=['agent.classifier', 'agent.graph', 'agent.memory', 'agent.tools.calculator', 'agent.tools.page_analyzer', 'agent.tools.ui_actions', 'agent.tools.web_search', 'agent.tools.yt_downloader', 'core.app_index', 'core.browser_tracker', 'core.config', 'core.converter', 'core.dwm_blur', 'core.file_search', 'core.hotkey', 'core.notes', 'core.reminders', 'core.system_controls', 'core.youtube'],
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
    [],
    exclude_binaries=True,
    name='ScenoxisRun',
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
    name='ScenoxisRun',
)
