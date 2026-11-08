ISSUE120_STAGE_E_IMAGE ?= pdfscore_stage_e_reproduction
ISSUE120_PRODUCTION_IMAGE ?= pdfscore_pipeline_gpu

.PHONY: docker-build-stage-e eval-issue120-stage-e-full eval-issue120-stage-e-smoke

docker-build-stage-e: ## Build the historical reproduction extension from an explicit production image
	docker build -f docker/Dockerfile.stage-e --build-arg PRODUCTION_IMAGE=$(ISSUE120_PRODUCTION_IMAGE) -t $(ISSUE120_STAGE_E_IMAGE) .

ISSUE120_STAGE_E_OUTPUT ?= logs/issue120_e2e_recovery
ISSUE120_STAGE_E_RUN_ROOT ?= $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline
ISSUE120_STAGE_E_EVAL_INPUTS_DIR ?= $(ISSUE120_STAGE_E_RUN_ROOT)/eval_inputs
ISSUE120_STAGE_E_EVAL_DIR ?= $(ISSUE120_STAGE_E_RUN_ROOT)/eval_detector
ISSUE120_STAGE_E_GT_ROOT ?= data/evaluation2/annotations
ISSUE120_STAGE_E_IMAGE_ROOT ?= data/evaluation2/images
ISSUE120_STAGE_E_STAFF_UNITS_JSON ?= data/evaluation2/staff_units.json
ISSUE120_STAGE_E_SCORE_THRESHOLD ?= 0.1
ISSUE120_STAGE_E_XDIST_UNIT_RATIO ?= 0.5
ISSUE120_STAGE_E_SMOKE_PAGES ?= 2
ISSUE120_STAGE_E_EVAL_EXTRA_ARGS ?=

# run-issue120-stage-e-full was removed in #522: it executed the removed standard
# detector route. Reproduce that historical run from commit 4f1594bc; the eval targets
# below still score retained Stage E artifacts.

eval-issue120-stage-e-full: ## Build Stage E eval inputs and write detector contract outputs
	@echo "Evaluating Stage E Detector Contract from full-pipeline artifacts..."
	@PYTHONPATH=. python3 tools/issue120/eval_stage_e_contract.py \
		--output-root $(ISSUE120_STAGE_E_OUTPUT) \
		--eval-inputs-dir $(ISSUE120_STAGE_E_EVAL_INPUTS_DIR) \
		--eval-output-dir $(ISSUE120_STAGE_E_EVAL_DIR) \
		--gt-root $(ISSUE120_STAGE_E_GT_ROOT) \
		--score-threshold $(ISSUE120_STAGE_E_SCORE_THRESHOLD) \
		--staff-units-json $(ISSUE120_STAGE_E_STAFF_UNITS_JSON) \
		--xdist-unit-ratio $(ISSUE120_STAGE_E_XDIST_UNIT_RATIO) \
		--image-root $(ISSUE120_STAGE_E_IMAGE_ROOT) \
		$(ISSUE120_STAGE_E_EVAL_EXTRA_ARGS)

eval-issue120-stage-e-smoke: ## Smoke-check Stage E contract wiring on the first N pages
	@echo "Smoke-checking Stage E Detector Contract wiring from full-pipeline artifacts..."
	@$(MAKE) -f "$(lastword $(MAKEFILE_LIST))" eval-issue120-stage-e-full \
		ISSUE120_STAGE_E_EVAL_INPUTS_DIR=$(ISSUE120_STAGE_E_RUN_ROOT)/eval_inputs_smoke \
		ISSUE120_STAGE_E_EVAL_DIR=$(ISSUE120_STAGE_E_RUN_ROOT)/eval_detector_smoke \
		ISSUE120_STAGE_E_EVAL_EXTRA_ARGS="--page-limit $(ISSUE120_STAGE_E_SMOKE_PAGES) --allow-partial --allow-target-mismatch $(ISSUE120_STAGE_E_EVAL_EXTRA_ARGS)"
