from tools.issue294.run_post277_mapping_guarded_full68_host import (
    MAPPING_GUARDED_MATRIX_SCRIPT,
    STANDARD_MATRIX_SCRIPT,
    rewrite_matrix_command,
)


def test_rewrite_matrix_command_only_swaps_issue294_matrix_entrypoint() -> None:
    command = [
        "docker",
        "exec",
        "container",
        "python",
        STANDARD_MATRIX_SCRIPT,
        "--summary",
        "/workspace/logs/summary.json",
    ]
    rewritten = rewrite_matrix_command(command)
    assert rewritten != command
    assert MAPPING_GUARDED_MATRIX_SCRIPT in rewritten
    assert STANDARD_MATRIX_SCRIPT not in rewritten
    assert command[4] == STANDARD_MATRIX_SCRIPT


def test_rewrite_matrix_command_leaves_other_commands_unchanged() -> None:
    command = ["docker", "exec", "container", "chown", "-R", "1000:1000", "/workspace/logs"]
    assert rewrite_matrix_command(command) == command
