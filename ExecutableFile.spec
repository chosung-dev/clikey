from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_dynamic_libs
import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--app-name", default="Clikey")
opts = parser.parse_args()

hidden = [
    "keyboard",
    "pyautogui",
    "PIL.ImageGrab",
    "autoit",
]
# 일부 패키지의 지연 import 대비
hidden += collect_submodules("pyautogui")

block_cipher = None
autoit_bins = collect_dynamic_libs('autoit')

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=autoit_bins,
    datas=[
        ('app.ico', '.'),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=opts.app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 콘솔 창 숨김
    icon='app.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='Clikey'
)
