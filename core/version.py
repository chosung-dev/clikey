"""앱 버전 관리 및 업데이트 체크"""
import urllib.request
import re

__version__ = "v1.1.5"

GITHUB_OWNER = "chosung-dev"
GITHUB_REPO = "clikey"


def get_latest_version() -> str | None:
    """GitHub main 브랜치의 version.py에서 __version__ 값을 조회. 실패 시 None 반환"""
    try:
        url = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/core/version.py"
        req = urllib.request.Request(url, headers={"User-Agent": "Clikey"})

        with urllib.request.urlopen(req, timeout=5) as response:
            content = response.read().decode("utf-8")
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
    except Exception:
        pass
    return None


def get_release_url() -> str:
    """GitHub 릴리즈 페이지 URL 반환"""
    return f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases"


def parse_version(version: str) -> tuple[int, ...]:
    """버전 문자열을 비교 가능한 튜플로 변환. 예: 'v1.0.1' -> (1, 0, 1)"""
    version = version.lstrip("v")
    parts = []
    for part in version.split("."):
        try:
            parts.append(int(part))
        except ValueError:
            parts.append(0)
    return tuple(parts)


def is_update_available(current: str, latest: str) -> bool:
    """최신 버전이 현재 버전보다 높은지 확인"""
    current_tuple = parse_version(current)
    latest_tuple = parse_version(latest)

    # 길이 맞추기 (짧은 쪽에 0 채움)
    max_len = max(len(current_tuple), len(latest_tuple))
    current_tuple = current_tuple + (0,) * (max_len - len(current_tuple))
    latest_tuple = latest_tuple + (0,) * (max_len - len(latest_tuple))

    return latest_tuple > current_tuple
