# ui_qt/theme.py
"""시안의 디자인 토큰. 색·크기를 여기 한 곳에서만 정의한다."""
from __future__ import annotations

import math
import os
from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QFontDatabase, QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

APP_ICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.ico")

# ---------------------------------------------------------------- 색

BG = "#FFFFFF"
PANEL = "#FAFAFB"
CANVAS = "#EFF0F3"

RULE_1 = "#EDEFF3"
RULE_2 = "#E9EAEE"
RULE_3 = "#E3E5EA"
RULE_4 = "#D3D6DD"

INK = "#1B1E23"
INK_2 = "#5A616D"
INK_3 = "#8C939F"
INK_4 = "#A9AEB9"
INK_5 = "#C8CCD4"

ACCENT = "#3A5BC7"
ACCENT_BG = "#EDF1FB"
RUN = "#1F8A70"
RUN_DEEP = "#1B6B58"
RUN_BG = "#E4F1EC"
DANGER = "#C4453D"

CHIP_NEUTRAL = "#F1F2F5"

# ---------------------------------------------------------------- 치수

RADIUS_CTRL = 6
RADIUS_CARD = 8
CTRL_H = 32
SIDEBAR_W = 272
ROW_H = 62

# 표 컬럼 폭 (이름은 남는 공간을 차지)
COL_SHORTCUT = 100
COL_NODES = 96
COL_LASTRUN = 132
COL_STATUS = 148
COL_GAP = 16
PAGE_PAD = 24

# ---------------------------------------------------------------- 글꼴


def font_stack() -> str:
    """IBM Plex Sans 가 깔려 있으면 쓰고, 없으면 Segoe UI 로."""
    families = set(QFontDatabase.families())
    for name in ("IBM Plex Sans", "Segoe UI", "Malgun Gothic"):
        if name in families:
            return name
    return "sans-serif"


def mono_stack() -> str:
    families = set(QFontDatabase.families())
    for name in ("IBM Plex Mono", "Cascadia Mono", "Consolas"):
        if name in families:
            return name
    return "monospace"


# ---------------------------------------------------------------- 아이콘

_STROKE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="none" '
    'stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)
_FILL = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="{color}">{body}</svg>'
)

