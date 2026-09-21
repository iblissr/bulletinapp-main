# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Bulletin Premium (one-file)."""
import os
from pathlib import Path

block_cipher = None

platform_binaries = []
try:
    from PyQt6.QtCore import QLibraryInfo
    try:
        plugins_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
    except AttributeError:
        plugins_path = Path(QLibraryInfo.path(QLibraryInfo.PluginsPath))
    platform_src = plugins_path / 'platforms'
    if platform_src.is_dir():
        for f in platform_src.iterdir():
            if f.suffix in ('.dll', '.so', '.dylib'):
                platform_binaries.append((str(f), 'PyQt6/Qt6/plugins/platforms'))
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=platform_binaries,
    datas=[],
    hiddenimports=[
        'PyQt6', 'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PyQt6.QtSvg', 'PyQt6.QtSvgWidgets',
        'qtawesome', 'qtawesome.animation', 'qtawesome.iconic_font',
        'openpyxl', 'openpyxl.cell', 'openpyxl.styles',
        'openpyxl.worksheet', 'openpyxl.reader', 'openpyxl.reader.excel',
        'openpyxl.writer', 'openpyxl.writer.excel',
        'reportlab', 'reportlab.lib', 'reportlab.lib.pagesizes',
        'reportlab.lib.units', 'reportlab.platypus', 'reportlab.platypus.tables',
        'reportlab.pdfbase', 'reportlab.pdfbase.ttfonts', 'reportlab.pdfgen',
        'app', 'app.db', 'app.main_window', 'app.theme', 'app.workspace',
        'app.screen_utils', 'app.sync', 'app.models',
        'app.widgets', 'app.widgets.common', 'app.widgets.dashboard',
        'app.widgets.home_dashboard', 'app.widgets.grades',
        'app.widgets.totalisation', 'app.widgets.moyennes',
        'app.widgets.compte_rendu', 'app.widgets.students',
        'app.widgets.config', 'app.widgets.class_config_panel',
        'app.widgets.sidebar', 'app.widgets.table_helpers',
        'app.widgets.backup_dialog', 'app.widgets.export_settings',
        'app.widgets.import_xlsx_wizard', 'app.widgets.import_preview',
        'app.widgets.import_helpers', 'app.widgets.sync_report',
        'app.widgets.add_student_dialog', 'app.wizards', 'app.wizards.class_wizard',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'PyQt6.Qt3DAnimation', 'PyQt6.Qt3DCore', 'PyQt6.Qt3DExtras',
        'PyQt6.Qt3DInput', 'PyQt6.Qt3DLogic', 'PyQt6.Qt3DQuick',
        'PyQt6.Qt3DQuickAnimation', 'PyQt6.Qt3DQuickExtras',
        'PyQt6.Qt3DQuickInput', 'PyQt6.Qt3DQuickRender', 'PyQt6.Qt3DRender',
        'PyQt6.QtBluetooth', 'PyQt6.QtBodymovin', 'PyQt6.QtCharts',
        'PyQt6.QtDataVisualization', 'PyQt6.QtDBus', 'PyQt6.QtDesigner',
        'PyQt6.QtHelp', 'PyQt6.QtHttpServer', 'PyQt6.QtLocation',
        'PyQt6.QtMultimedia', 'PyQt6.QtMultimediaWidgets', 'PyQt6.QtNfc',
        'PyQt6.QtPositioning', 'PyQt6.QtPrintSupport', 'PyQt6.QtQuick',
        'PyQt6.QtQuick3D', 'PyQt6.QtQuickControls2', 'PyQt6.QtQuickShapes',
        'PyQt6.QtQuickTest', 'PyQt6.QtQuickWidgets', 'PyQt6.QtRemoteObjects',
        'PyQt6.QtScxml', 'PyQt6.QtSensors', 'PyQt6.QtSerialBus',
        'PyQt6.QtSerialPort', 'PyQt6.QtShaderTools', 'PyQt6.QtSpatialAudio',
        'PyQt6.QtSpeech', 'PyQt6.QtStateMachine', 'PyQt6.QtTest',
        'PyQt6.QtTextToSpeech', 'PyQt6.QtUiTools', 'PyQt6.QtVirtualKeyboard',
        'PyQt6.QtWebChannel', 'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineQuick',
        'PyQt6.QtWebEngineWidgets', 'PyQt6.QtWebSockets', 'PyQt6.QtWebView',
        'PyQt6.QtXml',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Bulletin',
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
    icon='app.ico' if Path('app.ico').exists() else None,
)
