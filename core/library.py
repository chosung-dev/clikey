# core/library.py
"""매크로 라이브러리 — 디스크 폴더를 그대로 목록으로 쓴다.

색인 파일을 두지 않는다. 탐색기에서 파일을 옮기거나 폴더를 만들면 그대로
반영되고, 색인과 실제가 어긋날 일이 없다.

    <루트>/                     루트에 바로 둔 매크로
    <루트>/업무 자동화/*.clikey   하위 폴더 하나가 목록의 폴더 하나
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core.graph.model import AI_TYPES

MACRO_SUFFIX = ".clikey"
ROOT_FOLDER_NAME = "Clikey"
UNFILED = "분류 없음"

#: 클립보드에서 붙여넣은 템플릿 이미지를 담아두는 곳.
#: 점으로 시작해 매크로 폴더 목록에는 나타나지 않는다.
IMAGES_DIR = ".images"


# ---------------------------------------------------------------- 위치


ENV_ROOT = "CLIKEY_LIBRARY"


def library_root() -> Path:
    """매크로를 담아둘 폴더. 없으면 만든다.

    환경변수 CLIKEY_LIBRARY 로 위치를 바꿀 수 있다. 폴더를 지우고 만드는
    테스트가 실제 라이브러리를 건드리지 않게 하려는 것이 주 용도다.
    """
    override = os.environ.get(ENV_ROOT)
    if override:
        root = Path(override)
    else:
        documents = Path(os.path.expanduser("~")) / "Documents"
        if not documents.is_dir():
            documents = Path(os.path.expanduser("~"))
        root = documents / ROOT_FOLDER_NAME

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return root


# ---------------------------------------------------------------- 항목


@dataclass
class MacroFile:
    path: Path
    name: str
    folder: str
    nodes: int
    modified: float
    broken: bool = False
    start_key: str = ""      # 시작 노드에 적힌 실행 단축키
    stop_key: str = ""       # 종료 노드에 적힌 종료 단축키
    enabled: bool = True     # 꺼두면 단축키를 걸지 않는다
    mcp_only: bool = False   # 판단 노드가 있어 Claude 를 거쳐야만 도는 매크로


def humanize(timestamp: float) -> str:
    """시각을 사람이 읽는 표현으로. 0 이면 "—"."""
    if not timestamp:
        return "—"

    when = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    delta = now - when

    if delta.total_seconds() < 60:
        return "방금"
    if delta.days == 0 and when.date() == now.date():
        return f"오늘 {when:%H:%M}"
    if delta.days <= 1:
        return f"어제 {when:%H:%M}"
    if delta.days < 7:
        return f"{delta.days}일 전"
    if delta.days < 30:
        return f"{delta.days // 7}주 전"
    if delta.days < 365:
        return f"{delta.days // 30}개월 전"
    return f"{when:%Y-%m-%d}"


# 노드 수는 파일을 열어야 알 수 있어 목록을 그릴 때마다 전부 파싱하면 느리다.
# (경로 -> (수정시각, 크기, 노드 수)) 로 캐시해 바뀐 파일만 다시 읽는다.
_NODE_COUNT_CACHE: dict = {}
_CACHE_LIMIT = 2000


def read_summary(path: Path, stat=None):
    """(노드 수, 실행 단축키, 종료 단축키, 사용 여부, 판단 노드 있음).

    그래프 파일이 아니면 (None, "", "", True, False).
    """
    try:
        info = stat or path.stat()
        stamp = (info.st_mtime_ns, info.st_size)
    except OSError:
        return None, "", "", True, False

    key = str(path)
    cached = _NODE_COUNT_CACHE.get(key)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    summary = (None, "", "", True, False)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass
    else:
        nodes = data.get("nodes")
        if isinstance(nodes, dict):
            start_key = stop_key = ""
            asks = False
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                kind = node.get("type")
                if kind == "start" and not start_key:
                    start_key = str(node.get("hotkey") or "")
                elif kind == "stop" and not stop_key:
                    stop_key = str(node.get("hotkey") or "")
                elif kind in AI_TYPES:
                    asks = True
            enabled = data.get("enabled", True) is not False
            summary = (len(nodes), start_key, stop_key, enabled, asks)

    if len(_NODE_COUNT_CACHE) > _CACHE_LIMIT:
        _NODE_COUNT_CACHE.clear()
    _NODE_COUNT_CACHE[key] = (stamp, summary)
    return summary


def scan(root: Optional[Path] = None) -> List[MacroFile]:
    """루트와 그 하위 폴더에서 매크로 파일을 모은다 (한 단계 깊이)."""
    root = root or library_root()
    if not root.is_dir():
        return []

    entries: List[MacroFile] = []

    def collect(directory: Path, folder_name: str) -> None:
        try:
            children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            return
        for child in children:
            if child.suffix.lower() != MACRO_SUFFIX:
                continue
            try:
                info = child.stat()
            except OSError:
                continue
            if not child.is_file():
                continue

            # stat 을 재사용해 파일 정보를 한 번만 조회한다
            nodes, start_key, stop_key, enabled, mcp_only = read_summary(child, info)
            entries.append(MacroFile(
                path=child,
                name=child.stem,
                folder=folder_name,
                nodes=nodes if nodes is not None else 0,
                modified=info.st_mtime,
                broken=nodes is None,
                start_key=start_key,
                stop_key=stop_key,
                enabled=enabled,
                mcp_only=mcp_only,
            ))

    collect(root, UNFILED)

    try:
        subdirs = sorted((p for p in root.iterdir()
                          if p.is_dir() and not p.name.startswith(".")),
                         key=lambda p: p.name.lower())
    except OSError:
        subdirs = []
    for sub in subdirs:
        collect(sub, sub.name)

    entries.sort(key=lambda m: m.modified, reverse=True)
    return entries


def folder_names(root: Optional[Path] = None) -> List[str]:
    """하위 폴더 이름. 목록에 항목이 없어도 폴더는 보여준다."""
    root = root or library_root()
    try:
        return sorted((p.name for p in root.iterdir()
                       if p.is_dir() and not p.name.startswith(".")), key=str.lower)
    except OSError:
        return []


def images_root(root: Optional[Path] = None) -> Path:
    """붙여넣은 템플릿 이미지를 담아둘 폴더. 없으면 만든다."""
    path = (root or library_root()) / IMAGES_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_image(pixmap, stem: str = "붙여넣은 이미지",
               root: Optional[Path] = None) -> Path:
    """이미지를 라이브러리 안에 저장하고 그 경로를 돌려준다.

    클립보드 이미지는 파일이 아니라서 어딘가에 놓아두어야 참조할 수 있다.
    같은 이름이 있으면 뒤에 번호를 붙인다.
    """
    folder = images_root(root)
    path = folder / f"{stem}.png"
    n = 2
    while path.exists():
        path = folder / f"{stem} {n}.png"
        n += 1
    if not pixmap.save(str(path), "PNG"):
        raise OSError("이미지를 저장하지 못했습니다.")
    return path


# ---------------------------------------------------------------- 폴더 관리

INVALID_CHARS = set('\\/:*?"<>|')
RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def check_folder_name(name: str, root: Optional[Path] = None,
                      allow: Optional[str] = None) -> Optional[str]:
    """폴더 이름이 쓸 수 있는지 검사. 문제가 있으면 사람이 읽을 설명을 반환."""
    root = root or library_root()
    name = (name or "").strip()

    if not name:
        return "이름을 입력해주세요."
    if len(name) > 80:
        return "이름이 너무 깁니다."
    bad = sorted(set(name) & INVALID_CHARS)
    if bad:
        return f"다음 문자는 쓸 수 없습니다: {' '.join(bad)}"
    if name.rstrip(". ") != name:
        return "이름 끝에 마침표나 공백을 둘 수 없습니다."
    if name.upper() in RESERVED:
        return f"'{name}' 은(는) Windows 가 예약한 이름입니다."
    if allow is not None and name.lower() == allow.lower():
        return None
    if (root / name).exists():
        return f"'{name}' 폴더가 이미 있습니다."
    return None


def count_in_folder(name: str, root: Optional[Path] = None) -> int:
    root = root or library_root()
    target = root / name
    try:
        return sum(1 for p in target.iterdir()
                   if p.is_file() and p.suffix.lower() == MACRO_SUFFIX)
    except OSError:
        return 0


def create_folder(name: str, root: Optional[Path] = None) -> Path:
    root = root or library_root()
    target = root / name.strip()
    target.mkdir(parents=True, exist_ok=False)
    return target


def rename_folder(old: str, new: str, root: Optional[Path] = None) -> Path:
    root = root or library_root()
    target = root / new.strip()
    (root / old).rename(target)
    return target


def duplicate_folder(name: str, root: Optional[Path] = None) -> Path:
    """폴더를 내용째 복제한다. '이름 (사본)', 겹치면 '(사본 2)' 로."""
    import shutil

    root = root or library_root()
    source = root / name

    candidate = root / f"{name} (사본)"
    index = 2
    while candidate.exists():
        candidate = root / f"{name} (사본 {index})"
        index += 1

    shutil.copytree(source, candidate)
    return candidate


def check_macro_name(name: str, folder: str, root: Optional[Path] = None,
                     allow: Optional[str] = None) -> Optional[str]:
    """매크로 이름(파일 이름)이 쓸 수 있는지 검사."""
    root = root or library_root()
    name = (name or "").strip()

    if not name:
        return "이름을 입력해주세요."
    if len(name) > 80:
        return "이름이 너무 깁니다."
    bad = sorted(set(name) & INVALID_CHARS)
    if bad:
        return f"다음 문자는 쓸 수 없습니다: {' '.join(bad)}"
    if name.rstrip(". ") != name:
        return "이름 끝에 마침표나 공백을 둘 수 없습니다."
    if name.upper() in RESERVED:
        return f"'{name}' 은(는) Windows 가 예약한 이름입니다."
    if allow is not None and name.lower() == allow.lower():
        return None
    if (root / folder / f"{name}{MACRO_SUFFIX}").exists():
        return f"'{name}' 매크로가 이 폴더에 이미 있습니다."
    return None


def macro_path(folder: str, name: str, root: Optional[Path] = None) -> Path:
    root = root or library_root()
    return root / folder / f"{name.strip()}{MACRO_SUFFIX}"


def create_macro(folder: str, name: str, content: str,
                 root: Optional[Path] = None) -> Path:
    target = macro_path(folder, name, root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise FileExistsError(target)
    with open(target, "w", encoding="utf-8") as f:
        f.write(content)
    return target


def rename_macro(path: Path, new_name: str) -> Path:
    target = Path(path).with_name(f"{new_name.strip()}{MACRO_SUFFIX}")
    Path(path).rename(target)
    return target


def duplicate_macro(path: Path) -> Path:
    """같은 폴더에 '이름 (사본)' 으로 복제."""
    import shutil

    source = Path(path)
    stem = source.stem

    candidate = source.with_name(f"{stem} (사본){MACRO_SUFFIX}")
    index = 2
    while candidate.exists():
        candidate = source.with_name(f"{stem} (사본 {index}){MACRO_SUFFIX}")
        index += 1

    shutil.copy2(source, candidate)
    return candidate


def move_macro(path: Path, folder: str, root: Optional[Path] = None) -> Path:
    """다른 폴더로 옮긴다. 같은 이름이 있으면 거부."""
    root = root or library_root()
    source = Path(path)
    target = root / folder / source.name
    if target.exists():
        raise FileExistsError(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    source.rename(target)
    return target


def set_enabled(path: Path, enabled: bool) -> None:
    """매크로 파일의 사용 여부만 바꾼다. 나머지 내용은 그대로 둔다."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("매크로 파일 형식이 아닙니다.")

    data["enabled"] = bool(enabled)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def set_hotkeys(path: Path, start_key: str, stop_key: str) -> None:
    """실행·종료 단축키만 바꾼다. 나머지 내용은 그대로 둔다.

    단축키는 시작·종료 노드의 `hotkey` 에 적혀 있다. 종류마다 처음 하나에만
    적는 것은 `read_summary` 가 읽는 규칙과 같다 — 읽은 자리에 되돌려 써야
    목록에 보이던 값과 어긋나지 않는다.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), dict):
        raise ValueError("매크로 파일 형식이 아닙니다.")

    wanted = {"start": str(start_key or ""), "stop": str(stop_key or "")}
    for node in data["nodes"].values():
        if isinstance(node, dict) and node.get("type") in wanted:
            node["hotkey"] = wanted.pop(node["type"])
        if not wanted:
            break
    if len(wanted) == 2:
        raise ValueError("시작·종료 노드가 없어 단축키를 걸 수 없습니다.")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_macro(path: Path, root: Optional[Path] = None) -> None:
    """매크로 파일을 지운다. 되돌릴 수 없으므로 호출 전에 확인받을 것."""
    root = (root or library_root()).resolve()
    target = Path(path).resolve()

    # 라이브러리 밖 파일을 지우는 사고를 막는다
    if root not in target.parents or target.suffix.lower() != MACRO_SUFFIX:
        raise ValueError(f"라이브러리 안의 매크로가 아닙니다: {target}")

    target.unlink()


def delete_folder(name: str, root: Optional[Path] = None) -> None:
    """폴더를 통째로 지운다. 되돌릴 수 없으므로 호출 전에 반드시 확인받을 것."""
    import shutil

    root = root or library_root()
    target = (root / name).resolve()

    # 라이브러리 밖을 지우는 사고를 막는다
    if target.parent != root.resolve() or not target.is_dir():
        raise ValueError(f"라이브러리 안의 폴더가 아닙니다: {target}")

    shutil.rmtree(target)
