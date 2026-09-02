"""실행 기록 저장. 진짜 ~/.clikey 를 건드리지 않게 홈을 임시로 돌려놓고 돈다."""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

_HOME = Path(tempfile.mkdtemp(prefix="clikey_test_home_"))
os.environ["USERPROFILE"] = str(_HOME)
os.environ["HOME"] = str(_HOME)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import runlog                                    # noqa: E402
from core.persistence import _app_state_path               # noqa: E402

assert str(_HOME) in _app_state_path(), "앱 상태가 샌드박스 밖을 가리킵니다"


def clear():
    from core.persistence import save_app_state
    save_app_state({runlog.STATE_KEY: {}})


def test_unrun_macro_reads_as_never():
    clear()
    assert runlog.get("C:/없는것.json") == 0.0
    assert runlog.text("C:/없는것.json") == "—"


def test_mark_then_read_back():
    clear()
    when = runlog.mark("C:/가.json")
    assert runlog.get("C:/가.json") == when
    assert runlog.text("C:/가.json") == "방금"


def test_rename_carries_the_record():
    clear()
    when = runlog.mark("C:/가.json")
    runlog.rename("C:/가.json", "C:/나.json")
    assert runlog.get("C:/가.json") == 0.0
    assert runlog.get("C:/나.json") == when


def test_rename_of_unrun_macro_is_harmless():
    clear()
    runlog.rename("C:/없던것.json", "C:/새것.json")
    assert runlog.get("C:/새것.json") == 0.0


def test_forget_removes_it():
    clear()
    runlog.mark("C:/가.json")
    runlog.forget("C:/가.json")
    assert runlog.get("C:/가.json") == 0.0


def test_old_records_are_pruned_newest_first():
    clear()
    now = time.time()
    for i in range(runlog.LIMIT + 10):
        runlog.mark(f"C:/{i}.json", when=now + i)

    kept = runlog._load()
    assert len(kept) == runlog.LIMIT
    # 가장 오래된 열 개가 밀려나야 한다
    assert "C:/0.json" not in kept
    assert f"C:/{runlog.LIMIT + 9}.json" in kept


def test_junk_in_state_is_ignored():
    from core.persistence import save_app_state
    save_app_state({runlog.STATE_KEY: {"C:/가.json": "어제", "C:/나.json": 123.0}})
    table = runlog._load()
    assert "C:/가.json" not in table
    assert table["C:/나.json"] == 123.0


# ----------------------------------------------------------------

def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
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
    shutil.rmtree(_HOME, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
