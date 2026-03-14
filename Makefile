.PHONY: help lint format

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run lint and format checks using ruff
	uvx ruff check . && uvx ruff format --check .

format: ## Format code using ruff
	uvx ruff format .
	uvx ruff check --fix .

clean-artifacts: ## Remove all logs from the artifacts directory
	rm -f artifacts/*.log artifacts/*.txt

run-smoke-sr: ## Run smoke test inside sr_eval_gpu container (requires running container)
	@mkdir -p artifacts
	@echo "Running smoke test..."
	@docker exec -w /workspace -e PYTHONPATH=/workspace sr_eval_gpu \
		/opt/venv_sr/bin/python src/pipeline/main.py --config "configs/smoke_test.yaml" > artifacts/smoke_test.log 2>&1 || \
		(EXIT_CODE=$$?; echo "Smoke test failed with exit code $$EXIT_CODE. See artifacts/smoke_test.log"; exit $$EXIT_CODE)
	@echo "Smoke test complete successfully. See artifacts/smoke_test.log"

run-pipeline: ## Run the pipeline with a custom config (usage: make run-pipeline CONFIG=path/to/config.yaml)
	@if [ -z "$(CONFIG)" ]; then echo "Error: CONFIG is required. Usage: make run-pipeline CONFIG=path/to/config.yaml"; exit 1; fi
	@mkdir -p artifacts
	@LOG_FILE="artifacts/$$(basename "$(CONFIG)" .yaml)_$$(date +%Y%m%d_%H%M%S).log"; \
	echo "Running pipeline with $(CONFIG). Logging to $$LOG_FILE..."; \
	docker exec -w /workspace -e PYTHONPATH=/workspace sr_eval_gpu \
		/opt/venv_sr/bin/python src/pipeline/main.py --config "$(CONFIG)" --skip-existing > "$$LOG_FILE" 2>&1 || \
		(EXIT_CODE=$$?; echo "Pipeline failed with exit code $$EXIT_CODE. See $$LOG_FILE"; exit $$EXIT_CODE); \
	echo "Pipeline execution finished successfully. See $$LOG_FILE"

repo-tree: ## Generate a repository directory overview
	tree -L 3 -I "artifacts|logs|temp|datasets|.git|__pycache__|.venv*" > artifacts/repo_tree.txt

check-consistency: ## Check repository consistency (Manifest and Freshness)
	@mkdir -p artifacts
	@python3 tools/check_repo_consistency.py --stale-days 30 > artifacts/consistency_check.log 2>&1 || \
		(EXIT_CODE=$$?; cat artifacts/consistency_check.log; exit $$EXIT_CODE)
	@cat artifacts/consistency_check.log

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


