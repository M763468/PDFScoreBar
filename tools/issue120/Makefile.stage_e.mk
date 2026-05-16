ISSUE120_STAGE_E_CONFIG ?= configs/issue120_stage_e_full_pipeline.yaml
ISSUE120_STAGE_E_OUTPUT ?= logs/issue120_e2e_recovery

run-issue120-stage-e-full: ## Run the full 68-page pipeline inside sr_eval_gpu container
	@echo "Running Full Stage E Pipeline inside sr_eval_gpu..."
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/opt/venv_pipeline/bin/python tools/issue120/run_stage_e_full_pipeline.py --config $(ISSUE120_STAGE_E_CONFIG) --output-root $(ISSUE120_STAGE_E_OUTPUT)

eval-issue120-stage-e-full: ## Evaluate Stage E detector metrics against golden baseline
	@echo "Evaluating Stage E Detector Metrics..."
	@PYTHONPATH=. python3 tools/issue120/eval_full68_from_intermediates.py \
		--results-dir $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline/intermediate \
		--gt-root data/evaluation2/annotations \
		--output-dir $(ISSUE120_STAGE_E_OUTPUT)/stage_e_full_pipeline/eval_detector \
		--score-threshold 0.1 \
		--xdist-threshold 12.0
