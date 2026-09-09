"""Tiny dependency-free test runner (no pytest needed). Each test_*.py file
defines test_* functions and calls `main(sys.modules[__name__])` in its
`if __name__ == "__main__":` block. Exits 0 if all tests passed, 1 otherwise
- suitable for a shell script to chain with `&&` / check exit codes.
"""

from __future__ import annotations

import sys
import time
import traceback


def run_module_tests(module) -> bool:
    tests = [(name, f) for name, f in vars(module).items() if name.startswith("test_") and callable(f)]
    tests.sort(key=lambda nf: nf[1].__code__.co_firstlineno)

    passed, failed = 0, 0
    for name, fn in tests:
        t0 = time.monotonic()
        try:
            fn()
            dt = time.monotonic() - t0
            print(f"[ OK ] {name} ({dt:.2f}s)")
            passed += 1
        except AssertionError as e:
            dt = time.monotonic() - t0
            print(f"[FAIL] {name} ({dt:.2f}s): {e}")
            failed += 1
        except Exception as e:
            dt = time.monotonic() - t0
            print(f"[FAIL] {name} ({dt:.2f}s): unexpected {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{module.__name__}: {passed} passed, {failed} failed (of {len(tests)})")
    return failed == 0


def main(module) -> None:
    ok = run_module_tests(module)
    sys.exit(0 if ok else 1)
