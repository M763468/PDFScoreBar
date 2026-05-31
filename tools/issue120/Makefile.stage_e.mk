ISSUE120_STAGE_E_CONFIG ?= configs/issue120_stage_e_full_pipeline.yaml
ISSUE120_STAGE_E_OUTPUT ?= logs/issue120_e2e_recovery
ISSUE120_STAGE_E_MANIFEST ?= $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline/manifest.json
ISSUE120_STAGE_E_EVAL_DIR ?= $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline/eval_detector
ISSUE120_STAGE_E_EXTRA_ARGS ?=

run-issue120-stage-e-full: ## Run the full 68-page pipeline inside sr_eval_gpu container
	@echo "Running Full Stage E Pipeline inside sr_eval_gpu..."
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace \
		-e PYTHONPATH=/workspace \
		-e PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS \
		-e PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS \
		-e PDFSCORE_SR_TILE_LOGS \
		pdfscore_pipeline_gpu \
		/bin/sh -lc '/opt/venv_pipeline/bin/python tools/issue120/run_stage_e_full_pipeline.py --config $(ISSUE120_STAGE_E_CONFIG) --output-root $(ISSUE120_STAGE_E_OUTPUT) $(ISSUE120_STAGE_E_EXTRA_ARGS); status=$$?; chmod -R a+rwX $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline 2>/dev/null || true; exit $$status'

eval-issue120-stage-e-full: ## Evaluate Stage E detector metrics from manifest
	@echo "Evaluating Stage E Detector Metrics from manifest..."
	@PYTHONPATH=. python3 tools/issue120/eval_stage_e_from_manifest.py \
		--manifest $(ISSUE120_STAGE_E_MANIFEST) \
		--gt-root data/evaluation2/annotations \
		--output-dir $(ISSUE120_STAGE_E_EVAL_DIR) \
		--score-threshold 0.1 \
		--xdist-threshold 12.0
