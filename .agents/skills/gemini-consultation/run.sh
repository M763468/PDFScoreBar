#!/bin/bash
set -euo pipefail
# This script wraps gemini -p to ensure artifact-based result logging.
# Usage: bash .agents/skills/gemini-consultation/run.sh "prompt"
PROMPT=$1
mkdir -p artifacts

echo "Consulting Gemini: $PROMPT"
# Using a long timeout for deep reasoning
timeout 300s gemini -p "$PROMPT" > artifacts/gemini_consultation.txt 2>&1 || echo "Gemini consultation timed out or failed." >> artifacts/gemini_consultation.txt

echo "Artifact generated: artifacts/gemini_consultation.txt"
