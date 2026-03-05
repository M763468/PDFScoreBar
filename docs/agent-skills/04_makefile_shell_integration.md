# Makefile Integration

Many projects already expose operations via Make.

Coding agents can reliably use Make targets as skills.

Example:

Makefile

repo-tree: tree -L 3 \> artifacts/repo_tree.txt

tests: pytest -q \> artifacts/test_results.txt

lint: eslint . --fix

build: npm run build

Agent usage:

make repo-tree make tests make lint

Advantages:

-   standardized command interface
-   dependency chaining
-   easy discovery

Example dependency:

test-all: lint tests

Agent can simply run:

make test-all
