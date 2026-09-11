#!/usr/bin/env bash
set -euo pipefail

# One-shot local execution driver for Issue #294 after merging develop/#277.
# Repository changes are experiment-only. Production source/config/dispatch are not edited.

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
cd "$PROJECT_ROOT"

CONTAINER="${ISSUE294_CONTAINER:-pdfscore_issue294_profile_worktree}"
REQUIRED_DEVELOP="edc17ee08de6694827c67d4ab8b30c2adc1f05e3"
LATEST_HOMR="${ISSUE294_LATEST_HOMR_COMMIT:-457e7c6518a10ba755db2e60883419e56c4d7369}"
ACCEPTED_REBASE="${ISSUE294_ACCEPTED_REBASE_REPORT:-/home/masaki_muramatsu/issue264_phase_c_rescore/phase_c_mmr_geometry_rebased_score_report.json}"
OLD_MANIFEST="${ISSUE294_RETAINED_MANIFEST:-$PROJECT_ROOT/logs/issue294/issue294_full68_refresh_02/full68_host.json}"
WEIGHT_REL="external/realesrgan/weights/RealESRGAN_x4plus.pth"
WEIGHT_SHA="4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
WEIGHT_SIZE="67040989"
STAMP="${ISSUE294_RUN_SUFFIX:-$(date +%Y%m%d_%H%M%S)}"
RUN_TAG="${ISSUE294_RUN_TAG:-issue294_post277_full68_${STAMP}}"
FOCUSED_OUT="$PROJECT_ROOT/logs/issue294/issue294_post277_focused_${STAMP}.json"
FULL_MMR_OUT="$PROJECT_ROOT/logs/issue294/${RUN_TAG}/post277_mapping_guarded_mmr.json"
LOCAL_LOG="$PROJECT_ROOT/logs/issue294/${RUN_TAG}_resume_local.log"
CONTAINER_ACCEPTED="/tmp/issue294_phase_c_mmr_geometry_rebased_score_report.json"

mkdir -p "$PROJECT_ROOT/logs/issue294"
exec > >(tee -a "$LOCAL_LOG") 2>&1

printf 'Issue #294 post-#277 local runner\n'
printf 'repo=%s\nrun_tag=%s\ncontainer=%s\n' "$PROJECT_ROOT" "$RUN_TAG" "$CONTAINER"

HEAD="$(git rev-parse HEAD)"
if ! git merge-base --is-ancestor "$REQUIRED_DEVELOP" "$HEAD"; then
  echo "ERROR: HEAD=$HEAD does not contain required develop commit $REQUIRED_DEVELOP"
  echo "Merge origin/develop into perf/issue294-homr-baseline-refresh first."
  exit 2
fi
printf 'execution_head=%s\nrequired_develop=%s\n' "$HEAD" "$REQUIRED_DEVELOP"

if [[ ! -f "$ACCEPTED_REBASE" ]]; then
  echo "ERROR: accepted #264 rebase report missing: $ACCEPTED_REBASE"
  exit 2
fi
if [[ ! -f "$OLD_MANIFEST" ]]; then
  echo "ERROR: retained valid full68 manifest missing: $OLD_MANIFEST"
  exit 2
fi

if [[ "$(docker inspect --format '{{.State.Running}}' "$CONTAINER")" != "true" ]]; then
  echo "ERROR: container is not running: $CONTAINER"
  exit 2
fi

# Keep the accepted physical-GT report outside tracked/bind-mounted repository state.
docker cp "$ACCEPTED_REBASE" "$CONTAINER:$CONTAINER_ACCEPTED"

# Validate the known Real-ESRGAN production support weight before any expensive inference.
WEIGHT_SOURCE=""
WEIGHT_CANDIDATES=()
if [[ -n "${ISSUE294_REALESRGAN_WEIGHT:-}" ]]; then
  WEIGHT_CANDIDATES+=("$ISSUE294_REALESRGAN_WEIGHT")
fi
WEIGHT_CANDIDATES+=(
  "$PROJECT_ROOT/$WEIGHT_REL"
  "$PROJECT_ROOT/../ws_PDFScoreBar/$WEIGHT_REL"
)
for candidate in "${WEIGHT_CANDIDATES[@]}"; do
  if [[ -f "$candidate" ]] \
    && [[ "$(stat -c '%s' "$candidate")" == "$WEIGHT_SIZE" ]] \
    && [[ "$(sha256sum "$candidate" | awk '{print $1}')" == "$WEIGHT_SHA" ]]; then
    WEIGHT_SOURCE="$candidate"
    break
  fi
