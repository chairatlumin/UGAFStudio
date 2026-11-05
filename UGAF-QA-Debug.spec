# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['fastmcp', 'mcp', 'docx', 'PySide6', 'cv2', 'mss', 'PIL', 'loguru', 'pytesseract', 'numpy', 'scripts.fmv_harness', 'scripts.live_gameplay_agent', 'scripts.session_report', 'qa_framework.mcp_server', 'qa_framework.mcp_tools', 'app.database.database']
hiddenimports += collect_submodules('qa_framework')
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('scripts')
hiddenimports += collect_submodules('tools')


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('scripts/game_profiles.json', 'scripts'), ('qa_framework/testcases/catalog.json', 'qa_framework/testcases'), ('qa_framework/testcases/highschool_blood_cases.json', 'qa_framework/testcases'), ('docs/qa-workbench-exe.md', 'docs')],
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
    name='UGAF-QA-Debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
    name='UGAF-QA-Debug',
)

