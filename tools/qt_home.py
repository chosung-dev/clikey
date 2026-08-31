"""홈 화면(PySide6) 미리보기.

    .venv\\Scripts\\python.exe tools/qt_home.py
    .venv\\Scripts\\python.exe tools/qt_home.py --shot out.png
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui_qt.home import HomeWindow  # noqa: E402


def main():
    shot = None
    if "--shot" in sys.argv:
        shot = sys.argv[sys.argv.index("--shot") + 1]

    app = QApplication(sys.argv)
    window = HomeWindow(ratio=app.devicePixelRatio())
    window.show()

    if shot:
        def capture():
            pm = window.grab()
            # 고DPI 화면에서는 장치 픽셀로 잡히므로 논리 크기로 줄여 저장
            dpr = pm.devicePixelRatio()
            if dpr > 1.0:
                pm = pm.scaled(
                    int(pm.width() / dpr), int(pm.height() / dpr),
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
                pm.setDevicePixelRatio(1.0)
            pm.save(shot)
            print(f"스크린샷 저장: {shot} ({pm.width()}x{pm.height()})")
            app.quit()
        QTimer.singleShot(900, capture)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
