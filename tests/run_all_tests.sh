#!/usr/bin/env bash
# Master test runner for the ICVFX Telemetry & Synchronization Engine.
# Builds the C++ core, then runs every correctness, edge-case, and stress
# test suite in the repo, in order. Prints one pass/fail line per suite and
# exits non-zero if anything failed - safe to wire into CI as-is.
#
# Usage: ./tests/run_all_tests.sh
set -uo pipefail
cd "$(dirname "$0")/.."   # repo root

PASS=0
FAIL=0
FAILED_SUITES=()

run_suite() {
    local label="$1"; shift
    echo ""
    echo "=== $label ==="
    if "$@"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED_SUITES+=("$label")
    fi
}

echo "=== building cpp-core ==="
(cd cpp-core && ./build.sh) || { echo "cpp-core build FAILED - aborting"; exit 1; }
g++ -std=c++20 -O2 -Wall -Wextra -pthread -o cpp-core/tests/test_codec cpp-core/tests/test_codec.cpp \
    || { echo "test_codec build FAILED - aborting"; exit 1; }

run_suite "C++ codec unit tests"            cpp-core/tests/test_codec
run_suite "Ingest daemon edge cases"        python3 tests/test_ingest_edge_cases.py
run_suite "Throughput / load stress tests"  python3 tests/stress_test_throughput.py
run_suite "Incident arbiter edge cases"     python3 tests/test_arbiter_edge_cases.py
run_suite "MCP remediation server edge cases" python3 tests/test_mcp_server_edge_cases.py
run_suite "End-to-end fault injection (orchestrator)" python3 orchestrator/run_fault_injection_test.py

echo ""
echo "=================================="
echo "SUITES PASSED: $PASS   SUITES FAILED: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo "Failed suites:"
    for s in "${FAILED_SUITES[@]}"; do echo "  - $s"; done
    exit 1
fi
echo "ALL SUITES PASSED"
exit 0
