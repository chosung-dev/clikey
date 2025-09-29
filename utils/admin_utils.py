import ctypes
import sys


def is_admin():
    """
    Windows에서 현재 프로세스가 관리자 권한으로 실행 중인지 확인
    """
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def run_as_admin():
    """
    현재 프로그램을 관리자 권한으로 재시작
    """
    if is_admin():
        return True  # 이미 관리자 권한으로 실행 중

    try:
        # 관리자 권한으로 현재 프로그램 재시작
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            " ".join(sys.argv),
            None,
            1  # SW_SHOWNORMAL
        )
        # result > 32이면 성공
        return result > 32
    except Exception as e:
        print(f"관리자 권한 요청 실패: {e}")
        return False


def request_admin_if_needed():
    """
    Windows에서 관리자 권한이 필요한 경우 권한을 요청하고 프로그램을 재시작
    """
    if not is_admin():
        print("관리자 권한이 필요합니다. UAC 승인 후 프로그램이 재시작됩니다.")
        if run_as_admin():
            sys.exit(0)  # 관리자 권한으로 재시작 성공 시 현재 프로세스 종료
        else:
            print("관리자 권한 요청이 거부되었습니다.")
            return False

    return True