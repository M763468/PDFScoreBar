ISSUE120_STAGE_E_CONFIG ?= configs/issue120_stage_e_full_pipeline.yaml
ISSUE120_STAGE_E_OUTPUT ?= logs/issue120_e2e_recovery
ISSUE120_STAGE_E_MANIFEST ?= $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline/manifest.json
ISSUE120_STAGE_E_EVAL_DIR ?= $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline/eval_detector
ISSUE120_STAGE_E_EXTRA_ARGS ?=
ISSUE163_HOMR_ROUTE_CONFIG_OVERRIDE ?= configs/issue163_homr_route_parallel_experiment.yaml
ISSUE163_HOMR_PHASE_CONFIG_OVERRIDE ?= configs/issue163_homr_inprocess_sr_prep_overlap_experiment.yaml
ISSUE163_HOMR_PHASE_SPLIT_CONFIG_OVERRIDE ?= configs/issue163_homr_phase_split_sequential_experiment.yaml
ISSUE163_HOMR_PHASE_ABCS_OUTPUT ?= logs/issue163_homr_phase_abcs
ISSUE163_HOMR_PHASE_ABCS_IMAGE_LIST ?= logs/issue163_homr_phase_abcs/image_subset.txt
ISSUE163_STAGE_E_EXTRA_ARGS ?= --config-override $(ISSUE163_HOMR_ROUTE_CONFIG_OVERRIDE) --resource-sample-interval-sec 1.0
ISSUE163_STAGE_E_PHASE_EXTRA_ARGS ?= --config-override $(ISSUE163_HOMR_PHASE_CONFIG_OVERRIDE) --resource-sample-interval-sec 1.0

run-issue120-stage-e-full: ## Run the full 68-page pipeline inside sr_eval_gpu container
	@echo "Running Full Stage E Pipeline inside sr_eval_gpu..."
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/bin/sh -lc '/opt/venv_pipeline/bin/python tools/issue120/run_stage_e_full_pipeline.py --config $(ISSUE120_STAGE_E_CONFIG) --output-root $(ISSUE120_STAGE_E_OUTPUT) $(ISSUE120_STAGE_E_EXTRA_ARGS); status=$$?; chmod -R a+rwX $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline 2>/dev/null || true; exit $$status'

run-issue163-stage-e-homr-overlap: ## Run the Issue #163 opt-in HOMR baseline/SR subprocess overlap Stage E experiment
	@$(MAKE) run-issue120-stage-e-full ISSUE120_STAGE_E_EXTRA_ARGS="$(ISSUE163_STAGE_E_EXTRA_ARGS)"

run-issue163-stage-e-homr-phase-overlap: ## Run the Issue #163 opt-in HOMR in-process SR-prep/baseline overlap experiment
	@$(MAKE) run-issue120-stage-e-full ISSUE120_STAGE_E_EXTRA_ARGS="$(ISSUE163_STAGE_E_PHASE_EXTRA_ARGS)"

run-issue163-homr-phase-default: ## Run Issue #163 HOMR-only A condition: default sequential on a fixed image subset
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/bin/sh -lc '/opt/venv_pipeline/bin/python tools/issue163/run_homr_phase_mode_experiment.py --mode default_sequential --config $(ISSUE120_STAGE_E_CONFIG) --image-list $(ISSUE163_HOMR_PHASE_ABCS_IMAGE_LIST) --output-root $(ISSUE163_HOMR_PHASE_ABCS_OUTPUT) --run-id A_default_sequential --resource-sample-interval-sec 1.0; status=$$?; chmod -R a+rwX $(ISSUE163_HOMR_PHASE_ABCS_OUTPUT) 2>/dev/null || true; exit $$status'

run-issue163-homr-phase-split-sequential: ## Run Issue #163 HOMR-only B condition: phase split without overlap on a fixed image subset
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/bin/sh -lc '/opt/venv_pipeline/bin/python tools/issue163/run_homr_phase_mode_experiment.py --mode phase_split_sequential --config $(ISSUE120_STAGE_E_CONFIG) --config-override $(ISSUE163_HOMR_PHASE_SPLIT_CONFIG_OVERRIDE) --image-list $(ISSUE163_HOMR_PHASE_ABCS_IMAGE_LIST) --output-root $(ISSUE163_HOMR_PHASE_ABCS_OUTPUT) --run-id B_phase_split_sequential --resource-sample-interval-sec 1.0; status=$$?; chmod -R a+rwX $(ISSUE163_HOMR_PHASE_ABCS_OUTPUT) 2>/dev/null || true; exit $$status'

run-issue163-homr-phase-split-overlap: ## Run Issue #163 HOMR-only C condition: phase split with SR-prep/baseline overlap on a fixed image subset
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/bin/sh -lc '/opt/venv_pipeline/bin/python tools/issue163/run_homr_phase_mode_experiment.py --mode phase_split_overlap --config $(ISSUE120_STAGE_E_CONFIG) --config-override $(ISSUE163_HOMR_PHASE_CONFIG_OVERRIDE) --image-list $(ISSUE163_HOMR_PHASE_ABCS_IMAGE_LIST) --output-root $(ISSUE163_HOMR_PHASE_ABCS_OUTPUT) --run-id C_phase_split_overlap --resource-sample-interval-sec 1.0; status=$$?; chmod -R a+rwX $(ISSUE163_HOMR_PHASE_ABCS_OUTPUT) 2>/dev/null || true; exit $$status'

run-issue163-homr-phase-abcs: ## Run Issue #163 HOMR-only A/B/C phase-mode comparison on a fixed image subset
	@$(MAKE) run-issue163-homr-phase-default
	@$(MAKE) run-issue163-homr-phase-split-sequential
	@$(MAKE) run-issue163-homr-phase-split-overlap

eval-issue120-stage-e-full: ## Evaluate Stage E detector metrics from manifest
	@echo "Evaluating Stage E Detector Metrics from manifest..."
	@PYTHONPATH=. python3 tools/issue120/eval_stage_e_from_manifest.py \
		--manifest $(ISSUE120_STAGE_E_MANIFEST) \
		--gt-root data/evaluation2/annotations \
		--output-dir $(ISSUE120_STAGE_E_EVAL_DIR) \
		--score-threshold 0.1 \
		--xdist-threshold 12.0
