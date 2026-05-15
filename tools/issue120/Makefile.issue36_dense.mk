# Issue #120 / #149 dense candidate producer validation targets.
# Use with:
#   make -f Makefile -f tools/issue120/Makefile.issue36_dense.mk verify-issue120-issue36-dense

ISSUE120_ISSUE36_DENSE_OUTPUT_ROOT ?= logs/issue120_e2e_recovery/stage_d_issue36_dense_candidate_validation
ISSUE120_ISSUE36_DENSE_INVENTORY ?= logs/issue36_prep/20260208_bench_inventory.json
ISSUE120_ISSUE36_DENSE_EXCLUDE ?= logs/issue36_prep/excluded_pages_for_gt_prep.json
ISSUE120_ISSUE36_DENSE_REQUIRE_TARGET ?= 0

verify-issue120-issue36-dense: ## Regenerate Issue #36 v12 dense candidates, score, and evaluate Issue #120 detector metrics
	@mkdir -p artifacts
	@LOG_FILE="artifacts/issue120_issue36_dense_verify_$$(date +%Y%m%d_%H%M%S).log"; \
	TARGET_ARG=""; \
	if [ "$(ISSUE120_ISSUE36_DENSE_REQUIRE_TARGET)" = "1" ]; then TARGET_ARG="--require-detector-target"; fi; \
	echo "Running Issue #120/#149 Issue36 dense candidate validation. Logging to $$LOG_FILE..."; \
	docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace $(ISSUE120_DOCKER_IMAGE) \
		$(ISSUE120_DOCKER_PYTHON) tools/issue120/run_issue36_dense_candidates_then_eval.py \
		--inventory "$(ISSUE120_ISSUE36_DENSE_INVENTORY)" \
		--exclude "$(ISSUE120_ISSUE36_DENSE_EXCLUDE)" \
		--image-root "$(ISSUE120_IMAGE_ROOT)" \
		--gt-root "$(ISSUE120_GT_ROOT)" \
		--model-path "$(ISSUE120_MODEL_PATH)" \
		--output-root "$(ISSUE120_ISSUE36_DENSE_OUTPUT_ROOT)" \
		--score-threshold "$(ISSUE120_SCORE_THRESHOLD)" \
		--xdist-threshold "$(ISSUE120_XDIST_THRESHOLD)" \
		--no-pipeline-nms \
		$$TARGET_ARG > "$$LOG_FILE" 2>&1 || \
		(EXIT_CODE=$$?; echo "Issue36 dense candidate validation failed with exit code $$EXIT_CODE. See $$LOG_FILE"; exit $$EXIT_CODE); \
	echo "Issue36 dense candidate validation complete. See $$LOG_FILE"
