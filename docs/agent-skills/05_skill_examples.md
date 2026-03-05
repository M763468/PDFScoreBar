# Example Skill Proposals

These examples are generic and should be adapted to each repository.

## repo-tree

run.sh

tree -L 3 \> artifacts/repo_tree.txt

## dependency-snapshot

pip freeze \> artifacts/dependencies.txt

## run-tests

pytest -q \> artifacts/test_results.txt

## lint-fix

eslint . --fix

## build-project

npm run build

## repo-summary (composed skill)

tree -L 3 \> artifacts/tree.txt cloc . \> artifacts/loc.txt pip freeze
\> artifacts/deps.txt

These examples illustrate typical CLI wrappers used by coding agents.
