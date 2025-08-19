# MacroApp.spec
# PyInstaller>=6 기준
# pyinstaller ExecutableFile.spec
from PyInstaller.utils.hooks import collect_submodules

hidden = [
    "keyboard",
    "pyautogui",
    "PIL.ImageGrab",
    "autoit",
]
# 일부 패키지의 지연 import 대비
hidden += collect_submodules("pyautogui")

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        # ('assets/app.ico', 'assets'),  # 아이콘/리소스가 있으면 이런 식으로 추가
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
    name='Steam',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # 콘솔 창 숨김
    icon=None,              # 아이콘 있으면 'assets/app.ico'
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='NamaansMacro'
)
