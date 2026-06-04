ISSUE120_STAGE_E_CONFIG ?= configs/issue120_stage_e_full_pipeline.yaml
ISSUE120_STAGE_E_OUTPUT ?= logs/issue120_e2e_recovery
ISSUE120_STAGE_E_RUN_ROOT ?= $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline
ISSUE120_STAGE_E_EVAL_INPUTS_DIR ?= $(ISSUE120_STAGE_E_RUN_ROOT)/eval_inputs
ISSUE120_STAGE_E_EVAL_DIR ?= $(ISSUE120_STAGE_E_RUN_ROOT)/eval_detector
ISSUE120_STAGE_E_GT_ROOT ?= data/evaluation2/annotations
ISSUE120_STAGE_E_SCORE_THRESHOLD ?= 0.1
ISSUE120_STAGE_E_XDIST_THRESHOLD ?= 12.0
ISSUE120_STAGE_E_SMOKE_PAGES ?= 2
ISSUE120_STAGE_E_EXTRA_ARGS ?=
ISSUE120_STAGE_E_EVAL_EXTRA_ARGS ?=

run-issue120-stage-e-full: ## Run the full 68-page pipeline inside sr_eval_gpu container
	@echo "Running Full Stage E Pipeline inside sr_eval_gpu..."
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace \
		-e PYTHONPATH=/workspace \
		-e PDFSCORE_STAGE_E_DIAGNOSTIC_LOGS \
		-e PDFSCORE_HOMR_VERBOSE_INTERNAL_LOGS \
		-e PDFSCORE_SR_TILE_LOGS \
		pdfscore_pipeline_gpu \
		/bin/sh -lc '/opt/venv_pipeline/bin/python tools/issue120/run_stage_e_full_pipeline.py --config $(ISSUE120_STAGE_E_CONFIG) --output-root $(ISSUE120_STAGE_E_OUTPUT) $(ISSUE120_STAGE_E_EXTRA_ARGS); status=$$?; chmod -R a+rwX $(ISSUE120_STAGE_E_RUN_ROOT) 2>/dev/null || true; exit $$status'

eval-issue120-stage-e-full: ## Build Stage E eval inputs and write detector contract outputs
	@echo "Evaluating Stage E Detector Contract from full-pipeline artifacts..."
	@PYTHONPATH=. python3 tools/issue120/eval_stage_e_contract.py \
		--output-root $(ISSUE120_STAGE_E_OUTPUT) \
		--eval-inputs-dir $(ISSUE120_STAGE_E_EVAL_INPUTS_DIR) \
		--eval-output-dir $(ISSUE120_STAGE_E_EVAL_DIR) \
		--gt-root $(ISSUE120_STAGE_E_GT_ROOT) \
		--score-threshold $(ISSUE120_STAGE_E_SCORE_THRESHOLD) \
		--xdist-threshold $(ISSUE120_STAGE_E_XDIST_THRESHOLD) \
		$(ISSUE120_STAGE_E_EVAL_EXTRA_ARGS)

eval-issue120-stage-e-smoke: ## Smoke-check Stage E contract wiring on the first N pages
	@echo "Smoke-checking Stage E Detector Contract wiring from full-pipeline artifacts..."
	@$(MAKE) eval-issue120-stage-e-full \
		ISSUE120_STAGE_E_EVAL_INPUTS_DIR=$(ISSUE120_STAGE_E_RUN_ROOT)/eval_inputs_smoke \
		ISSUE120_STAGE_E_EVAL_DIR=$(ISSUE120_STAGE_E_RUN_ROOT)/eval_detector_smoke \
		ISSUE120_STAGE_E_EVAL_EXTRA_ARGS="--page-limit $(ISSUE120_STAGE_E_SMOKE_PAGES) --allow-partial --allow-target-mismatch $(ISSUE120_STAGE_E_EVAL_EXTRA_ARGS)"