done
if [[ -z "$WEIGHT_SOURCE" ]]; then
  echo "ERROR: verified RealESRGAN_x4plus.pth not found."
  echo "Set ISSUE294_REALESRGAN_WEIGHT to the verified weight path or place it at $PROJECT_ROOT/$WEIGHT_REL."
  exit 2
fi
mkdir -p "$PROJECT_ROOT/$(dirname "$WEIGHT_REL")"
if [[ "$WEIGHT_SOURCE" != "$PROJECT_ROOT/$WEIGHT_REL" ]]; then
  cp -p "$WEIGHT_SOURCE" "$PROJECT_ROOT/$WEIGHT_REL"
fi
CONTAINER_WEIGHT_SHA="$(docker exec "$CONTAINER" sha256sum "/workspace/$WEIGHT_REL" | awk '{print $1}')"
if [[ "$CONTAINER_WEIGHT_SHA" != "$WEIGHT_SHA" ]]; then
  echo "ERROR: container does not see verified Real-ESRGAN weight: $CONTAINER_WEIGHT_SHA"
  exit 2
fi

printf '\n=== targeted post-#277 tests ===\n'
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python -m pytest \
  tests/test_issue294_post277_mapping_guarded_mmr.py \
  tests/test_issue294_post277_full68_host.py \
  tests/test_issue294_mapping_guarded_connector_positive_candidate.py \
  tests/test_issue294_full68_host.py \
  tests/test_issue294_downstream_candidate_matrix.py \
  tests/test_mmr_ocr_heuristics.py

printf '\n=== repository fast/lint gates ===\n'
make test-fast
make lint

printf '\n=== focused retained-artifact post-#277 MMR gate ===\n'
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python tools/issue294/run_post277_mapping_guarded_mmr.py \
  --full68-manifest /workspace/logs/issue294/issue294_full68_refresh_02/full68_host.json \
  --accepted-rebase-report "$CONTAINER_ACCEPTED" \
  --output "/workspace/logs/issue294/$(basename "$FOCUSED_OUT")"

printf '\n=== true-x4 fixed-support smoke ===\n'
SMOKE_ROOT="/workspace/temp/${RUN_TAG}_fixed_support_smoke"
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python tools/issue294/run_fixed_support_smoke.py \
  --image /workspace/data/evaluation2/images/Va_Prokofiev_Symphony1/page_004.png \
  --output-root "$SMOKE_ROOT"

printf '\n=== fresh mapping-guarded canonical full68 ===\n'
PYTHON="${ISSUE294_HOST_PYTHON:-$PROJECT_ROOT/.venv_pdf/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "ERROR: host Python missing/not executable: $PYTHON"
  exit 2
fi
"$PYTHON" tools/issue294/run_post277_mapping_guarded_full68_host.py \
  --run-tag "$RUN_TAG" \
  --latest-homr-commit "$LATEST_HOMR" \
  --chunk-size 6

printf '\n=== fresh full68 post-#277 MMR semantic gate ===\n'
docker exec -w /workspace -e PYTHONPATH=/workspace "$CONTAINER" \
  /opt/venv_pipeline/bin/python tools/issue294/run_post277_mapping_guarded_mmr.py \
  --full68-manifest "/workspace/logs/issue294/${RUN_TAG}/full68_host.json" \
  --accepted-rebase-report "$CONTAINER_ACCEPTED" \
  --full68 \
  --expect-production-reference \
  --require-manifest-head \
  --output "/workspace/logs/issue294/${RUN_TAG}/post277_mapping_guarded_mmr.json"

printf '\n=== completed ===\n'
printf 'head=%s\nrun_tag=%s\nfocused=%s\nmanifest=%s\nmmr=%s\nlog=%s\n' \
  "$HEAD" \
  "$RUN_TAG" \
  "$FOCUSED_OUT" \
  "$PROJECT_ROOT/logs/issue294/$RUN_TAG/full68_host.json" \
  "$FULL_MMR_OUT" \
  "$LOCAL_LOG"
