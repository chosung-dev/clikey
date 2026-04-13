import tkinter as tk


def fit_window_height(win: tk.Toplevel, base_width: int, base_height: int) -> None:
    """위젯 배치가 끝난 뒤 내용이 창보다 커서 잘릴 경우 높이만 늘려 맞춤.

    가로는 설정값(base_width)을 그대로 유지하고, 세로만 reqheight 가
    base_height 보다 크면 그만큼 확장한다. 고DPI 환경(125%/150% 등)에서
    폰트/위젯이 커져 버튼이 잘리는 문제를 보정한다.
    """
    try:
        win.update_idletasks()
        req_h = win.winfo_reqheight()
        if req_h > base_height:
            geo = win.geometry()
            # 기존 geometry 문자열에서 위치(+x+y) 부분을 보존
            plus_idx = geo.find("+")
            pos = geo[plus_idx:] if plus_idx != -1 else ""
            win.geometry(f"{base_width}x{req_h}{pos}")
    except Exception:
        pass
