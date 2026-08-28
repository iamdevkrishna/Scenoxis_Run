# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('ui/styles.qss', 'ui'), ('README.md', '.'), ('assets', 'assets'), ('E:\\Projects\\Scenoxis Run\\.venv\\Lib\\site-packages\\uiautomation\\bin', 'uiautomation/bin')]
binaries = []
hiddenimports = ['agent.classifier', 'agent.graph', 'agent.memory', 'agent.tools.calculator', 'agent.tools.page_analyzer', 'agent.tools.ui_actions', 'agent.tools.web_search', 'agent.tools.yt_downloader', 'core.app_index', 'core.browser_tracker', 'core.config', 'core.converter', 'core.dwm_blur', 'core.file_search', 'core.hotkey', 'core.notes', 'core.reminders', 'core.system_controls', 'core.youtube', 'ui.settings_window', 'ui.features_window']
tmp_ret = collect_all('chromadb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('posthog')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    icon=['assets\\icon.ico'],
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
