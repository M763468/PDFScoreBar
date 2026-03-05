#!/bin/bash
set -euo pipefail
TEST_PATH=${1:-tests/}
mkdir -p artifacts
echo "Running pytest on $TEST_PATH..."
pytest "$TEST_PATH" > artifacts/test_results.txt
echo "Artifact generated: artifacts/test_results.txt"