PATHS = {
    "cursor": '<path d="M3.5 2.2l9.4 4.7-3.9 1-1 3.9z"/>',
    "search": '<circle cx="7.2" cy="7.2" r="4.4"/><path d="M10.5 10.5l3 3"/>',
    "plus": '<path d="M8 3.4v9.2M3.4 8h9.2"/>',
    "minus": '<path d="M3.4 8h9.2"/>',
    "folder": '<path d="M2.2 12.4V4.2a1 1 0 011-1h2.9l1.4 1.7h5.3a1 1 0 011 1v6.5a1 1 0 01-1 1H3.2a1 1 0 01-1-1z"/>',
    "archive": '<rect x="2.2" y="4.4" width="11.6" height="8.6" rx="1"/><path d="M1.4 4.4h13.2M6.6 7.6h2.8"/>',
    "all": '<rect x="2" y="2.6" width="12" height="10.8" rx="1.8"/><path d="M2 6.2h12"/>',
    "gear": (
        '<circle cx="8" cy="8" r="2.1"/><path d="M12.9 9.8a1.1 1.1 0 00.22 1.21l.04.04a1.34 1.34 0 '
        '11-1.9 1.9l-.04-.04a1.1 1.1 0 00-1.21-.22 1.1 1.1 0 00-.67 1v.11a1.34 1.34 0 11-2.68 '
        '0v-.06a1.1 1.1 0 00-.72-1 1.1 1.1 0 00-1.21.22l-.04.04a1.34 1.34 0 11-1.9-1.9l.04-.04a1.1 '
        '1.1 0 00.22-1.21 1.1 1.1 0 00-1-.67h-.11a1.34 1.34 0 110-2.68h.06a1.1 1.1 0 001-.72 1.1 '
        '1.1 0 00-.22-1.21l-.04-.04a1.34 1.34 0 111.9-1.9l.04.04a1.1 1.1 0 001.21.22h.05a1.1 1.1 0 '
        '00.67-1v-.11a1.34 1.34 0 112.68 0v.06a1.1 1.1 0 00.67 1 1.1 1.1 0 001.21-.22l.04-.04a1.34 '
        '1.34 0 111.9 1.9l-.04.04a1.1 1.1 0 00-.22 1.21v.05a1.1 1.1 0 001 .67h.11a1.34 1.34 0 110 '
        '2.68h-.06a1.1 1.1 0 00-1 .67z"/>'
    ),
    "graph": (
        '<circle cx="4.2" cy="3.4" r="1.7"/><circle cx="11.8" cy="8" r="1.7"/>'
        '<circle cx="4.2" cy="12.6" r="1.7"/><path d="M5.7 4.3l4.6 2.9M10.3 8.8l-4.6 2.9"/>'
    ),
    "check": '<path d="M3.4 8.4l3 3 6.2-6.8"/>',
    "cross": '<path d="M4.2 4.2l7.6 7.6M11.8 4.2l-7.6 7.6"/>',
    # 노드 종류
    "mouse_click": '<path d="M3.6 2.4l8.8 4.4-3.7.9-.9 3.7z"/><path d="M9 9l3.2 3.2"/>',
    "mouse_move": (
        '<path d="M8 2.2v11.6M2.2 8h11.6"/>'
        '<path d="M8 2.2L6.3 4M8 2.2L9.7 4M8 13.8L6.3 12M8 13.8L9.7 12"/>'
        '<path d="M2.2 8L4 6.3M2.2 8L4 9.7M13.8 8L12 6.3M13.8 8L12 9.7"/>'
    ),
    "mouse_down": (
        '<rect x="4" y="1.8" width="6.2" height="9.4" rx="3.1"/><path d="M7.1 4v2"/>'
        '<path d="M7.1 13v1.2M5.5 12.6l1.6 1.6 1.6-1.6"/>'
    ),
    "mouse_up": (
        '<rect x="4" y="4.8" width="6.2" height="9.4" rx="3.1"/><path d="M7.1 7v2"/>'
        '<path d="M7.1 3.4V1.8M5.5 3.4l1.6-1.6 1.6 1.6"/>'
    ),
    "key_press": (
        '<rect x="2.2" y="3.6" width="11.6" height="8.8" rx="1.6"/>'
        '<path d="M5 6.6h.01M8 6.6h.01M11 6.6h.01M5.4 9.5h5.2"/>'
    ),
    "key_down": (
        '<rect x="2.2" y="3.6" width="11.6" height="8.8" rx="1.6"/><path d="M8 6.1v2.1l1.5.9"/>'
    ),
    "key_up": (
        '<rect x="2.2" y="5.4" width="11.6" height="8.8" rx="1.6"/>'
        '<path d="M8 3.6V1.4M6.4 3l1.6-1.6L9.6 3"/>'
    ),
    "delay": '<circle cx="8" cy="8" r="5.8"/><path d="M8 4.6V8l2.2 1.3"/>',
    "rgb_match": '<path d="M8 1.8s4.3 4.4 4.3 7.1A4.3 4.3 0 013.7 8.9C3.7 6.2 8 1.8 8 1.8z"/>',
    "image_match": (
        '<rect x="2" y="3" width="12" height="10" rx="1.6"/><circle cx="5.8" cy="6.4" r="1.1"/>'
        '<path d="M2.4 11l3.3-3 2.4 2.2 2.2-2 3.3 3"/>'
    ),
    "loop": '<path d="M13.4 7.2a5.6 5.6 0 10-1.5 4.4"/><path d="M13.6 3.4v3.8h-3.8"/>',
    "start": '<circle cx="8" cy="8" r="4.6"/>',
    "stop": '<rect x="3.4" y="3.4" width="9.2" height="9.2" rx="1.4"/>',
    "crop": (
        '<path d="M4.4 1.6v10h10"/><path d="M1.6 4.4h10v10"/>'
    ),
    "arrow_right": '<path d="M3 8h9M8.6 4.6L12 8l-3.4 3.4"/>',
    # 창 조작
    "maximize": '<rect x="3.2" y="3.2" width="9.6" height="9.6" rx="1.2"/>',
    "restore": (
        '<rect x="2.6" y="5.4" width="8" height="8" rx="1.2"/>'
        '<path d="M5.4 5.4V3.8a1.2 1.2 0 011.2-1.2h6.4a1.2 1.2 0 011.2 1.2v6.4a1.2 1.2 0 01-1.2 1.2h-1.6"/>'
    ),
    "close": '<path d="M4 4l8 8M12 4l-8 8"/>',
}

