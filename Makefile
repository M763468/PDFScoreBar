.PHONY: help lint format

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run lint checks using ruff
	uvx ruff check .

format: ## Format code using ruff
	uvx ruff format .
	uvx ruff check --fix .

run-smoke-sr: ## Run smoke test with SR inside sr_eval container (requires Docker)
	docker run --rm --gpus all -v $$(pwd):/workspace -w /workspace sr_eval:latest \
		bash -c "export PYTHONPATH=/workspace:/workspace/external/homr; \
		/opt/venv_sr/bin/python -m src.pipeline.main --config configs/smoke_test.yaml"

verify-issue18: ## Verify Issue #18 (model persistence) inside sr_eval container
	docker run --rm --gpus all -v $$(pwd):/workspace -w /workspace sr_eval:latest \
		bash -c "export PYTHONPATH=/workspace:/workspace/external/homr; \
		/opt/venv_sr/bin/python -m src.pipeline.main --config configs/verify_issue18.yaml"

repo-tree: ## Generate a repository directory overview
	tree -L 3 -I "artifacts|logs|temp|datasets|.git|__pycache__|.venv*" > artifacts/repo_tree.txt

test: ## Run test suite
	pytest > artifacts/test_results.txt

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


