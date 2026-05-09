.PHONY: help lint format

ISSUE120_RESULTS_DIR ?= data/evaluation2/golden_baseline_eval2_bc23deb
ISSUE120_GT_ROOT ?= data/evaluation2/annotations
ISSUE120_OUTPUT_DIR ?= logs/issue120_e2e_recovery/latest_full_report
ISSUE120_SCORE_THRESHOLD ?= 0.1
ISSUE120_XDIST_THRESHOLD ?= 12.0
ISSUE120_MEASURE_SUMMARY ?=

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run lint and format checks using ruff
	uvx ruff check . && uvx ruff format --check .

format: ## Format code using ruff
	uvx ruff format .
	uvx ruff check --fix .

clean-artifacts: ## Remove all logs from the artifacts directory
	rm -f artifacts/*.log artifacts/*.txt

clean-logs: ## Remove old logs (older than 30d) from logs/ category subdirs, excluding protected ones
	@echo "Cleaning up old logs..."
	@find logs/runs logs/eval logs/experiments -maxdepth 1 -type d -mtime +30 \
		! -name ".*" \
		! -name "*_keep_*" \
		! -name "*_final_*" \
		! -exec test -e "{}/.keep" \; \
		-print -exec rm -rf {} +

docker-clean: ## Remove the pipeline container and image (cleanup for space saving)
	@echo "Cleaning up Docker container and image..."
	-docker rm -f pdfscore_pipeline_gpu
	-docker rmi pdfscore_pipeline_gpu

docker-build: ## Build the unified Docker image with cleanup and logging to artifacts/
	@mkdir -p artifacts
	@echo "Starting Docker build. Logging to artifacts/docker_build.log..."
	-$(MAKE) docker-clean
	docker build -t pdfscore_pipeline_gpu . > artifacts/docker_build.log 2>&1 || \
		(EXIT_CODE=$$?; echo "Docker build failed with exit code $$EXIT_CODE. See artifacts/docker_build.log"; exit $$EXIT_CODE)
	@echo "Docker build finished successfully."

promote-log: ## Promote a log from worktree to permanent logs (usage: make promote-log SRC=path/to/log DEST=category)
	@if [ -z "$(SRC)" ] || [ -z "$(DEST)" ]; then \
		echo "Error: SRC and DEST are required. Usage: make promote-log SRC=logs/runs/my_run DEST=eval"; \
		exit 1; \
	fi
	@if [ ! -d "logs/$(DEST)" ]; then \
		echo "Error: Category logs/$(DEST) does not exist."; \
		exit 1; \
	fi
	@mkdir -p logs/$(DEST)
	@mv $(SRC) logs/$(DEST)/
	@echo "Promoted $(SRC) to logs/$(DEST)/"

run-smoke: ## Run smoke test inside pdfscore_pipeline_gpu container
	@mkdir -p artifacts
	@echo "Running smoke test..."
	@docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/opt/venv_pipeline/bin/python src/pipeline/main.py --config "configs/smoke_test.yaml" > artifacts/smoke_test.log 2>&1 || \
		(EXIT_CODE=$$?; echo "Smoke test failed with exit code $$EXIT_CODE. See artifacts/smoke_test.log"; exit $$EXIT_CODE)
	@echo "Smoke test complete successfully. See artifacts/smoke_test.log"

run-smoke-sr: run-smoke ## Alias for run-smoke (deprecated)

run-pipeline: ## Run the pipeline with a custom config (usage: make run-pipeline CONFIG=path/to/config.yaml)
	@if [ -z "$(CONFIG)" ]; then echo "Error: CONFIG is required. Usage: make run-pipeline CONFIG=path/to/config.yaml"; exit 1; fi
	@mkdir -p artifacts
	@LOG_FILE="artifacts/$$(basename "$(CONFIG)" .yaml)_$$(date +%Y%m%d_%H%M%S).log"; \
	echo "Running pipeline with $(CONFIG). Logging to $$LOG_FILE..."; \
	docker run --rm --gpus all -v $(PWD):/workspace -w /workspace -e PYTHONPATH=/workspace pdfscore_pipeline_gpu \
		/opt/venv_pipeline/bin/python src/pipeline/main.py --config "$(CONFIG)" --skip-existing > "$$LOG_FILE" 2>&1 || \
		(EXIT_CODE=$$?; echo "Pipeline failed with exit code $$EXIT_CODE. See $$LOG_FILE"; exit $$EXIT_CODE); \
	echo "Pipeline execution finished successfully. See $$LOG_FILE"

eval-issue120-full: ## Evaluate Issue #120 canonical full-68 detector intermediates without running the pipeline
	@mkdir -p "$(ISSUE120_OUTPUT_DIR)"
	@MEASURE_ARG=""; \
	if [ -n "$(ISSUE120_MEASURE_SUMMARY)" ]; then \
		MEASURE_ARG="--measure-summary-json $(ISSUE120_MEASURE_SUMMARY)"; \
	fi; \
	PYTHONPATH=. python3 tools/issue120/eval_full68_from_intermediates.py \
		--results-dir "$(ISSUE120_RESULTS_DIR)" \
		--gt-root "$(ISSUE120_GT_ROOT)" \
		--output-dir "$(ISSUE120_OUTPUT_DIR)" \
		--score-threshold "$(ISSUE120_SCORE_THRESHOLD)" \
		--xdist-threshold "$(ISSUE120_XDIST_THRESHOLD)" \
		$$MEASURE_ARG

repo-tree: ## Generate a repository directory overview
	tree -L 3 -I "artifacts|logs|temp|datasets|.git|__pycache__|.venv*" > artifacts/repo_tree.txt

check-consistency: ## Check repository consistency (Manifest and Freshness)
	@mkdir -p artifacts
	@python3 tools/check_repo_consistency.py --stale-days 30 > artifacts/consistency_check.log 2>&1 || \
		(EXIT_CODE=$$?; cat artifacts/consistency_check.log; exit $$EXIT_CODE)
	@cat artifacts/consistency_check.log

setup-worktree: ## Setup a new worktree and container (usage: make setup-worktree BRANCH=branch_name)
	@if [ -z "$(BRANCH)" ]; then echo "Error: BRANCH is required."; exit 1; fi
	@./.agents/skills/worktree-manager/run.sh add $(BRANCH)

test: ## Run test suite
	PYTHONPATH=. .venv_pdf/bin/pytest tests/ > artifacts/test_results.txt

repo-summary: ## Generate comprehensive repository summary
	./.agents/skills/repo-summary/run.sh

issue-triage: ## Fetch and triage open GitHub issues
	./.agents/skills/issue-triage/run.sh

issue-post-mortem: ## Review completed work against original issue
	./.agents/skills/issue-post-mortem/run.sh

visual-diff: ## Identify and collect recent visual evidence
	./.agents/skills/visual-diff-viewer/run.sh

api-explore: ## Extract API info from a Python file (usage: make api-explore FILE=path/to/file.py)
	./.agents/skills/python-api-explorer/run.sh "$(FILE)"

artifact-summary: ## Summarize all artifacts
	./.agents/skills/artifact-clerk/run.sh