FILLED = {
    "play": '<path d="M4.8 2.8l7.8 4.8a.35.35 0 010 .6l-7.8 4.8a.35.35 0 01-.53-.3V3.1a.35.35 0 01.53-.3z"/>',
    "pause": '<rect x="4" y="3.2" width="2.6" height="9.6" rx=".9"/><rect x="9.4" y="3.2" width="2.6" height="9.6" rx=".9"/>',
}


# 아이콘 크기는 흔한 화면 배율(1.25 / 1.5 / 1.75 / 2.0)에서 모두 정수 장치 픽셀로
# 떨어지는 값을 쓴다. 4의 배수면 안전하다. 어정쩡한 값(11, 13, 15)은 반 픽셀에
# 걸쳐 가는 선이 흐려 보인다.
ICON_SM = 12
ICON_MD = 16
ICON_LG = 20


def logo_pixmap(size: int, ratio: float = 1.0) -> QPixmap:
    """앱 로고(app.ico)를 주어진 크기로. 원본 비율(244x256)을 지킨다."""
    px = int(round(size * ratio))
    source = QIcon(APP_ICON).pixmap(px, px)
    if source.isNull():
        source = QPixmap(APP_ICON)
    scaled = source.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    scaled.setDevicePixelRatio(ratio)
    return scaled


@lru_cache(maxsize=512)
def icon_pixmap(name: str, size: int, color: str, width: float = 1.4,
                ratio: float = 1.0) -> QPixmap:
    """SVG 아이콘을 QPixmap 으로.

    같은 조합이 화면 곳곳에서 반복해 쓰이므로 캐시한다. 목록 한 줄마다
    SVG 를 새로 렌더하면 행 300개에서 그것만으로 수백 ms 가 든다.
    QPixmap 은 암묵적 공유라 여러 위젯이 같은 객체를 써도 안전하다.
    """
    return _render_icon(name, size, color, width, ratio)


def _render_icon(name: str, size: int, color: str, width: float,
                 ratio: float) -> QPixmap:
    """SVG 아이콘을 QPixmap 으로. 고DPI 를 위해 ratio 를 넘긴다."""
    if name in FILLED:
        svg = _FILL.format(color=color, body=FILLED[name])
    else:
        svg = _STROKE.format(color=color, w=width, body=PATHS[name])

    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))

    # 픽스맵의 DPR 은 반드시 화면 배율과 같아야 한다. 다르게 넣으면 Qt 가 그릴 때
    # 한 번 더 리샘플링하면서 가는 선의 한쪽 변이 뭉개진다.
    # 크기는 size × ratio 가 정수로 떨어지는 값을 쓰는 게 가장 선명하다 — ICON 참고.
    device = max(1, round(size * ratio))
    pm = QPixmap(device, device)
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)

    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing, True)
    # 대상 사각형을 논리 좌표로 명시해야 한다. 생략하면 고DPI(ratio>1)에서
    # 장치 픽셀 기준으로 그려져 아이콘이 ratio 배로 커지며 잘린다.
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


# ---------------------------------------------------------------- 스타일시트


