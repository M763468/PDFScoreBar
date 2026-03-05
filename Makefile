.PHONY: help lint format

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

lint: ## Run lint checks using ruff
	uvx ruff check .

format: ## Format code using ruff
	uvx ruff format .
	uvx ruff check --fix .

repo-tree: ## Generate a repository directory overview
	tree -L 3 -I "artifacts|logs|temp|datasets|.git|__pycache__|.venv*" > artifacts/repo_tree.txt

test: ## Run test suite
	pytest > artifacts/test_results.txt


