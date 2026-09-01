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

> **키보드/마우스 제어**를 위해 관리자 권한이 필요합니다. 문제가 있다면 IDE 또는 터미널을 관리자 권한으로 실행해 보세요.

------

## 실행

```
python app.py
```

------

## 빌드(실행 파일 만들기)

Windows에서 **PyInstaller**로 exe를 생성할 수 있습니다. 프로젝트에 `spec` 파일을 사용합니다.

--app-name 옵션을 주어 프로그램 이름을 임의로 설정 할 수 있습니다.

```
pyinstaller --noconfirm --clean ExecutableFile.spec -- --app-name "Clikey"
```

생성된 실행 파일은 `dist/` 폴더에 위치합니다.
