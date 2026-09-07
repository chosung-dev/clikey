"""core.library 파일 조작 테스트 — 임시 폴더에서만 돈다.

    python tests/test_library.py
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import library  # noqa: E402


def sample(start="f8", stop="f9"):
    return {
        "version": 1,
        "nodes": {
            "start": {"type": "start", "hotkey": start, "step_delay": 0.05},
            "d1": {"type": "delay", "seconds": 2},
            "end": {"type": "stop", "hotkey": stop},
        },
        "edges": [{"from": "start", "to": "d1"}, {"from": "d1", "to": "end"}],
        "entry": "start",
        "layout": {"start": [10, 20]},
        "enabled": True,
    }


def write(data):
    """임시 매크로 파일 하나를 만들고 경로를 돌려준다."""
    folder = tempfile.mkdtemp()
    path = os.path.join(folder, "테스트.clikey")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- set_hotkeys

def test_sets_both_keys():
    path = write(sample())
    try:
        library.set_hotkeys(path, "f10", "f11")
        data = read(path)
        assert data["nodes"]["start"]["hotkey"] == "f10"
        assert data["nodes"]["end"]["hotkey"] == "f11"
    finally:
        shutil.rmtree(os.path.dirname(path))


def test_keeps_everything_else():
    """단축키만 바꾼다 — 노드 값도 자리도 건드리지 않는다."""
    path = write(sample())
    try:
        before = read(path)
        library.set_hotkeys(path, "ctrl+alt+f5", "")
        after = read(path)

        assert after["nodes"]["d1"] == before["nodes"]["d1"]
        assert after["nodes"]["start"]["step_delay"] == 0.05
        assert after["layout"] == before["layout"]
        assert after["edges"] == before["edges"]
        assert after["enabled"] is True
        assert after["nodes"]["end"]["hotkey"] == ""       # 해제도 저장된다
    finally:
        shutil.rmtree(os.path.dirname(path))


def test_reads_back_what_the_list_shows():
    """목록이 읽는 자리(read_summary)와 쓰는 자리가 같아야 한다."""
    path = write(sample())
    try:
        library.set_hotkeys(path, "f6", "f7")
        nodes, start_key, stop_key, enabled = library.read_summary(Path(path))
        assert (start_key, stop_key) == ("f6", "f7")
        assert nodes == 3 and enabled is True
    finally:
        shutil.rmtree(os.path.dirname(path))


def test_adds_the_key_when_the_node_had_none():
    data = sample()
    del data["nodes"]["start"]["hotkey"]
    del data["nodes"]["end"]["hotkey"]
    path = write(data)
    try:
        library.set_hotkeys(path, "f8", "f9")
        assert read(path)["nodes"]["start"]["hotkey"] == "f8"
        assert read(path)["nodes"]["end"]["hotkey"] == "f9"
    finally:
        shutil.rmtree(os.path.dirname(path))


def test_refuses_a_file_without_start_or_stop():
    data = sample()
    data["nodes"] = {"d1": {"type": "delay", "seconds": 2}}
    path = write(data)
    try:
        try:
            library.set_hotkeys(path, "f8", "f9")
        except ValueError:
            pass
        else:
            raise AssertionError("시작·종료가 없는데 통과했다")
        assert "hotkey" not in read(path)["nodes"]["d1"]    # 그대로 둔다
    finally:
        shutil.rmtree(os.path.dirname(path))


def test_refuses_a_file_that_is_not_a_macro():
    path = write([1, 2, 3])
    try:
        try:
            library.set_hotkeys(path, "f8", "f9")
        except ValueError:
            pass
        else:
            raise AssertionError("매크로가 아닌데 통과했다")
    finally:
        shutil.rmtree(os.path.dirname(path))


# ----------------------------------------------------------------

def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            print(f"      {type(exc).__name__}: {str(exc)[:300]}")
        else:
            print(f"ok    {fn.__name__}")
    print(f"\n{len(tests) - failed}/{len(tests)} 통과")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
