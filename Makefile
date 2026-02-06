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


