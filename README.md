# 나만의 매크로 프로그램 Clikey

------

## 시스템 요구사항

<img src="https://img.shields.io/badge/python-3.12%2B-blue"/>
<img src="https://img.shields.io/badge/platform-Windows-brightgreen"/>

- Python 패키지: 프로젝트 루트의 `requirements.txt` 참고

------

## 설치

```
# (1) 가상환경 권장
python -m venv .venv
.venv\Scripts\activate

# (2) 의존성 설치
pip install -r requirements.txt
```

> **키보드/마우스 제어**를 위해 관리자 권한이 필요한 경우가 있습니다. 문제가 있다면 IDE 또는 터미널을 관리자 권한으로 실행해 보세요.

------

## 실행

```
python app.py
```

앱이 실행되면:

- 좌측: **매크로 리스트**
- 우측/상단: 단계 추가 버튼(마우스/키보드/지연/이미지 조건 등)
- 메뉴: **파일 → 저장/새로 저장/불러오기/종료**, 기타 설정

------

## 데이터/파일 포맷

매크로 파일은 JSON으로 저장됩니다. (예시)

```
{
  "items": [
    "마우스:이동 100,200",
    "시간:1.5",
    "조건: 픽셀(500,400) == (255,255,255)",
    "  키보드:입력 hello",
    "조건끝"
  ],
  "settings": {
    "repeat": 1,
    "start_delay": 0
  },
  "hotkeys": {
    "start": "f8",
    "stop": "f9"
  }
}
```

> 실제 항목 문자열(예: `마우스:이동`, `키보드:입력`, `시간:초`)의 세부 포맷은 버전에 따라 달라질 수 있으며, UI를 통해 추가하면 자동으로 올바른 형식으로 들어갑니다.

------

## 빌드(실행 파일 만들기)

Windows에서 **PyInstaller**로 exe를 생성할 수 있습니다. 프로젝트에 `spec` 파일을 사용합니다.

--app-name 옵션을 주어 프로그램 이름을 임의로 설정 할 수 있습니다.

```
pyinstaller --noconfirm --clean ExecutableFile.spec -- --app-name "AppName"
```

생성된 실행 파일은 `dist/` 폴더에 위치합니다.
