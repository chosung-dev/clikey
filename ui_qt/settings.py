# ui_qt/settings.py
"""환경 설정 창."""
from __future__ import annotations

import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import hotkeys, prefs
from ui_qt import theme as T
from ui_qt.dialogs import BaseDialog
from ui_qt.fields import ChoiceField, HotkeyField, NumberField


def _section(text: str, note: str = "") -> QWidget:
    """구역 머리글. 안내문을 주면 바로 아래에 붙여 한 덩어리로 만든다.

    본문 간격을 사이에 끼우면 머리글만 위로 떠 보여, 무엇에 대한 설명인지
    한눈에 이어지지 않는다.
    """
    box = QWidget()
    outer = QVBoxLayout(box)
    outer.setContentsMargins(0, 6, 0, 0)
    outer.setSpacing(4)

    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(7)

    label = QLabel(text)
    label.setObjectName("SectionLabel")
    lay.addWidget(label)

    rule = QFrame()
    rule.setFixedHeight(1)
    rule.setStyleSheet(f"background: {T.RULE_1};")
    lay.addWidget(rule, 1)
    outer.addWidget(row)

    if note:
        hint = QLabel(note)
        hint.setObjectName("DialogHint")
        hint.setWordWrap(True)
        outer.addWidget(hint)
    return box


def _row(label_text: str, widget: QWidget, hint: str = "") -> QWidget:
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)

    label = QLabel(label_text)
    label.setObjectName("DialogLabel")
    lay.addWidget(label)
    lay.addWidget(widget)

    if hint:
        note = QLabel(hint)
        note.setObjectName("DialogHint")
        note.setWordWrap(True)
        lay.addWidget(note)
    return box


class _Foldable(QWidget):
    """눌러서 여닫는 구역 머리.

    자주 만지지 않는 설정까지 늘 펼쳐 두면 창이 길어져 정작 자주 쓰는 값이
    아래로 밀린다. 대신 지금 켜져 있는 것은 펴서 보여준다 — 쓰고 있는 설정을
    한 번 더 눌러야 보이는 것은 숨긴 것이나 마찬가지다.
    """

    def __init__(self, text: str, body: QWidget, opened: bool = False,
                 summary=None):
        super().__init__()
        self.body = body
        self.opened = opened
        #: 접혀 있을 때 오른쪽에 붙일 한마디. 화살표 하나만 남으면 그 줄이
        #: 아무 말도 하지 않아 창이 휑해 보인다.
        self.summary = summary

        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 2)
        lay.setSpacing(7)

        self.caret = QLabel()
        self.caret.setFixedSize(12, 12)
        lay.addWidget(self.caret)

        label = QLabel(text)
        label.setObjectName("SectionLabel")
        lay.addWidget(label)

        self.rule = QFrame()
        self.rule.setFixedHeight(1)
        self.rule.setStyleSheet(f"background: {T.RULE_1};")
        lay.addWidget(self.rule, 1)

        self.state = QLabel()
        self.state.setObjectName("DialogHint")
        lay.addWidget(self.state)

        self._apply()

    def _apply(self) -> None:
        self.caret.setPixmap(T.icon_pixmap(
            "caret_down" if self.opened else "caret_right", 12, T.INK_3,
            width=1.6, ratio=self.devicePixelRatioF()))
        self.body.setVisible(self.opened)

        word = "" if self.opened or self.summary is None else self.summary()
        self.state.setText(word)
        self.state.setVisible(bool(word))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.opened = not self.opened
            self._apply()
            # 접으면 창도 따라 줄어야 한다 — 안 그러면 빈 자리가 남는다
            window = self.window()
            if window is not None:
                window.adjustSize()
        super().mousePressEvent(event)


class SettingsDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__(parent, "환경 설정", 440)
        # 칸이 많아 기본 간격으로는 창이 길어지고, 접었을 때 빈 자리가 도드라진다
        self.body.setSpacing(8)
        self.values = prefs.load()

        self.body.addWidget(_section(
            "새 매크로 기본 설정",
            "매크로를 새로 만들 때 해당 설정이 들어갑니다. "
            "설정은 매크로의 노드 설정으로 변경 가능합니다."))

        self.body.addWidget(_row(
            "실행", HotkeyField(self.values["default_start_key"],
                              lambda v: self._set("default_start_key", v))))
        self.body.addWidget(_row(
            "종료", HotkeyField(self.values["default_stop_key"],
                              lambda v: self._set("default_stop_key", v))))

        self.body.addWidget(_row(
            "노드 사이 간격",
            NumberField(self.values["step_delay"],
                        lambda v: self._set("step_delay", v),
                        decimals=2, minimum=0, maximum=10, suffix="초"),
            "노드를 하나 실행한 뒤 쉬는 시간 (초)",
        ))
        self.body.addWidget(_row(
            "마우스 이동 시간",
            NumberField(self.values["mouse_move_duration"],
                        lambda v: self._set("mouse_move_duration", v),
                        decimals=2, minimum=0, maximum=5, suffix="초"),
            "0 이면 좌표로 즉시 이동, 값을 올리면 부드럽게 이동합니다",
        ))

        # 연동은 대부분 한 번 켜두고 잊는 설정이라 접어 둔다. 이미 켜져
        # 있으면 펴서 상태가 바로 보이게 한다.
        mcp = QWidget()
        inner = QVBoxLayout(mcp)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(10)

        inner.addWidget(_row(
            "연동", ChoiceField([(True, "켬"), (False, "끔")],
                              bool(self.values["mcp_enabled"]),
                              lambda v: self._set("mcp_enabled", v)),
            "켜면 Claude Code 가 매크로 목록을 보고 실행할 수 있습니다. "
            "AI 판단 노드가 든 매크로는 이 길로만 돌릴 수 있습니다.",
        ))
        inner.addWidget(_row(
            "포트", NumberField(self.values["mcp_port"],
                              lambda v: self._set("mcp_port", int(v)),
                              decimals=0, minimum=1024, maximum=65535),
            "127.0.0.1 에만 열립니다. 포트를 바꾸면 아래 등록을 다시 해야 합니다.",
        ))

        self.status = QLabel(self._server_status())
        self.status.setObjectName("DialogHint")
        self.status.setWordWrap(True)
        inner.addWidget(self.status)

        register = QPushButton("Claude Code 에 등록")
        register.setObjectName("GhostBtn")
        register.setFixedHeight(32)
        register.setCursor(Qt.PointingHandCursor)
        register.clicked.connect(self._register)
        inner.addWidget(register)

        self.body.addWidget(_Foldable(
            "Claude MCP", mcp, opened=bool(self.values["mcp_enabled"]),
            summary=self._server_word))
        self.body.addWidget(mcp)

        self.add_buttons([
            ("취소", "ghost", self.reject),
            ("저장", "primary", self._save),
        ])
        self.center_on_parent()

    # ------------------------------------------------------------ 연동

    def _server_word(self) -> str:
        """접었을 때 옆에 붙일 한마디."""
        from ui_qt import mcp_bridge

        if mcp_bridge.running():
            return f"포트 {mcp_bridge._port} 에서 대기 중"
        return "꺼져 있음"

    def _server_status(self) -> str:
        """지금 도는 모습과 고른 값이 다르면 그 사실까지 말해준다.

        연동은 앱이 뜰 때 한 번만 붙는다. 여기서 켜고 끄는 것은 다음에
        시작할 때의 이야기이므로, 지금 상태와 다르면 반드시 알려야 한다.
        """
        from ui_qt import mcp_bridge

        state = mcp_bridge.status()
        live = mcp_bridge.running()
        want = bool(self.values.get("mcp_enabled"))
        port = int(self.values.get("mcp_port") or mcp_bridge.PORT)

        if want and not live:
            return f"지금 상태 — {state} · 저장하면 켜집니다"
        if not want and live:
            return f"지금 상태 — {state} · 저장하면 꺼집니다"
        if want and live and port != (mcp_bridge._port or port):
            return f"지금 상태 — {state} · 저장하면 포트 {port} 로 옮겨갑니다"
        return f"지금 상태 — {state}"

    def _register(self) -> None:
        """`claude mcp add` 를 대신 불러준다.

        `~/.claude.json` 을 직접 고치지 않는다. 그 파일의 생김새는 Claude Code
        가 가진 것이고 언제 바뀔지 모른다. CLI 를 부르면 형식이 바뀌어도 따라간다.
        """
        from ui_qt import dialogs, mcp_bridge

        port = int(self.values.get("mcp_port") or mcp_bridge.PORT)
        command = mcp_bridge.register_command(port)

        if shutil.which("claude") is None:
            QGuiApplication.clipboard().setText(command)
            dialogs.alert(
                self, "명령을 복사했습니다",
                "claude 명령을 찾지 못했습니다. 아래를 터미널에 붙여넣어 "
                f"등록하세요. (클립보드에 복사해 두었습니다)\n\n{command}")
            return

        try:
            done = subprocess.run(command.split(), capture_output=True,
                                  text=True, timeout=20,
                                  creationflags=getattr(subprocess,
                                                        "CREATE_NO_WINDOW", 0))
        except Exception as exc:
            dialogs.alert(self, "등록하지 못했습니다", str(exc))
            return

        if done.returncode == 0:
            dialogs.alert(self, "등록했습니다",
                          "Claude Code 에서 /mcp 로 연결을 확인할 수 있습니다.")
        else:
            message = (done.stderr or done.stdout or "").strip()
            dialogs.alert(self, "등록하지 못했습니다",
                          message[:400] or "claude 명령이 실패했습니다.")

    def _set(self, key: str, value) -> None:
        self.values[key] = value
        # 연동 값을 만지면 아래 안내가 바로 따라와야 한다
        if key.startswith("mcp_") and hasattr(self, "status"):
            self.status.setText(self._server_status())

    def _save(self) -> None:
        for key in ("default_start_key", "default_stop_key"):
            self.values[key] = hotkeys.normalize(self.values.get(key) or "")
        prefs.save(self.values)

        # 연동은 저장하는 순간 그대로 따라간다. 앱을 다시 시작하지 않아도 된다.
        from ui_qt import mcp_bridge

        mcp_bridge.apply(bool(self.values.get("mcp_enabled")),
                         int(self.values.get("mcp_port") or mcp_bridge.PORT))
        self.accept()


def open_settings(parent=None) -> bool:
    """설정 창을 연다. 저장했으면 True."""
    from PySide6.QtWidgets import QDialog

    return SettingsDialog(parent).exec() == QDialog.Accepted
