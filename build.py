import PyInstaller.__main__
import os

if __name__ == '__main__':
    import uiautomation
    uiauto_dir = os.path.dirname(uiautomation.__file__)
    uiauto_bin = os.path.join(uiauto_dir, 'bin')

    PyInstaller.__main__.run([
        'main.py',
        '--name=ScenoxisRun',
        '--windowed',
        '--icon=assets/icon.ico',
        '--add-data=ui/styles.qss;ui',
        '--add-data=README.md;.',
        '--add-data=assets;assets',
        f'--add-data={uiauto_bin};uiautomation/bin',
        '--hidden-import=agent.classifier',
        '--hidden-import=agent.graph',
        '--hidden-import=agent.memory',
        '--hidden-import=agent.tools.calculator',
        '--hidden-import=agent.tools.page_analyzer',
        '--hidden-import=agent.tools.ui_actions',
        '--hidden-import=agent.tools.web_search',
        '--hidden-import=agent.tools.yt_downloader',
        '--hidden-import=core.app_index',
        '--hidden-import=core.browser_tracker',
        '--hidden-import=core.config',
        '--hidden-import=core.converter',
        '--hidden-import=core.dwm_blur',
        '--hidden-import=core.file_search',
        '--hidden-import=core.hotkey',
        '--hidden-import=core.notes',
        '--hidden-import=core.reminders',
        '--hidden-import=core.system_controls',
        '--hidden-import=core.youtube',
        '--hidden-import=ui.settings_window',
        '--hidden-import=ui.features_window',
        '--collect-all=chromadb',
        '--collect-all=posthog',
        '--noconfirm',
        '--clean'
    ])
