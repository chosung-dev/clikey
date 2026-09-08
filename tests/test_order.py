"""매크로 차례(손으로 정한 순서) 테스트 — 임시 홈에서만 돈다.

    python tests/test_order.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 앱 상태 파일을 실제 홈이 아니라 임시 폴더에 두게 한다. persistence 는 부를
# 때마다 홈을 다시 물으므로, import 전에 잡아두면 된다.
_HOME = tempfile.mkdtemp()
os.environ["HOME"] = _HOME
os.environ["USERPROFILE"] = _HOME

from core import persistence  # noqa: E402
from ui_qt.home import Macro, in_order, settle  # noqa: E402


def fresh():
    """앱 상태를 비운다. 테스트끼리 값이 새지 않게."""
    path = os.path.join(_HOME, ".clikey", "app_state.json")
    if os.path.exists(path):
        os.remove(path)


def macros(*names):
    return [Macro(name=n, folder="게임", nodes=1, last_run="—") for n in names]


# ---------------------------------------------------------------- 차례 세우기

def test_no_order_leaves_the_list_alone():
    given = macros("가", "나", "다")
    assert [m.name for m in in_order(given, [], key=lambda m: m.name)] == ["가", "나", "다"]


def test_follows_the_saved_order():
    given = macros("가", "나", "다")
    got = in_order(given, ["다", "가", "나"], key=lambda m: m.name)
    assert [m.name for m in got] == ["다", "가", "나"]


def test_new_macros_come_first():
    """차례를 정한 뒤에 만든 매크로는 위에 선다 — 원래 최근 것이 위였다."""
    given = macros("가", "나", "새로 만든 것")
    got = in_order(given, ["나", "가"], key=lambda m: m.name)
    assert [m.name for m in got] == ["새로 만든 것", "나", "가"]


# ---------------------------------------------------------------- 굳히기

def test_settle_freezes_a_new_list():
    """처음 본 목록은 그 차례 그대로 적어둔다 — 그래야 안 흔들린다."""
    kept = []
    got = settle(["다", "가", "나"], [], key=lambda n: n, remember=kept.append)
    assert got == ["다", "가", "나"]
    assert kept == [["다", "가", "나"]]


def test_settle_leaves_a_settled_list_alone():
    """이미 다 적혀 있으면 다시 적지 않는다 — 볼 때마다 쓸 이유가 없다."""
    kept = []
    got = settle(["가", "나"], ["나", "가"], key=lambda n: n, remember=kept.append)
    assert got == ["나", "가"]
    assert kept == []


def test_settle_records_newcomers():
    kept = []
    settle(["가", "나", "새것"], ["나", "가"], key=lambda n: n, remember=kept.append)
    assert kept == [["새것", "나", "가"]]


def test_settle_ignores_an_empty_list():
    """폴더가 비어 있다고 차례를 지워버리면 안 된다."""
    kept = []
    assert settle([], ["가", "나"], key=lambda n: n, remember=kept.append) == []
    assert kept == []


def test_missing_macros_are_skipped():
    """차례에 적힌 것이 사라져도 남은 것들의 순서는 지켜진다."""
    given = macros("가", "다")
    got = in_order(given, ["다", "나", "가"], key=lambda m: m.name)
    assert [m.name for m in got] == ["다", "가"]


# ---------------------------------------------------------------- 적어두기

def test_round_trip():
    fresh()
    persistence.save_macro_order("게임", ["다", "가", "나"])
    assert persistence.load_macro_order("게임") == ["다", "가", "나"]


def test_unknown_folder_is_empty():
    fresh()
    assert persistence.load_macro_order("없는 폴더") == []


def test_folders_do_not_bleed_into_each_other():
    fresh()
    persistence.save_macro_order("게임", ["가"])
    persistence.save_macro_order("업무", ["나"])
    assert persistence.load_macro_order("게임") == ["가"]
    assert persistence.load_macro_order("업무") == ["나"]


def test_folder_rename_carries_the_order():
    fresh()
    persistence.save_macro_order("게임", ["가", "나"])
    persistence.move_macro_order("게임", "놀이")
    assert persistence.load_macro_order("게임") == []
    assert persistence.load_macro_order("놀이") == ["가", "나"]


def test_folder_delete_drops_the_order():
    fresh()
    persistence.save_macro_order("게임", ["가", "나"])
    persistence.move_macro_order("게임", None)
    assert persistence.load_macro_order("게임") == []


def test_moving_an_unknown_folder_does_nothing():
    fresh()
    persistence.save_macro_order("게임", ["가"])
    persistence.move_macro_order("없는 폴더", "어딘가")
    assert persistence.load_macro_order("게임") == ["가"]
    assert persistence.load_macro_order("어딘가") == []


# ---------------------------------------------------------------- 폴더 차례

def test_folder_order_round_trip():
    fresh()
    persistence.save_folder_order(["다", "가", "나"])
    assert persistence.load_folder_order() == ["다", "가", "나"]


def test_folder_order_starts_empty():
    fresh()
    assert persistence.load_folder_order() == []


def test_folder_order_follows_a_rename():
    fresh()
    persistence.save_folder_order(["가", "나"])
    persistence.rename_in_folder_order("가", "새이름")
    assert persistence.load_folder_order() == ["새이름", "나"]


def test_folder_order_drops_a_deleted_folder():
    fresh()
    persistence.save_folder_order(["가", "나"])
    persistence.rename_in_folder_order("가", None)
    assert persistence.load_folder_order() == ["나"]


def test_folder_order_ignores_an_unknown_name():
    fresh()
    persistence.save_folder_order(["가"])
    persistence.rename_in_folder_order("없는 폴더", "무엇")
    assert persistence.load_folder_order() == ["가"]


def test_folder_and_macro_orders_live_side_by_side():
    fresh()
    persistence.save_folder_order(["가", "나"])
    persistence.save_macro_order("가", ["하나", "둘"])
    assert persistence.load_folder_order() == ["가", "나"]
    assert persistence.load_macro_order("가") == ["하나", "둘"]


def test_other_app_state_survives():
    """차례를 적는다고 창 크기 같은 다른 상태가 지워지면 안 된다."""
    fresh()
    persistence.save_app_state({"home_window": [100, 200]})
    persistence.save_macro_order("게임", ["가"])
    assert persistence.load_app_state().get("home_window") == [100, 200]


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
    shutil.rmtree(_HOME, ignore_errors=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
