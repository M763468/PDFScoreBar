# worktree-manager

## Purpose
Enables AI agents to autonomously build, manage, and clean up parallel development environments (git worktrees). This skill ensures compliance with the Shared/Isolated data policies defined in `docs/LOG_MANAGEMENT.md`, maintaining data integrity during parallel tasks.

## Inputs
- `COMMAND`: `add`, `remove`, or `list`.
- `BRANCH_NAME`: The name of the git branch to create a worktree for.
- `CONTAINER_SUFFIX` (optional for `add`): A custom suffix for the worktree directory and container name.

## Steps
1. **Setup**:
   - Run `./run.sh add <branch_name>` to create a new worktree and start an isolated Docker container.
2. **Work**:
   - Navigate to the newly created worktree path and perform tasks using the designated container.
3. **Promote Assets**:
   - After completing the work, if there are logs or artifacts to persist, use `make promote-log SRC=<path> DEST=<category>` to move them to permanent storage in the main repository.
4. **Cleanup**:
   - Run `./run.sh remove <branch_name>` to delete the worktree and automatically stop/remove the associated container.

## Required commands
- `git worktree`: For managing worktrees.
- `docker`: For container lifecycle management.
- `./run.sh`: Unified management script within the skill directory.
- `make promote-log`: For persisting important artifacts.
- `make clean-logs`: For periodic maintenance of old logs.