def stylesheet() -> str:
    sans = font_stack()
    mono = mono_stack()
    return f"""
    * {{
        font-family: "{sans}";
        color: {INK};
    }}
    QWidget#Root  {{ background: {BG}; }}
    QWidget#Sidebar {{ background: {PANEL}; border-right: 1px solid {RULE_2}; }}

    QLabel#Brand    {{ font-size: 14px; font-weight: 600; }}
    QLabel#PageTitle{{ font-size: 21px; font-weight: 600; }}
    QLabel#PageMeta {{ font-size: 12px; color: {INK_3}; }}
    QLabel#PageError{{ font-size: 12px; color: {DANGER}; }}
    QLineEdit#TitleEdit {{
        font-size: 20px; font-weight: 600;
        background: {BG}; border: 1px solid {ACCENT}; border-radius: {RADIUS_CTRL}px;
        padding: 0 8px;
        selection-background-color: {ACCENT_BG}; selection-color: {ACCENT};
    }}
    QLineEdit#TitleEdit[invalid="true"] {{ border-color: {DANGER}; }}
    QLabel#SectionLabel {{ font-size: 10px; font-weight: 600; color: {INK_3}; }}
    QLabel#ColHead  {{ font-size: 11px; color: {INK_3}; }}
    QLabel#StatusBar{{ font-size: 11px; color: {INK_3}; }}

    QLabel#RowName  {{ font-size: 13px; font-weight: 500; }}
    QLabel#RowNameMuted {{ font-size: 13px; font-weight: 500; color: {INK_2}; }}
    QLabel#RowFolder{{ font-size: 11px; color: {INK_4}; }}
    QLabel#Cell     {{ font-size: 12px; color: {INK_2}; }}
    QLabel#CellMuted{{ font-size: 12px; color: {INK_3}; }}
    QLabel#CellEmpty{{ font-size: 12px; color: {INK_5}; }}

    QLabel#Kbd {{
        font-family: "{mono}"; font-size: 11px;
        border: 1px solid {RULE_3}; border-radius: 5px;
        background: {BG}; padding: 0 8px;
    }}
    QLabel#KbdMuted {{
        font-family: "{mono}"; font-size: 11px; color: {INK_4};
        border: 1px solid {RULE_1}; border-radius: 5px;
        background: {BG}; padding: 0 8px;
    }}
    QLabel#HintKey {{ font-family: "{mono}"; font-size: 11px; color: {INK_2}; }}
    QLabel#HintText {{ font-size: 11px; color: {INK_3}; }}
    QLabel#HintTitle {{ font-size: 12px; font-weight: 500; }}

    QFrame#NavItem, QFrame#NavItemOn {{ border-radius: 7px; }}
    QFrame#NavItemOn {{ background: {ACCENT_BG}; }}
    QFrame#NavItem:hover {{ background: {RULE_1}; }}
    QLabel#NavText   {{ font-size: 13px; }}
    QLabel#NavTextOn {{ font-size: 13px; font-weight: 500; color: {ACCENT}; }}
    QLabel#NavCount  {{ font-family: "{mono}"; font-size: 11px; color: {INK_4}; }}
    QLabel#NavCountOn{{ font-family: "{mono}"; font-size: 11px; color: {ACCENT}; }}

    QFrame#HintCard {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CARD}px;
    }}

    QLineEdit#Search {{
        border: 1px solid {RULE_3}; border-radius: 7px; background: {BG};
        font-size: 12px; padding-left: 30px;
    }}
    QLineEdit#Search:focus {{ border-color: {ACCENT}; }}

    QPushButton#RunBtn {{
        background: {RUN}; border: 1px solid {RUN}; border-radius: {RADIUS_CTRL}px;
        color: #FFFFFF; font-size: 12px; font-weight: 500; padding: 0 12px;
    }}
    QPushButton#RunBtn:hover {{ background: #1B7A63; }}
    QPushButton#RunBtn:disabled {{
        background: {CHIP_NEUTRAL}; border-color: {RULE_3}; color: {INK_4};
    }}
    /* 중지는 실행 중에만 살아난다 — 그때만 붉게 보이도록 */
    QPushButton#StopBtn {{
        background: {BG}; border: 1px solid #E8C4C1; border-radius: {RADIUS_CTRL}px;
        color: {DANGER}; font-size: 12px; font-weight: 500; padding: 0 12px;
    }}
    QPushButton#StopBtn:hover {{
        background: {DANGER}; border-color: {DANGER}; color: #FFFFFF;
    }}
    QPushButton#StopBtn:pressed {{ background: #A8382F; border-color: #A8382F; }}
    QPushButton#StopBtn:disabled {{
        background: {BG}; color: {INK_4}; border-color: {RULE_1}; font-weight: 400;
    }}

    QPushButton#NewMacro {{
        background: {INK}; border: 1px solid {INK}; border-radius: 7px;
    }}
    QPushButton#NewMacro:hover {{ background: #2C3038; }}
    /* 창 조작 버튼 — Windows 관례대로 모서리까지 꽉 채우고 닫기만 붉게 */
    /* 대화상자 */
    QFrame#DialogCard {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: 10px;
    }}
    QLabel#DialogTitle {{ font-size: 14px; font-weight: 600; }}
    QLabel#DialogBody  {{ font-size: 12.5px; color: {INK_2}; line-height: 150%; }}
    QLabel#DialogLabel {{ font-size: 11px; font-weight: 500; color: {INK_2}; }}
    QLabel#DialogHint  {{ font-size: 10.5px; color: {INK_4}; }}
    QLabel#DialogError {{ font-size: 10.5px; color: {DANGER}; }}

    QPushButton#DlgPrimary {{
        background: {ACCENT}; border: 1px solid {ACCENT}; border-radius: {RADIUS_CTRL}px;
        color: #FFFFFF; font-size: 12.5px; font-weight: 500; padding: 0 14px;
    }}
    QPushButton#DlgPrimary:hover {{ background: #2C48A8; }}
    QPushButton#DlgDanger {{
        background: {DANGER}; border: 1px solid {DANGER}; border-radius: {RADIUS_CTRL}px;
        color: #FFFFFF; font-size: 12.5px; font-weight: 500; padding: 0 14px;
    }}
    QPushButton#DlgDanger:hover {{ background: #A8382F; }}
    QPushButton#DlgGhost {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CTRL}px;
        font-size: 12.5px; padding: 0 14px;
    }}
    QPushButton#DlgGhost:hover {{ border-color: {RULE_4}; background: {PANEL}; }}

    QPushButton#TinyBtn {{ border: none; border-radius: 4px; background: transparent; }}
    QPushButton#TinyBtn:hover {{ background: {RULE_2}; }}

    QMenu {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CARD}px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 22px 6px 12px; border-radius: 5px; font-size: 12.5px;
    }}
    QMenu::item:selected {{ background: {ACCENT_BG}; color: {ACCENT}; }}
    QMenu::separator {{ height: 1px; background: {RULE_1}; margin: 4px 6px; }}

    QPushButton#WinBtn, QPushButton#WinBtnClose {{
        border: none; background: transparent;
    }}
    QPushButton#WinBtn:hover {{ background: {RULE_1}; }}
    QPushButton#WinBtn:pressed {{ background: {RULE_3}; }}
    QPushButton#WinBtnClose:hover {{ background: {DANGER}; }}
    QPushButton#WinBtnClose:pressed {{ background: #A8382F; }}

    /* 편집기 좌우 패널 */
    QWidget#Panel {{ background: {PANEL}; }}
    QFrame#SearchBox {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CTRL}px;
    }}
    QFrame#PaletteItem {{
        background: {BG}; border: 1px solid {RULE_1}; border-radius: {RADIUS_CTRL}px;
    }}
    QFrame#PaletteItem:hover {{ border-color: {RULE_4}; }}
    QFrame#ValueBox {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CTRL}px;
    }}
    QFrame#ListCard {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CARD}px;
    }}

    /* 속성 입력 */
    QLineEdit#Field {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CTRL}px;
        font-size: 12px; padding: 0 9px;
    }}
    QLineEdit#Field:focus {{ border-color: {ACCENT}; }}
    /* 잘못된 입력은 포커스 중에도 붉게 — :focus 규칙보다 뒤에 와야 이긴다 */
    QLineEdit#Field[invalid="true"],
    QLineEdit#Field[invalid="true"]:focus {{ border-color: {DANGER}; }}
    QLineEdit#BareField {{
        background: transparent; border: none; font-size: 12px; padding: 0;
        font-family: "{mono}";
    }}
    QFrame#Segmented {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CTRL}px;
    }}
    QPushButton#Segment {{
        border: none; border-radius: 4px; background: transparent;
        font-size: 12px; color: {INK_2};
    }}
    QPushButton#Segment:hover {{ background: {RULE_1}; }}
    QPushButton#Segment:checked {{
        background: {ACCENT_BG}; color: {ACCENT}; font-weight: 500;
    }}
    QPushButton#GhostBtn {{
        background: {BG}; border: 1px solid {RULE_3}; border-radius: {RADIUS_CTRL}px;
        font-size: 12px; padding: 0 10px;
    }}
    QPushButton#GhostBtn:hover {{ border-color: {RULE_4}; }}

    QFrame#Row      {{ background: {BG}; border-bottom: 1px solid {RULE_1}; }}
    QFrame#Row:hover{{ background: {PANEL}; }}
    QFrame#RowOn    {{ background: #F7F9FE; border-bottom: 1px solid {RULE_1}; }}
    QFrame#HeadRow  {{ border-top: 1px solid {RULE_2}; border-bottom: 1px solid {RULE_1}; }}

    QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {RULE_4}; border-radius: 5px; min-height: 30px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    """
