# ExecutableFile.spec
#
#   pyinstaller --noconfirm --clean ExecutableFile.spec -- --app-name "Clikey"
#
# 결과물은 dist/Clikey/ 에 통째로 나온다. 그 폴더를 압축해 옮기면 설치 없이
# 바로 실행된다.
import argparse

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

parser = argparse.ArgumentParser()
parser.add_argument("--app-name", default="Clikey")
opts = parser.parse_args()

# 코드에서 이름으로 직접 부르지 않아 PyInstaller 가 놓치는 것들.
hidden = [
    "keyboard",
    "autoit",
    # NodeGraphQt 는 Qt.py 를 거쳐 바인딩을 고른다. 실제로 쓰는 것은 PySide6
    # 하나뿐인데, Qt.py 가 실행 중에 이름으로 찾으므로 여기 적어둬야 한다.
    "Qt",
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtSvg",          # 아이콘을 SVG 로 그린다
    "PySide6.QtOpenGLWidgets",  # NodeGraphQt 캔버스
]

# 안 쓰는데 딸려 들어오면 결과물만 무거워지는 것들.
excludes = [
    "tkinter",
    "tkinterdnd2",
    "pyautogui",
    "PIL",
    "mss",
    "matplotlib",
    "pytest",
    # Qt.py 가 다른 바인딩도 찾아보므로 없는 것을 분명히 해둔다
    "PySide2",
    "PyQt5",
    "PyQt6",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.Qt3DCore",
    "PySide6.QtDataVisualization",
]

# autoit 은 동봉된 DLL 로 움직인다.
autoit_bins = collect_dynamic_libs("autoit")
# NodeGraphQt 는 노드 배경 png 를 파일로 읽는다.
nodegraph_datas = collect_data_files("NodeGraphQt")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=autoit_bins,
    datas=[
        ("app.ico", "."),
    ] + nodegraph_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
# opencv 는 동영상 입출력용 ffmpeg DLL(28MB) 을 함께 들고 온다. 우리는 화면
# 캡처 이미지에서 템플릿을 찾는 데만 쓰므로 동영상 쪽은 필요 없다.
a.binaries = [b for b in a.binaries
              if "opencv_videoio_ffmpeg" not in b[0].lower()]

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=opts.app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # Qt DLL 을 upx 로 줄이면 실행이 깨지는 사례가 잦아 쓰지 않는다.
    upx=False,
    console=False,          # 콘솔 창 숨김
    icon="app.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="Clikey",
)
